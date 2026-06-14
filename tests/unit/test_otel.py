"""Tests for OpenTelemetry instrumentation in the Hyperping SDK."""

from __future__ import annotations

import json as _json
from collections.abc import Generator
from typing import Any
from unittest.mock import patch

import httpx
import pytest
import respx
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from hyperping._async_client import AsyncHyperpingClient
from hyperping._async_mcp_transport import AsyncMcpTransport
from hyperping._mcp_transport import McpTransport
from hyperping._version import __version__ as _SDK_VERSION  # noqa: N812
from hyperping.client import HyperpingClient, RetryConfig
from hyperping.endpoints import API_BASE, MCP_URL, Endpoint
from hyperping.exceptions import HyperpingAPIError, HyperpingAuthError

# ── Helpers ────────────────────────────────────────────────────────────────────


def _tool_resp(data: dict[str, Any], *, req_id: int = 2) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"content": [{"type": "text", "text": _json.dumps(data)}]},
        },
    )


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture
def _span_provider() -> Generator[tuple[InMemorySpanExporter, TracerProvider], None, None]:
    """Create an isolated local TracerProvider and InMemorySpanExporter.

    Does NOT modify the global OTel TracerProvider (which can only be set once
    per process). Each test gets its own provider and exporter.
    """
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    yield exporter, provider
    exporter.clear()


@pytest.fixture
def span_exporter(
    _span_provider: tuple[InMemorySpanExporter, TracerProvider],
) -> InMemorySpanExporter:
    """Expose just the InMemorySpanExporter from the local provider."""
    exporter, _ = _span_provider
    return exporter


@pytest.fixture
def otel_tracer(
    _span_provider: tuple[InMemorySpanExporter, TracerProvider],
) -> Any:
    """Return a test-local tracer from the isolated TracerProvider."""
    _, provider = _span_provider
    return provider.get_tracer("hyperping", _SDK_VERSION)


@pytest.fixture
def otel_client(otel_tracer: Any) -> Generator[HyperpingClient, None, None]:
    """HyperpingClient with the test-local tracer injected (bypasses global OTel)."""
    c = HyperpingClient(
        api_key="sk_test_key",
        base_url=API_BASE,
        retry_config=RetryConfig(max_retries=0),
    )
    c._tracer = otel_tracer  # type: ignore[assignment]
    yield c
    c.close()


@pytest.fixture
def otel_async_client(otel_tracer: Any) -> Generator[AsyncHyperpingClient, None, None]:
    """AsyncHyperpingClient with the test-local tracer injected."""
    c = AsyncHyperpingClient(
        api_key="sk_test_key",
        base_url=API_BASE,
        retry_config=RetryConfig(max_retries=0),
    )
    c._tracer = otel_tracer  # type: ignore[assignment]
    yield c


@pytest.fixture
def otel_mcp(otel_tracer: Any) -> Generator[McpTransport, None, None]:
    """McpTransport with test-local tracer and pre-initialized state."""
    t = McpTransport(api_key="sk_test", base_url=MCP_URL)
    t._tracer = otel_tracer  # type: ignore[assignment]
    t._initialized = True
    t._init_result = {"protocolVersion": "2025-03-26"}
    yield t
    t.close()


@pytest.fixture
def otel_async_mcp(otel_tracer: Any) -> Generator[AsyncMcpTransport, None, None]:
    """AsyncMcpTransport with test-local tracer and pre-initialized state."""
    t = AsyncMcpTransport(api_key="sk_test", base_url=MCP_URL)
    t._tracer = otel_tracer  # type: ignore[assignment]
    t._initialized = True
    t._init_result = {"protocolVersion": "2025-03-26"}
    yield t


# ── TestOtelModule ─────────────────────────────────────────────────────────────


class TestOtelModule:
    def test_has_otel_flag_true_when_installed(self) -> None:
        """HAS_OTEL is True in the test environment (opentelemetry-api is installed)."""
        from hyperping._otel import HAS_OTEL

        assert HAS_OTEL is True

    def test_get_tracer_returns_tracer(self) -> None:
        """get_tracer() returns a non-None tracer when OTel is installed."""
        from hyperping._otel import get_tracer

        t = get_tracer()
        assert t is not None

    def test_get_tracer_returns_none_when_missing(self) -> None:
        """get_tracer() returns None when HAS_OTEL is False."""
        import hyperping._otel as otel_mod

        with patch.object(otel_mod, "HAS_OTEL", False):
            t = otel_mod.get_tracer()
        assert t is None


# ── TestSyncClientSpans ────────────────────────────────────────────────────────


class TestSyncClientSpans:
    @respx.mock
    def test_request_creates_span(
        self, otel_client: HyperpingClient, span_exporter: InMemorySpanExporter
    ) -> None:
        """GET /v1/monitors emits a span named 'hyperping GET /v1/monitors'."""
        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(return_value=httpx.Response(200, json=[]))
        otel_client.list_monitors()
        spans = span_exporter.get_finished_spans()
        assert any(s.name == f"hyperping GET {Endpoint.MONITORS}" for s in spans)

    @respx.mock
    def test_span_has_http_method_attribute(
        self, otel_client: HyperpingClient, span_exporter: InMemorySpanExporter
    ) -> None:
        """Span carries http.request.method = 'GET'."""
        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(return_value=httpx.Response(200, json=[]))
        otel_client.list_monitors()
        spans = [s for s in span_exporter.get_finished_spans() if "GET" in s.name]
        assert spans, "No matching span found"
        assert spans[0].attributes.get("http.request.method") == "GET"  # type: ignore[union-attr]

    @respx.mock
    def test_span_has_url_attribute(
        self, otel_client: HyperpingClient, span_exporter: InMemorySpanExporter
    ) -> None:
        """Span carries url.full."""
        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(return_value=httpx.Response(200, json=[]))
        otel_client.list_monitors()
        spans = [s for s in span_exporter.get_finished_spans() if "GET" in s.name]
        assert spans
        assert "url.full" in (spans[0].attributes or {})

    @respx.mock
    def test_span_has_status_ok_on_success(
        self, otel_client: HyperpingClient, span_exporter: InMemorySpanExporter
    ) -> None:
        """Span status is UNSET (interpreted as OK) on successful 200 response."""
        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(return_value=httpx.Response(200, json=[]))
        otel_client.list_monitors()
        spans = [s for s in span_exporter.get_finished_spans() if "GET" in s.name]
        assert spans
        assert spans[0].status.status_code == StatusCode.UNSET

    @respx.mock
    def test_span_records_error_on_api_error(
        self, otel_client: HyperpingClient, span_exporter: InMemorySpanExporter
    ) -> None:
        """Span status is ERROR and exception is recorded on 500 response."""
        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(
            return_value=httpx.Response(500, json={"error": "Internal Server Error"})
        )
        with pytest.raises(HyperpingAPIError):
            otel_client.list_monitors()
        spans = [s for s in span_exporter.get_finished_spans() if "GET" in s.name]
        assert spans
        assert spans[0].status.status_code == StatusCode.ERROR

    @respx.mock
    def test_span_records_error_on_auth_error(
        self, otel_client: HyperpingClient, span_exporter: InMemorySpanExporter
    ) -> None:
        """Span status is ERROR on 401 (authentication failure)."""
        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(
            return_value=httpx.Response(401, json={"error": "Unauthorized"})
        )
        with pytest.raises(HyperpingAuthError):
            otel_client.list_monitors()
        spans = [s for s in span_exporter.get_finished_spans() if "GET" in s.name]
        assert spans
        assert spans[0].status.status_code == StatusCode.ERROR

    @respx.mock
    def test_no_span_when_tracer_is_none(self, span_exporter: InMemorySpanExporter) -> None:
        """When _tracer is None, no span is emitted and the client works normally."""
        c = HyperpingClient(
            api_key="sk_test_key",
            base_url=API_BASE,
            retry_config=RetryConfig(max_retries=0),
        )
        c._tracer = None  # type: ignore[assignment]
        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(return_value=httpx.Response(200, json=[]))
        c.list_monitors()
        spans = [s for s in span_exporter.get_finished_spans() if "hyperping" in s.name]
        assert len(spans) == 0
        c.close()


# ── TestAsyncClientSpans ───────────────────────────────────────────────────────


class TestAsyncClientSpans:
    @respx.mock
    async def test_async_request_creates_span(
        self, otel_async_client: AsyncHyperpingClient, span_exporter: InMemorySpanExporter
    ) -> None:
        """Async GET /v1/monitors emits a span."""
        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(return_value=httpx.Response(200, json=[]))
        await otel_async_client.list_monitors()
        spans = span_exporter.get_finished_spans()
        assert any(s.name == f"hyperping GET {Endpoint.MONITORS}" for s in spans)
        await otel_async_client.close()

    @respx.mock
    async def test_async_span_has_attributes(
        self, otel_async_client: AsyncHyperpingClient, span_exporter: InMemorySpanExporter
    ) -> None:
        """Async span carries http.request.method and url.full."""
        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(return_value=httpx.Response(200, json=[]))
        await otel_async_client.list_monitors()
        spans = [s for s in span_exporter.get_finished_spans() if "GET" in s.name]
        assert spans
        attrs = spans[0].attributes or {}
        assert attrs.get("http.request.method") == "GET"
        assert "url.full" in attrs
        await otel_async_client.close()

    @respx.mock
    async def test_async_span_records_error(
        self, otel_async_client: AsyncHyperpingClient, span_exporter: InMemorySpanExporter
    ) -> None:
        """Async span status is ERROR on 500."""
        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(
            return_value=httpx.Response(500, json={"error": "Server Error"})
        )
        with pytest.raises(HyperpingAPIError):
            await otel_async_client.list_monitors()
        spans = [s for s in span_exporter.get_finished_spans() if "GET" in s.name]
        assert spans
        assert spans[0].status.status_code == StatusCode.ERROR
        await otel_async_client.close()


# ── TestMcpTransportSpans ──────────────────────────────────────────────────────


class TestMcpTransportSpans:
    @respx.mock
    def test_mcp_rpc_creates_span(
        self, otel_mcp: McpTransport, span_exporter: InMemorySpanExporter
    ) -> None:
        """tools/call emits a span named 'hyperping.mcp tools/call'."""
        respx.post(MCP_URL).mock(return_value=_tool_resp({"ok": True}))
        otel_mcp.call_tool("test_tool")
        spans = span_exporter.get_finished_spans()
        assert any(s.name == "hyperping.mcp tools/call" for s in spans)

    @respx.mock
    def test_mcp_span_has_rpc_method_attribute(
        self, otel_mcp: McpTransport, span_exporter: InMemorySpanExporter
    ) -> None:
        """MCP span carries rpc.method = 'tools/call'."""
        respx.post(MCP_URL).mock(return_value=_tool_resp({"ok": True}))
        otel_mcp.call_tool("test_tool")
        spans = [s for s in span_exporter.get_finished_spans() if "tools/call" in s.name]
        assert spans
        assert spans[0].attributes.get("rpc.method") == "tools/call"  # type: ignore[union-attr]

    @respx.mock
    def test_mcp_span_has_rpc_system_attribute(
        self, otel_mcp: McpTransport, span_exporter: InMemorySpanExporter
    ) -> None:
        """MCP span carries rpc.system = 'jsonrpc'."""
        respx.post(MCP_URL).mock(return_value=_tool_resp({"ok": True}))
        otel_mcp.call_tool("test_tool")
        spans = [s for s in span_exporter.get_finished_spans() if "tools/call" in s.name]
        assert spans
        assert spans[0].attributes.get("rpc.system") == "jsonrpc"  # type: ignore[union-attr]

    @respx.mock
    def test_mcp_span_records_error_on_rpc_error(
        self, otel_mcp: McpTransport, span_exporter: InMemorySpanExporter
    ) -> None:
        """MCP span status is ERROR when JSON-RPC returns an error."""
        respx.post(MCP_URL).mock(
            return_value=httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": 2, "error": {"code": -32600, "message": "Bad req"}},
            )
        )
        with pytest.raises(HyperpingAPIError):
            otel_mcp.call_tool("test_tool")
        spans = [s for s in span_exporter.get_finished_spans() if "tools/call" in s.name]
        assert spans
        assert spans[0].status.status_code == StatusCode.ERROR

    @respx.mock
    def test_mcp_span_records_error_on_http_error(
        self, otel_mcp: McpTransport, span_exporter: InMemorySpanExporter
    ) -> None:
        """MCP span status is ERROR on HTTP 500."""
        respx.post(MCP_URL).mock(return_value=httpx.Response(500))
        with pytest.raises(HyperpingAPIError):
            otel_mcp.call_tool("test_tool")
        spans = [s for s in span_exporter.get_finished_spans() if "tools/call" in s.name]
        assert spans
        assert spans[0].status.status_code == StatusCode.ERROR


# ── TestAsyncMcpTransportSpans ─────────────────────────────────────────────────


class TestAsyncMcpTransportSpans:
    @respx.mock
    async def test_async_mcp_rpc_creates_span(
        self, otel_async_mcp: AsyncMcpTransport, span_exporter: InMemorySpanExporter
    ) -> None:
        """Async tools/call emits 'hyperping.mcp tools/call'."""
        respx.post(MCP_URL).mock(return_value=_tool_resp({"ok": True}))
        await otel_async_mcp.call_tool("test_tool")
        spans = span_exporter.get_finished_spans()
        assert any(s.name == "hyperping.mcp tools/call" for s in spans)
        await otel_async_mcp.close()

    @respx.mock
    async def test_async_mcp_span_records_error(
        self, otel_async_mcp: AsyncMcpTransport, span_exporter: InMemorySpanExporter
    ) -> None:
        """Async MCP span status is ERROR on HTTP 500."""
        respx.post(MCP_URL).mock(return_value=httpx.Response(500))
        with pytest.raises(HyperpingAPIError):
            await otel_async_mcp.call_tool("test_tool")
        spans = [s for s in span_exporter.get_finished_spans() if "tools/call" in s.name]
        assert spans
        assert spans[0].status.status_code == StatusCode.ERROR
        await otel_async_mcp.close()


# ── TestNoopWhenUninstalled ────────────────────────────────────────────────────


class TestNoopWhenUninstalled:
    @respx.mock
    def test_sync_client_works_without_otel(self) -> None:
        """Client works normally when _tracer is None (simulates HAS_OTEL=False)."""
        import hyperping._otel as otel_mod

        with patch.object(otel_mod, "HAS_OTEL", False):
            c = HyperpingClient(
                api_key="sk_test_key",
                base_url=API_BASE,
                retry_config=RetryConfig(max_retries=0),
            )
        assert c._tracer is None
        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(return_value=httpx.Response(200, json=[]))
        result = c.list_monitors()
        assert result == []
        c.close()

    @respx.mock
    async def test_async_client_works_without_otel(self) -> None:
        """Async client works normally when _tracer is None."""
        import hyperping._otel as otel_mod

        with patch.object(otel_mod, "HAS_OTEL", False):
            c = AsyncHyperpingClient(
                api_key="sk_test_key",
                base_url=API_BASE,
                retry_config=RetryConfig(max_retries=0),
            )
        assert c._tracer is None
        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(return_value=httpx.Response(200, json=[]))
        result = await c.list_monitors()
        assert result == []
        await c.close()

    @respx.mock
    def test_mcp_transport_works_without_otel(self) -> None:
        """MCP transport works normally when _tracer is None."""
        import hyperping._otel as otel_mod

        with patch.object(otel_mod, "HAS_OTEL", False):
            t = McpTransport(api_key="sk_test", base_url=MCP_URL)
        assert t._tracer is None
        t._initialized = True
        t._init_result = {"protocolVersion": "2025-03-26"}
        respx.post(MCP_URL).mock(return_value=_tool_resp({"ok": True}))
        result = t.call_tool("test_tool")
        assert result == {"ok": True}
        t.close()

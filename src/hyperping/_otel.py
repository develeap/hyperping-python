"""Optional OpenTelemetry instrumentation for the Hyperping SDK.

When opentelemetry-api is not installed, all functions are no-ops and the SDK
behaves identically to today with zero overhead.

Install ``hyperping[otel]`` to enable tracing.
"""

from __future__ import annotations

import contextlib
from collections.abc import Generator
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

try:
    from opentelemetry import trace
    from opentelemetry.trace import Span, Status, StatusCode, Tracer  # noqa: F401

    HAS_OTEL: bool = True
except ImportError:
    HAS_OTEL = False

if TYPE_CHECKING:
    from opentelemetry.trace import Span, Tracer

from hyperping._version import __version__


def get_tracer() -> Tracer | None:
    """Return a Tracer for the hyperping SDK, or None when OTel is not installed."""
    if not HAS_OTEL:
        return None
    return trace.get_tracer("hyperping", __version__)


@contextlib.contextmanager
def start_request_span(
    tracer: Tracer | None,
    method: str,
    path: str,
    base_url: str,
) -> Generator[Span | None, None, None]:
    """Context manager wrapping a REST API call in an OTel span.

    Yields None (no-op) when tracer is None. Compatible with both sync and
    async callers because the span lifecycle is synchronous regardless.
    """
    if tracer is None:
        yield None
        return

    span_name = f"hyperping {method} {path}"
    server_address = urlsplit(base_url).hostname or base_url

    with tracer.start_as_current_span(span_name) as span:
        span.set_attribute("http.request.method", method)
        span.set_attribute("url.full", base_url.rstrip("/") + path)
        span.set_attribute("server.address", server_address)
        span.set_attribute("hyperping.sdk.version", __version__)
        yield span


@contextlib.contextmanager
def start_rpc_span(
    tracer: Tracer | None,
    rpc_method: str,
    url: str,
) -> Generator[Span | None, None, None]:
    """Context manager wrapping an MCP JSON-RPC call in an OTel span.

    Yields None (no-op) when tracer is None.
    """
    if tracer is None:
        yield None
        return

    span_name = f"hyperping.mcp {rpc_method}"
    server_address = urlsplit(url).hostname or url

    with tracer.start_as_current_span(span_name) as span:
        span.set_attribute("rpc.method", rpc_method)
        span.set_attribute("rpc.system", "jsonrpc")
        span.set_attribute("server.address", server_address)
        span.set_attribute("hyperping.sdk.version", __version__)
        yield span


def record_error(span: Span | None, exception: BaseException) -> None:
    """Record an exception on a span and set its status to ERROR.

    No-op when span is None.
    """
    if span is None or not HAS_OTEL:
        return
    span.set_status(Status(StatusCode.ERROR))
    span.record_exception(exception)

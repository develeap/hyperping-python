"""Tests for the async MCP JSON-RPC 2.0 transport layer."""

import json

import httpx
import pytest
import respx
from pydantic import SecretStr

from hyperping._async_mcp_transport import MCP_URL, AsyncMcpTransport
from hyperping.exceptions import (
    HyperpingAPIError,
    HyperpingAuthError,
    HyperpingNotFoundError,
    HyperpingRateLimitError,
    HyperpingValidationError,
)

# -- Helpers ------------------------------------------------------------------

INIT_RESPONSE = httpx.Response(
    200,
    json={
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "serverInfo": {"name": "hyperping"},
        },
    },
)

NOTIFICATION_ACCEPTED = httpx.Response(202)


def _tool_response(data: dict, *, req_id: int = 2) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"content": [{"type": "text", "text": json.dumps(data)}]},
        },
    )


# -- Tests --------------------------------------------------------------------


@respx.mock
async def test_initialize():
    respx.post(MCP_URL).mock(
        side_effect=[INIT_RESPONSE, NOTIFICATION_ACCEPTED],
    )
    transport = AsyncMcpTransport(api_key="sk_test", base_url=MCP_URL)
    result = await transport.initialize()
    assert result["protocolVersion"] == "2025-03-26"
    await transport.close()


@respx.mock
async def test_call_tool_auto_initializes():
    respx.post(MCP_URL).mock(
        side_effect=[
            INIT_RESPONSE,
            NOTIFICATION_ACCEPTED,
            _tool_response({"schedules": []}),
        ],
    )
    transport = AsyncMcpTransport(api_key="sk_test", base_url=MCP_URL)
    result = await transport.call_tool("list_on_call_schedules")
    assert result == {"schedules": []}
    await transport.close()


@respx.mock
async def test_call_tool_http_401():
    respx.post(MCP_URL).mock(return_value=httpx.Response(401, text="Invalid Token"))
    transport = AsyncMcpTransport(api_key="sk_bad", base_url=MCP_URL)
    transport._initialized = True
    with pytest.raises(HyperpingAuthError):
        await transport.call_tool("list_team_members")
    await transport.close()


@respx.mock
async def test_call_tool_http_403():
    respx.post(MCP_URL).mock(return_value=httpx.Response(403, text="Forbidden"))
    transport = AsyncMcpTransport(api_key="sk_bad", base_url=MCP_URL)
    transport._initialized = True
    with pytest.raises(HyperpingAuthError):
        await transport.call_tool("list_team_members")
    await transport.close()


@respx.mock
async def test_call_tool_http_404():
    respx.post(MCP_URL).mock(return_value=httpx.Response(404, text="Not Found"))
    transport = AsyncMcpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    with pytest.raises(HyperpingNotFoundError):
        await transport.call_tool("get_monitor", {"id": "nonexistent"})
    await transport.close()


@respx.mock
async def test_call_tool_http_429():
    respx.post(MCP_URL).mock(
        return_value=httpx.Response(
            429,
            text="Rate limit exceeded",
            headers={"retry-after": "30"},
        ),
    )
    transport = AsyncMcpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    with pytest.raises(HyperpingRateLimitError) as exc_info:
        await transport.call_tool("list_monitors")
    assert exc_info.value.retry_after == 30
    await transport.close()


@respx.mock
async def test_call_tool_http_400():
    respx.post(MCP_URL).mock(return_value=httpx.Response(400, text="Bad Request"))
    transport = AsyncMcpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    with pytest.raises(HyperpingValidationError):
        await transport.call_tool("create_monitor", {"invalid": "params"})
    await transport.close()


@respx.mock
async def test_call_tool_http_500():
    respx.post(MCP_URL).mock(return_value=httpx.Response(500, text="Internal Server Error"))
    transport = AsyncMcpTransport(api_key="sk_test", base_url=MCP_URL, max_retries=0)
    transport._initialized = True
    with pytest.raises(HyperpingAPIError, match="HTTP 500"):
        await transport.call_tool("some_tool")
    await transport.close()


@respx.mock
async def test_call_tool_jsonrpc_error():
    respx.post(MCP_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "error": {"code": -32601, "message": "Method not found"},
            },
        ),
    )
    transport = AsyncMcpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    with pytest.raises(HyperpingAPIError, match="Method not found"):
        await transport.call_tool("nonexistent_tool")
    await transport.close()


@respx.mock
async def test_call_tool_empty_content():
    respx.post(MCP_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"content": []},
            },
        ),
    )
    transport = AsyncMcpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    result = await transport.call_tool("some_tool")
    assert result is None
    await transport.close()


@respx.mock
async def test_call_tool_invalid_json():
    respx.post(MCP_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"content": [{"type": "text", "text": "not valid json{"}]},
            },
        ),
    )
    transport = AsyncMcpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    with pytest.raises(HyperpingAPIError, match="Failed to parse"):
        await transport.call_tool("some_tool")
    await transport.close()


@respx.mock
async def test_call_tool_retry_on_500():
    """Verify that a transient 500 is retried and the second attempt succeeds."""
    respx.post(MCP_URL).mock(
        side_effect=[
            httpx.Response(500, text="Internal Server Error"),
            _tool_response({"ok": True}, req_id=2),
        ],
    )
    transport = AsyncMcpTransport(api_key="sk_test", base_url=MCP_URL, max_retries=1)
    transport._initialized = True
    result = await transport.call_tool("flaky_tool")
    assert result == {"ok": True}
    await transport.close()


async def test_context_manager():
    async with AsyncMcpTransport(api_key="sk_test", base_url=MCP_URL) as transport:
        assert transport is not None


async def test_secretstr_api_key():
    transport = AsyncMcpTransport(api_key=SecretStr("sk_secret"), base_url=MCP_URL)
    assert transport._client.headers["Authorization"] == "Bearer sk_secret"
    await transport.close()


@respx.mock
async def test_call_tool_http_429_non_integer_retry_after():
    """Non-integer retry-after header should be ignored (retry_after=None)."""
    respx.post(MCP_URL).mock(
        return_value=httpx.Response(
            429,
            text="Rate limit exceeded",
            headers={"retry-after": "not-a-number"},
        ),
    )
    transport = AsyncMcpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    with pytest.raises(HyperpingRateLimitError) as exc_info:
        await transport.call_tool("list_monitors")
    assert exc_info.value.retry_after is None
    await transport.close()


@respx.mock
async def test_call_tool_retry_exhausted():
    """All retries exhausted on 500 should raise the last exception."""
    respx.post(MCP_URL).mock(
        side_effect=[
            httpx.Response(500, text="Internal Server Error"),
            httpx.Response(502, text="Bad Gateway"),
        ],
    )
    transport = AsyncMcpTransport(api_key="sk_test", base_url=MCP_URL, max_retries=1)
    transport._initialized = True
    with pytest.raises(HyperpingAPIError, match="HTTP 502"):
        await transport.call_tool("failing_tool")
    await transport.close()


@respx.mock
async def test_call_tool_empty_text():
    """Content with empty text string should return None."""
    respx.post(MCP_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"content": [{"type": "text", "text": ""}]},
            },
        ),
    )
    transport = AsyncMcpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    result = await transport.call_tool("some_tool")
    assert result is None
    await transport.close()


@respx.mock
async def test_send_rpc_notification_returns_none():
    """A notification that gets 200 instead of 202 should still return None."""
    respx.post(MCP_URL).mock(
        return_value=httpx.Response(200, json={"jsonrpc": "2.0"}),
    )
    transport = AsyncMcpTransport(api_key="sk_test", base_url=MCP_URL)
    result = await transport._send_rpc("notifications/initialized", is_notification=True)
    assert result is None
    await transport.close()


@respx.mock
async def test_call_tool_result_none_from_202():
    """If the tool call response is 202 (accepted), call_tool returns None."""
    respx.post(MCP_URL).mock(return_value=httpx.Response(202))
    transport = AsyncMcpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    result = await transport.call_tool("some_tool")
    assert result is None
    await transport.close()

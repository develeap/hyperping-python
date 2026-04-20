"""Tests for the MCP JSON-RPC 2.0 transport layer."""

import json
from unittest.mock import patch

import httpx
import pytest
import respx

from hyperping._mcp_transport import MCP_URL, McpTransport
from hyperping.exceptions import (
    HyperpingAPIError,
    HyperpingAuthError,
    HyperpingNotFoundError,
    HyperpingRateLimitError,
    HyperpingValidationError,
)


@respx.mock
def test_initialize():
    respx.post(MCP_URL).mock(
        side_effect=[
            httpx.Response(
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
            ),
            httpx.Response(202),  # notifications/initialized
        ]
    )
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    result = transport.initialize()
    assert result["protocolVersion"] == "2025-03-26"
    transport.close()


@respx.mock
def test_call_tool_auto_initializes():
    respx.post(MCP_URL).mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": {"protocolVersion": "2025-03-26"},
                },
            ),
            httpx.Response(202),
            httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps({"schedules": []})}]
                    },
                },
            ),
        ]
    )
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    result = transport.call_tool("list_on_call_schedules")
    assert result == {"schedules": []}
    transport.close()


@respx.mock
def test_call_tool_http_401():
    respx.post(MCP_URL).mock(return_value=httpx.Response(401, text="Invalid Token"))
    transport = McpTransport(api_key="sk_bad", base_url=MCP_URL)
    transport._initialized = True  # skip init
    with pytest.raises(HyperpingAuthError):
        transport.call_tool("list_team_members")
    transport.close()


@respx.mock
def test_call_tool_http_403():
    """MCP server returns 403 (not 401) for invalid API keys."""
    respx.post(MCP_URL).mock(return_value=httpx.Response(403, text="Forbidden"))
    transport = McpTransport(api_key="sk_bad", base_url=MCP_URL)
    transport._initialized = True
    with pytest.raises(HyperpingAuthError):
        transport.call_tool("list_team_members")
    transport.close()


@respx.mock
def test_call_tool_jsonrpc_error():
    respx.post(MCP_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "error": {"code": -32601, "message": "Method not found"},
            },
        )
    )
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    with pytest.raises(HyperpingAPIError, match="Method not found"):
        transport.call_tool("nonexistent_tool")
    transport.close()


@respx.mock
def test_call_tool_empty_content():
    """Test that empty content returns None."""
    respx.post(MCP_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"content": []},
            },
        )
    )
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    result = transport.call_tool("some_tool")
    assert result is None
    transport.close()


@respx.mock
def test_call_tool_invalid_json_response():
    """Test that invalid JSON in tool response raises HyperpingAPIError."""
    respx.post(MCP_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"content": [{"type": "text", "text": "not valid json{"}]},
            },
        )
    )
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    with pytest.raises(HyperpingAPIError, match="Failed to parse"):
        transport.call_tool("some_tool")
    transport.close()


@respx.mock
def test_call_tool_http_500():
    """Test that HTTP 500 raises HyperpingAPIError."""
    respx.post(MCP_URL).mock(return_value=httpx.Response(500, text="Internal Server Error"))
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    with pytest.raises(HyperpingAPIError, match="HTTP 500"):
        transport.call_tool("some_tool")
    transport.close()


def test_context_manager():
    """Test that McpTransport supports context manager protocol."""
    with McpTransport(api_key="sk_test", base_url=MCP_URL) as transport:
        assert transport is not None


def test_secretstr_api_key():
    """Test that McpTransport accepts SecretStr api_key."""
    from pydantic import SecretStr

    transport = McpTransport(api_key=SecretStr("sk_secret"), base_url=MCP_URL)
    assert transport._client.headers["Authorization"] == "Bearer sk_secret"
    transport.close()


@respx.mock
def test_call_tool_http_404():
    """Test that HTTP 404 raises HyperpingNotFoundError."""
    respx.post(MCP_URL).mock(return_value=httpx.Response(404, text="Not Found"))
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    with pytest.raises(HyperpingNotFoundError, match="Resource not found"):
        transport.call_tool("missing_tool")
    transport.close()


@respx.mock
def test_call_tool_http_429_with_retry_after():
    """Test that HTTP 429 with Retry-After header parses retry_after."""
    respx.post(MCP_URL).mock(
        return_value=httpx.Response(
            429,
            text="Rate limited",
            headers={"retry-after": "30"},
        )
    )
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    with pytest.raises(HyperpingRateLimitError) as exc_info:
        transport.call_tool("some_tool")
    assert exc_info.value.retry_after == 30
    assert exc_info.value.status_code == 429
    transport.close()


@respx.mock
def test_call_tool_http_429_no_retry_after():
    """Test that HTTP 429 without Retry-After header sets retry_after=None."""
    respx.post(MCP_URL).mock(return_value=httpx.Response(429, text="Rate limited"))
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    with pytest.raises(HyperpingRateLimitError) as exc_info:
        transport.call_tool("some_tool")
    assert exc_info.value.retry_after is None
    transport.close()


@respx.mock
def test_call_tool_http_429_non_integer_retry_after():
    """Test 429 with non-integer Retry-After falls back to None."""
    respx.post(MCP_URL).mock(
        return_value=httpx.Response(
            429,
            text="Rate limited",
            headers={"retry-after": "Thu, 01 Dec 2025 16:00:00 GMT"},
        )
    )
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    with pytest.raises(HyperpingRateLimitError) as exc_info:
        transport.call_tool("some_tool")
    assert exc_info.value.retry_after is None
    transport.close()


@respx.mock
def test_call_tool_http_400():
    """Test that HTTP 400 raises HyperpingValidationError."""
    respx.post(MCP_URL).mock(return_value=httpx.Response(400, text="Bad Request"))
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    with pytest.raises(HyperpingValidationError, match="Validation error"):
        transport.call_tool("some_tool")
    transport.close()


@respx.mock
def test_call_tool_http_422():
    """Test that HTTP 422 raises HyperpingValidationError."""
    respx.post(MCP_URL).mock(return_value=httpx.Response(422, text="Unprocessable Entity"))
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    with pytest.raises(HyperpingValidationError) as exc_info:
        transport.call_tool("some_tool")
    assert exc_info.value.status_code == 422
    transport.close()


@respx.mock
def test_call_tool_generic_error_response_body():
    """Test generic HTTP error attaches response_body with raw text."""
    respx.post(MCP_URL).mock(return_value=httpx.Response(418, text="I'm a teapot"))
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    with pytest.raises(HyperpingAPIError) as exc_info:
        transport.call_tool("some_tool")
    assert exc_info.value.status_code == 418
    assert exc_info.value.response_body["raw"] == "I'm a teapot"
    transport.close()


@respx.mock
def test_call_tool_retry_exhausted():
    """Test that exhausting all retries on 5xx hits the for...else branch."""
    respx.post(MCP_URL).mock(return_value=httpx.Response(502, text="Bad Gateway"))
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL, max_retries=2)
    transport._initialized = True
    with patch("hyperping._mcp_transport.time.sleep"):
        with pytest.raises(HyperpingAPIError, match="HTTP 502"):
            transport.call_tool("some_tool")
    transport.close()


@respx.mock
def test_call_tool_result_none_after_retry():
    """Test that result=None after successful retry returns None."""
    respx.post(MCP_URL).mock(
        return_value=httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": 1, "result": {"content": []}},
        )
    )
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    result = transport.call_tool("some_tool")
    assert result is None
    transport.close()


@respx.mock
def test_call_tool_empty_text_returns_none():
    """Test that content with empty text returns None (line 183)."""
    respx.post(MCP_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"content": [{"type": "text", "text": ""}]},
            },
        )
    )
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    result = transport.call_tool("some_tool")
    assert result is None
    transport.close()


@respx.mock
def test_call_tool_notification_200_returns_none():
    """Test _send_rpc returns None for notifications with 200 (line 111)."""
    respx.post(MCP_URL).mock(return_value=httpx.Response(200, json={"jsonrpc": "2.0"}))
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    result = transport._send_rpc("notifications/test", is_notification=True)
    assert result is None
    transport.close()

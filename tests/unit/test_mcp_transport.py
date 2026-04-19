"""Tests for the MCP JSON-RPC 2.0 transport layer."""

import json

import httpx
import pytest
import respx

from hyperping._mcp_transport import MCP_URL, McpTransport
from hyperping.exceptions import HyperpingAPIError, HyperpingAuthError


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

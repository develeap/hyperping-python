"""Tests for the async MCP JSON-RPC 2.0 transport layer."""

import asyncio
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


# -- JSON-RPC rate-limit classification (Task 3 / Tests 2, 18, 21, 22) -------


@respx.mock
async def test_jsonrpc_rate_limit_classified_as_rate_limit_error():
    """200 + JSON-RPC code=-32000 with rate-limit message -> HyperpingRateLimitError."""
    respx.post(MCP_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "error": {
                    "code": -32000,
                    "message": 'Hyperping MCP rate limit exceeded for "initialize" '
                    "(5/5 per minute). Retry after 32s.",
                },
            },
        )
    )
    transport = AsyncMcpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    with pytest.raises(HyperpingRateLimitError) as exc_info:
        await transport.call_tool("some_tool")
    assert exc_info.value.retry_after == 32
    assert exc_info.value.status_code == 200
    assert "rate limit" in exc_info.value.message.lower()
    assert exc_info.value.response_body["code"] == -32000
    await transport.close()


@respx.mock
async def test_jsonrpc_rate_limit_without_retry_after_seconds():
    """JSON-RPC rate-limit message without parseable seconds -> retry_after=None."""
    respx.post(MCP_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "error": {
                    "code": -32000,
                    "message": "Hyperping MCP rate limit exceeded. Try again later.",
                },
            },
        )
    )
    transport = AsyncMcpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    with pytest.raises(HyperpingRateLimitError) as exc_info:
        await transport.call_tool("some_tool")
    assert exc_info.value.retry_after is None
    await transport.close()


@respx.mock
async def test_jsonrpc_non_ratelimit_error_still_generic_api_error():
    """Non -32000 JSON-RPC error continues to raise plain HyperpingAPIError."""
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
    transport = AsyncMcpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    with pytest.raises(HyperpingAPIError) as exc_info:
        await transport.call_tool("nonexistent_tool")
    assert not isinstance(exc_info.value, HyperpingRateLimitError)
    await transport.close()


@respx.mock
async def test_jsonrpc_32000_but_not_ratelimit_message_is_generic():
    """code=-32000 without 'rate limit' substring stays a generic HyperpingAPIError."""
    respx.post(MCP_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "error": {"code": -32000, "message": "Some other server error"},
            },
        )
    )
    transport = AsyncMcpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    with pytest.raises(HyperpingAPIError) as exc_info:
        await transport.call_tool("some_tool")
    assert not isinstance(exc_info.value, HyperpingRateLimitError)
    await transport.close()


# -- TOCTOU init race + idempotency (Task 5 / Tests 7, 9) --------------------


@respx.mock
async def test_concurrent_first_call_single_initialize():
    """asyncio.gather of two first call_tool calls triggers exactly one initialize."""
    route = respx.post(MCP_URL).mock(
        side_effect=[
            INIT_RESPONSE,
            NOTIFICATION_ACCEPTED,
            _tool_response({"ok": True}, req_id=2),
            _tool_response({"ok": True}, req_id=3),
        ],
    )
    transport = AsyncMcpTransport(api_key="sk_test", base_url=MCP_URL)
    r1, r2 = await asyncio.gather(
        transport.call_tool("some_tool"),
        transport.call_tool("some_tool"),
    )
    assert r1 == {"ok": True}
    assert r2 == {"ok": True}
    assert route.call_count == 4
    # Inspect bodies to ensure exactly ONE initialize POST. A TOCTOU
    # regression would send two and the total-count check alone wouldn't
    # catch it.
    methods = [json.loads(call.request.content)["method"] for call in route.calls]
    assert methods.count("initialize") == 1, methods
    assert methods.count("notifications/initialized") == 1, methods
    assert methods.count("tools/call") == 2, methods
    await transport.close()


@respx.mock
async def test_initialize_is_idempotent():
    """Calling await transport.initialize() twice does not POST twice."""
    route = respx.post(MCP_URL).mock(
        side_effect=[INIT_RESPONSE, NOTIFICATION_ACCEPTED],
    )
    transport = AsyncMcpTransport(api_key="sk_test", base_url=MCP_URL)
    await transport.initialize()
    count_after_first = route.call_count
    assert count_after_first == 2
    await transport.initialize()  # second call must be a pure no-op
    assert route.call_count == count_after_first, (
        "second initialize() must not issue any HTTP request"
    )
    methods = [json.loads(call.request.content)["method"] for call in route.calls]
    assert methods == ["initialize", "notifications/initialized"]
    await transport.close()


# -- Cool-off latch (Task 7 / Tests 11, 13) ----------------------------------


@respx.mock
async def test_initialize_rate_limit_latches_cooloff(monkeypatch):
    """After a rate-limited initialize, further call_tool calls short-circuit."""
    fake_now = {"t": 1000.0}
    monkeypatch.setattr(
        "hyperping._async_mcp_transport.time.monotonic", lambda: fake_now["t"]
    )

    rl_response = httpx.Response(
        200,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "error": {
                "code": -32000,
                "message": 'Hyperping MCP rate limit exceeded for "initialize" '
                "(5/5 per minute). Retry after 30s.",
            },
        },
    )
    route = respx.post(MCP_URL).mock(return_value=rl_response)

    transport = AsyncMcpTransport(api_key="sk_test", base_url=MCP_URL)
    with pytest.raises(HyperpingRateLimitError):
        await transport.call_tool("some_tool")
    assert route.call_count == 1

    with pytest.raises(HyperpingRateLimitError) as exc_info:
        await transport.call_tool("some_tool")
    assert route.call_count == 1
    assert exc_info.value.retry_after is not None
    assert exc_info.value.retry_after >= 1

    await transport.close()


@respx.mock
async def test_initialize_cooloff_clears_after_deadline(monkeypatch):
    """Once the cool-off elapses, async initialize is attempted again."""
    fake_now = {"t": 1000.0}
    monkeypatch.setattr(
        "hyperping._async_mcp_transport.time.monotonic", lambda: fake_now["t"]
    )

    rl_body = {
        "jsonrpc": "2.0",
        "id": 1,
        "error": {
            "code": -32000,
            "message": "Hyperping MCP rate limit exceeded. Retry after 10s.",
        },
    }

    route = respx.post(MCP_URL).mock(
        side_effect=[
            httpx.Response(200, json=rl_body),
            INIT_RESPONSE,
            NOTIFICATION_ACCEPTED,
            _tool_response({"ok": True}, req_id=2),
        ]
    )

    transport = AsyncMcpTransport(api_key="sk_test", base_url=MCP_URL)
    with pytest.raises(HyperpingRateLimitError):
        await transport.call_tool("some_tool")
    assert route.call_count == 1, "first call_tool must POST initialize exactly once"

    with pytest.raises(HyperpingRateLimitError):
        await transport.call_tool("some_tool")
    assert route.call_count == 1, "latched call_tool must not POST"

    fake_now["t"] += 100.0
    result = await transport.call_tool("some_tool")
    assert result == {"ok": True}
    assert route.call_count == 4, (
        "post-deadline call_tool must POST initialize + notification + tool"
    )
    await transport.close()


# -- Transient retry never catches rate-limit (Task 8 / Test 25) -------------


@respx.mock
async def test_rate_limit_is_not_retried_by_call_tool():
    """call_tool's transient retry loop must NOT retry HyperpingRateLimitError."""
    route = respx.post(MCP_URL).mock(
        return_value=httpx.Response(
            429, text="Rate limited", headers={"retry-after": "5"},
        ),
    )
    transport = AsyncMcpTransport(api_key="sk_test", base_url=MCP_URL, max_retries=3)
    transport._initialized = True
    with pytest.raises(HyperpingRateLimitError):
        await transport.call_tool("some_tool")
    assert route.call_count == 1
    await transport.close()


@respx.mock
async def test_jsonrpc_rate_limit_is_not_retried_by_call_tool():
    """JSON-RPC -32000 rate-limit (HTTP 200) must NOT trigger retries either."""
    route = respx.post(MCP_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "error": {
                    "code": -32000,
                    "message": "Hyperping MCP rate limit exceeded. Retry after 5s.",
                },
            },
        ),
    )
    transport = AsyncMcpTransport(api_key="sk_test", base_url=MCP_URL, max_retries=3)
    transport._initialized = True
    with pytest.raises(HyperpingRateLimitError):
        await transport.call_tool("some_tool")
    assert route.call_count == 1
    await transport.close()


# -- Retry-After parser robustness (MAJOR-7) ---------------------------------


@pytest.mark.parametrize(
    "message, expected",
    [
        ('Hyperping MCP rate limit exceeded. Retry after 32s.', 32),
        ('Rate limit exceeded for "initialize". Retry-After: 30s', 30),
        ('Rate limit exceeded. retry after 30 seconds.', 30),
        ('Rate limit exceeded. RETRY AFTER 7', 7),
        ('Rate limit exceeded. Retry after 0s', 0),
        ('Rate limit exceeded. Retry after 1.5s', 1),
        ('Rate limit exceeded.', None),
        ('Rate limit exceeded. Try again later.', None),
    ],
)
@respx.mock
async def test_jsonrpc_rate_limit_retry_after_parser_variants(message, expected):
    respx.post(MCP_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "error": {"code": -32000, "message": message},
            },
        )
    )
    transport = AsyncMcpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    with pytest.raises(HyperpingRateLimitError) as exc_info:
        await transport.call_tool("some_tool")
    assert exc_info.value.retry_after == expected
    await transport.close()


@respx.mock
async def test_jsonrpc_rate_limit_marker_requires_exceeded():
    """A -32000 mentioning 'rate limit' but not 'exceeded' stays generic."""
    respx.post(MCP_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "error": {
                    "code": -32000,
                    "message": "Bad rate limit configuration in monitor",
                },
            },
        )
    )
    transport = AsyncMcpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    with pytest.raises(HyperpingAPIError) as exc_info:
        await transport.call_tool("some_tool")
    assert not isinstance(exc_info.value, HyperpingRateLimitError)
    await transport.close()


# -- Notification leg rate-limit classified (MAJOR-1) ------------------------


@respx.mock
async def test_notifications_initialized_rate_limit_classified(monkeypatch):
    """A 200 + -32000 on notifications/initialized raises HyperpingRateLimitError."""
    monkeypatch.setattr(
        "hyperping._async_mcp_transport.time.monotonic", lambda: 1000.0
    )
    respx.post(MCP_URL).mock(
        side_effect=[
            INIT_RESPONSE,
            httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32000,
                        "message": "Hyperping MCP rate limit exceeded. Retry after 5s.",
                    },
                },
            ),
        ]
    )
    transport = AsyncMcpTransport(api_key="sk_test", base_url=MCP_URL)
    with pytest.raises(HyperpingRateLimitError) as exc_info:
        await transport.call_tool("some_tool")
    assert exc_info.value.retry_after == 5
    assert exc_info.value.status_code == 200
    assert transport._init_blocked_until > 0
    await transport.close()


# -- Cool-off preserves originating status_code (MAJOR-2) --------------------


@respx.mock
async def test_cooloff_short_circuit_preserves_429_status_code(monkeypatch):
    """A latch armed by HTTP 429 must short-circuit with status_code=429."""
    fake_now = {"t": 1000.0}
    monkeypatch.setattr(
        "hyperping._async_mcp_transport.time.monotonic", lambda: fake_now["t"]
    )
    respx.post(MCP_URL).mock(
        return_value=httpx.Response(
            429,
            text="Too many initializes",
            headers={"retry-after": "30"},
        ),
    )
    transport = AsyncMcpTransport(api_key="sk_test", base_url=MCP_URL)
    with pytest.raises(HyperpingRateLimitError) as e1:
        await transport.call_tool("some_tool")
    assert e1.value.status_code == 429
    with pytest.raises(HyperpingRateLimitError) as e2:
        await transport.call_tool("some_tool")
    assert e2.value.status_code == 429
    await transport.close()


@respx.mock
async def test_cooloff_short_circuit_preserves_200_status_code(monkeypatch):
    """A latch armed by JSON-RPC -32000 short-circuits with status_code=200."""
    fake_now = {"t": 1000.0}
    monkeypatch.setattr(
        "hyperping._async_mcp_transport.time.monotonic", lambda: fake_now["t"]
    )
    respx.post(MCP_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "error": {
                    "code": -32000,
                    "message": "Hyperping MCP rate limit exceeded. Retry after 30s.",
                },
            },
        )
    )
    transport = AsyncMcpTransport(api_key="sk_test", base_url=MCP_URL)
    with pytest.raises(HyperpingRateLimitError) as e1:
        await transport.call_tool("some_tool")
    assert e1.value.status_code == 200
    with pytest.raises(HyperpingRateLimitError) as e2:
        await transport.call_tool("some_tool")
    assert e2.value.status_code == 200
    await transport.close()


# -- math.ceil semantics on cool-off short-circuit (MAJOR-3) -----------------


@respx.mock
async def test_cooloff_short_circuit_uses_math_ceil_not_plus_one(monkeypatch):
    """When server advertises Retry-After: 30, short-circuit returns 30, not 31."""
    fake_now = {"t": 1000.0}
    monkeypatch.setattr(
        "hyperping._async_mcp_transport.time.monotonic", lambda: fake_now["t"]
    )
    respx.post(MCP_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "error": {
                    "code": -32000,
                    "message": "Hyperping MCP rate limit exceeded. Retry after 30s.",
                },
            },
        )
    )
    transport = AsyncMcpTransport(api_key="sk_test", base_url=MCP_URL)
    with pytest.raises(HyperpingRateLimitError):
        await transport.call_tool("some_tool")
    with pytest.raises(HyperpingRateLimitError) as exc_info:
        await transport.call_tool("some_tool")
    assert exc_info.value.retry_after == 30, (
        f"expected exactly 30 (math.ceil), got {exc_info.value.retry_after}"
    )
    fake_now["t"] += 0.6
    with pytest.raises(HyperpingRateLimitError) as exc_info:
        await transport.call_tool("some_tool")
    assert exc_info.value.retry_after == 30
    fake_now["t"] += 29.0
    with pytest.raises(HyperpingRateLimitError) as exc_info:
        await transport.call_tool("some_tool")
    assert exc_info.value.retry_after == 1
    await transport.close()


# -- retry_after=0 means "no latch" (MINOR-2) --------------------------------


@respx.mock
async def test_jsonrpc_rate_limit_with_retry_after_zero_does_not_latch(monkeypatch):
    """retry_after=0 from server means retry-now; do not set a 30s default."""
    fake_now = {"t": 1000.0}
    monkeypatch.setattr(
        "hyperping._async_mcp_transport.time.monotonic", lambda: fake_now["t"]
    )
    respx.post(MCP_URL).mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "error": {
                        "code": -32000,
                        "message": "Hyperping MCP rate limit exceeded. Retry after 0s.",
                    },
                },
            ),
            INIT_RESPONSE,
            NOTIFICATION_ACCEPTED,
            _tool_response({"ok": True}, req_id=2),
        ]
    )
    transport = AsyncMcpTransport(api_key="sk_test", base_url=MCP_URL)
    with pytest.raises(HyperpingRateLimitError):
        await transport.call_tool("some_tool")
    assert transport._init_blocked_until <= fake_now["t"]
    result = await transport.call_tool("some_tool")
    assert result == {"ok": True}
    await transport.close()

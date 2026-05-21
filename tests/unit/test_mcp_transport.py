"""Tests for the MCP JSON-RPC 2.0 transport layer."""

import json
import threading
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


# -- JSON-RPC rate-limit classification (Task 2 / Tests 1, 17, 19, 20) --------


@respx.mock
def test_jsonrpc_rate_limit_classified_as_rate_limit_error():
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
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True  # bypass handshake to exercise _send_rpc directly
    with pytest.raises(HyperpingRateLimitError) as exc_info:
        transport.call_tool("some_tool")
    assert exc_info.value.retry_after == 32
    assert exc_info.value.status_code == 200
    assert "rate limit" in exc_info.value.message.lower()
    assert exc_info.value.response_body["code"] == -32000
    transport.close()


@respx.mock
def test_jsonrpc_rate_limit_without_retry_after_seconds():
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
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    with pytest.raises(HyperpingRateLimitError) as exc_info:
        transport.call_tool("some_tool")
    assert exc_info.value.retry_after is None
    transport.close()


@respx.mock
def test_jsonrpc_non_ratelimit_error_still_generic_api_error():
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
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    with pytest.raises(HyperpingAPIError) as exc_info:
        transport.call_tool("nonexistent_tool")
    assert not isinstance(exc_info.value, HyperpingRateLimitError)
    transport.close()


@respx.mock
def test_jsonrpc_32000_but_not_ratelimit_message_is_generic():
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
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    with pytest.raises(HyperpingAPIError) as exc_info:
        transport.call_tool("some_tool")
    assert not isinstance(exc_info.value, HyperpingRateLimitError)
    transport.close()


# -- TOCTOU init race + idempotency (Task 4 / Tests 6, 8) --------------------


@respx.mock
def test_concurrent_first_call_single_initialize():
    """Two concurrent first-callers must trigger exactly one initialize POST.

    respx's side_effect serializes responses by call order; the two tool
    replies are interchangeable (both ``{"ok": True}``) so any ordering
    between the two threads is acceptable.
    """
    init_route = respx.post(MCP_URL).mock(
        side_effect=[
            httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-03-26"}},
            ),
            httpx.Response(202),  # notifications/initialized
            httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "result": {"content": [{"type": "text", "text": json.dumps({"ok": True})}]},
                },
            ),
            httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": 3,
                    "result": {"content": [{"type": "text", "text": json.dumps({"ok": True})}]},
                },
            ),
        ]
    )
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    barrier = threading.Barrier(2)
    results: list[object] = []
    errors: list[BaseException] = []

    def hit() -> None:
        barrier.wait()
        try:
            results.append(transport.call_tool("some_tool"))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    t1 = threading.Thread(target=hit)
    t2 = threading.Thread(target=hit)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert errors == [], f"unexpected errors from threads: {errors!r}"
    # Expected: exactly 4 POSTs total -- one initialize, one notification, two tool calls.
    assert init_route.call_count == 4
    # Inspect bodies to ensure exactly ONE was the initialize handshake. A
    # regression that fired two "initialize" POSTs and skipped the notification
    # would still total 4, so the count alone is not sufficient evidence that
    # the TOCTOU race is closed.
    methods = [json.loads(call.request.content)["method"] for call in init_route.calls]
    assert methods.count("initialize") == 1, methods
    assert methods.count("notifications/initialized") == 1, methods
    assert methods.count("tools/call") == 2, methods
    assert results == [{"ok": True}, {"ok": True}]
    transport.close()


@respx.mock
def test_initialize_is_idempotent():
    """Calling initialize() twice does not POST twice."""
    route = respx.post(MCP_URL).mock(
        side_effect=[
            httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-03-26"}},
            ),
            httpx.Response(202),
        ]
    )
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    transport.initialize()
    count_after_first = route.call_count
    assert count_after_first == 2  # initialize + notification
    transport.initialize()  # second call must be a pure no-op
    assert route.call_count == count_after_first, (
        "second initialize() must not issue any HTTP request"
    )
    # And the request methods are exactly what we expect, in order.
    methods = [json.loads(call.request.content)["method"] for call in route.calls]
    assert methods == ["initialize", "notifications/initialized"]
    transport.close()


# -- Cool-off latch (Task 6 / Tests 10, 12) ----------------------------------


@respx.mock
def test_initialize_rate_limit_latches_cooloff(monkeypatch):
    """After a rate-limited initialize, further call_tool calls short-circuit."""
    fake_now = {"t": 1000.0}
    monkeypatch.setattr(
        "hyperping._mcp_transport.time.monotonic", lambda: fake_now["t"]
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

    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    with pytest.raises(HyperpingRateLimitError):
        transport.call_tool("some_tool")  # triggers initialize, gets latched
    assert route.call_count == 1  # only the initialize POST was made

    # Subsequent call_tool must not hit the network.
    with pytest.raises(HyperpingRateLimitError) as exc_info:
        transport.call_tool("some_tool")
    assert route.call_count == 1  # still 1 -- no further HTTP requests
    assert exc_info.value.retry_after is not None
    assert exc_info.value.retry_after >= 1

    transport.close()


@respx.mock
def test_initialize_cooloff_clears_after_deadline(monkeypatch):
    """Once the cool-off elapses, initialize is attempted again."""
    fake_now = {"t": 1000.0}
    monkeypatch.setattr(
        "hyperping._mcp_transport.time.monotonic", lambda: fake_now["t"]
    )

    rl_body = {
        "jsonrpc": "2.0",
        "id": 1,
        "error": {
            "code": -32000,
            "message": "Hyperping MCP rate limit exceeded. Retry after 10s.",
        },
    }
    ok_init = httpx.Response(
        200,
        json={"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-03-26"}},
    )
    ok_tool = httpx.Response(
        200,
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "result": {"content": [{"type": "text", "text": json.dumps({"ok": True})}]},
        },
    )

    route = respx.post(MCP_URL).mock(
        side_effect=[
            httpx.Response(200, json=rl_body),  # first initialize: rate-limited
            ok_init,  # second initialize: success
            httpx.Response(202),  # notifications/initialized
            ok_tool,  # tool call
        ]
    )

    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    with pytest.raises(HyperpingRateLimitError):
        transport.call_tool("some_tool")
    assert route.call_count == 1, "first call_tool must POST initialize exactly once"

    # Still latched: zero further HTTP traffic until the cool-off elapses.
    with pytest.raises(HyperpingRateLimitError):
        transport.call_tool("some_tool")
    assert route.call_count == 1, "latched call_tool must not POST"

    # Advance past the deadline. Now initialize + notification + tool call fire.
    fake_now["t"] += 100.0
    result = transport.call_tool("some_tool")
    assert result == {"ok": True}
    assert route.call_count == 4, (
        "post-deadline call_tool must POST initialize + notification + tool"
    )
    transport.close()


# -- Transient retry never catches rate-limit (Task 8 / Tests 23, 24) --------


@respx.mock
def test_rate_limit_is_not_retried_by_call_tool():
    """call_tool's transient retry loop must NOT retry HyperpingRateLimitError."""
    route = respx.post(MCP_URL).mock(
        return_value=httpx.Response(
            429, text="Rate limited", headers={"retry-after": "5"},
        ),
    )
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL, max_retries=3)
    transport._initialized = True
    with pytest.raises(HyperpingRateLimitError):
        transport.call_tool("some_tool")
    assert route.call_count == 1  # NOT 4 -- no retry attempts
    transport.close()


@respx.mock
def test_jsonrpc_rate_limit_is_not_retried_by_call_tool():
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
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL, max_retries=3)
    transport._initialized = True
    with pytest.raises(HyperpingRateLimitError):
        transport.call_tool("some_tool")
    assert route.call_count == 1
    transport.close()


# -- User repro: six fresh clients (Test 3) ----------------------------------


@respx.mock
def test_six_fresh_clients_under_jsonrpc_rate_limit_all_fail_typed():
    """User's paste-ready repro: every iteration raises typed rate-limit error."""
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
    captured: list[HyperpingRateLimitError] = []
    for _ in range(6):
        transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
        try:
            transport.call_tool("list_monitors", {"status": "ssl_expiring"})
        except HyperpingRateLimitError as exc:
            captured.append(exc)
        finally:
            transport.close()
    assert len(captured) == 6
    for exc in captured:
        assert exc.retry_after == 32
        assert exc.status_code == 200


# -- Retry-After parser robustness (MAJOR-7) ---------------------------------


@pytest.mark.parametrize(
    "message, expected",
    [
        ('Hyperping MCP rate limit exceeded. Retry after 32s.', 32),
        ('Rate limit exceeded for "initialize". Retry-After: 30s', 30),
        ('Rate limit exceeded. retry after 30 seconds.', 30),
        ('Rate limit exceeded. RETRY AFTER 7', 7),
        ('Rate limit exceeded. Retry after 0s', 0),
        ('Rate limit exceeded. Retry after 1.5s', 1),  # sub-second floored
        ('Rate limit exceeded.', None),  # no advertised value
        ('Rate limit exceeded. Try again later.', None),  # graceful
    ],
)
@respx.mock
def test_jsonrpc_rate_limit_retry_after_parser_variants(message, expected):
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
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    with pytest.raises(HyperpingRateLimitError) as exc_info:
        transport.call_tool("some_tool")
    assert exc_info.value.retry_after == expected
    transport.close()


# -- Marker tightness: "rate limit" without "exceeded" is NOT a rate-limit ---


@respx.mock
def test_jsonrpc_rate_limit_marker_requires_exceeded():
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
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    with pytest.raises(HyperpingAPIError) as exc_info:
        transport.call_tool("some_tool")
    assert not isinstance(exc_info.value, HyperpingRateLimitError)
    transport.close()


# -- Notification leg rate-limit classified (MAJOR-1) ------------------------


@respx.mock
def test_notifications_initialized_rate_limit_classified(monkeypatch):
    """A 200 + -32000 on notifications/initialized raises HyperpingRateLimitError."""
    monkeypatch.setattr(
        "hyperping._mcp_transport.time.monotonic", lambda: 1000.0
    )
    respx.post(MCP_URL).mock(
        side_effect=[
            # initialize succeeds
            httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-03-26"}},
            ),
            # notification gets rate-limited via JSON-RPC error
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
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    with pytest.raises(HyperpingRateLimitError) as exc_info:
        transport.call_tool("some_tool")
    assert exc_info.value.retry_after == 5
    assert exc_info.value.status_code == 200
    # The latch must be armed by the second-leg failure, so the next
    # call_tool short-circuits without HTTP traffic.
    assert transport._init_blocked_until > 0
    transport.close()


# -- Cool-off preserves originating status_code (MAJOR-2) --------------------


@respx.mock
def test_cooloff_short_circuit_preserves_429_status_code(monkeypatch):
    """A latch armed by HTTP 429 must short-circuit with status_code=429."""
    fake_now = {"t": 1000.0}
    monkeypatch.setattr(
        "hyperping._mcp_transport.time.monotonic", lambda: fake_now["t"]
    )
    respx.post(MCP_URL).mock(
        return_value=httpx.Response(
            429,
            text="Too many initializes",
            headers={"retry-after": "30"},
        ),
    )
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    with pytest.raises(HyperpingRateLimitError) as e1:
        transport.call_tool("some_tool")
    assert e1.value.status_code == 429
    # Second call within the window: short-circuit must preserve status_code=429.
    with pytest.raises(HyperpingRateLimitError) as e2:
        transport.call_tool("some_tool")
    assert e2.value.status_code == 429
    transport.close()


@respx.mock
def test_cooloff_short_circuit_preserves_200_status_code(monkeypatch):
    """A latch armed by JSON-RPC -32000 short-circuits with status_code=200."""
    fake_now = {"t": 1000.0}
    monkeypatch.setattr(
        "hyperping._mcp_transport.time.monotonic", lambda: fake_now["t"]
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
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    with pytest.raises(HyperpingRateLimitError) as e1:
        transport.call_tool("some_tool")
    assert e1.value.status_code == 200
    with pytest.raises(HyperpingRateLimitError) as e2:
        transport.call_tool("some_tool")
    assert e2.value.status_code == 200
    transport.close()


# -- math.ceil semantics on cool-off short-circuit (MAJOR-3) -----------------


@respx.mock
def test_cooloff_short_circuit_uses_math_ceil_not_plus_one(monkeypatch):
    """When server advertises Retry-After: 30, short-circuit returns 30, not 31."""
    fake_now = {"t": 1000.0}
    monkeypatch.setattr(
        "hyperping._mcp_transport.time.monotonic", lambda: fake_now["t"]
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
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    with pytest.raises(HyperpingRateLimitError):
        transport.call_tool("some_tool")  # arms latch with wait=30
    # Same monotonic moment: remaining is exactly 30.0 -> ceil(30.0) == 30.
    with pytest.raises(HyperpingRateLimitError) as exc_info:
        transport.call_tool("some_tool")
    assert exc_info.value.retry_after == 30, (
        f"expected exactly 30 (math.ceil), got {exc_info.value.retry_after}"
    )
    # Advance a fractional amount: remaining = 29.4 -> ceil = 30.
    fake_now["t"] += 0.6
    with pytest.raises(HyperpingRateLimitError) as exc_info:
        transport.call_tool("some_tool")
    assert exc_info.value.retry_after == 30
    # Advance to within 1s of the deadline: remaining = 0.4 -> ceil = 1.
    fake_now["t"] += 29.0
    with pytest.raises(HyperpingRateLimitError) as exc_info:
        transport.call_tool("some_tool")
    assert exc_info.value.retry_after == 1
    transport.close()


# -- retry_after=0 means "no latch" (MINOR-2) --------------------------------


@respx.mock
def test_jsonrpc_rate_limit_with_retry_after_zero_does_not_latch(monkeypatch):
    """retry_after=0 from server means retry-now; do not set a 30s default."""
    fake_now = {"t": 1000.0}
    monkeypatch.setattr(
        "hyperping._mcp_transport.time.monotonic", lambda: fake_now["t"]
    )
    ok_init = httpx.Response(
        200,
        json={"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-03-26"}},
    )
    ok_tool = httpx.Response(
        200,
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "result": {"content": [{"type": "text", "text": json.dumps({"ok": True})}]},
        },
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
            ok_init,
            httpx.Response(202),
            ok_tool,
        ]
    )
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    with pytest.raises(HyperpingRateLimitError):
        transport.call_tool("some_tool")
    # Latch deadline equals "now" so the next call is permitted immediately.
    assert transport._init_blocked_until <= fake_now["t"]
    result = transport.call_tool("some_tool")
    assert result == {"ok": True}
    transport.close()

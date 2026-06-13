"""Security tests for exception redaction.

Audit findings:
- ``HyperpingAPIError.response_body`` is attached to exceptions for any 4xx
  (except 401/403) and ends up in tracebacks / ``logging.exception()`` logs.
  Sensitive server-echoed content (Authorization headers, subscriber emails,
  webhook URLs) must not leak through the exception surface.
- The MCP transport stores up to 500 bytes of raw server response on 429
  with the same exposure path.
- Error messages may also carry untrusted bytes; they must be control-byte-
  stripped and length-capped before being formatted into ``str(err)``.
"""

from __future__ import annotations

import httpx
import respx

from hyperping.client import HyperpingClient, RetryConfig
from hyperping.endpoints import API_BASE
from hyperping.exceptions import HyperpingAPIError, HyperpingRateLimitError


def test_response_body_does_not_leak_secrets_via_str() -> None:
    """``str(err)`` must redact sensitive keys carried in ``response_body``."""
    err = HyperpingAPIError(
        message="API error: bad request",
        status_code=400,
        response_body={"echo": {"Authorization": "Bearer sk_secret_abc"}},
    )
    rendered = str(err)
    assert "sk_secret_abc" not in rendered
    assert "Bearer" not in rendered or "REDACTED" in rendered


def test_response_body_redacts_nested_sensitive_keys() -> None:
    """Sensitive keys nested arbitrarily deep must be redacted at assignment time."""
    err = HyperpingAPIError(
        message="API error",
        status_code=500,
        response_body={
            "outer": {
                "middle": {
                    "authorization": "Bearer sk_secret_xyz",
                    "subscriber_email": "victim@example.com",
                }
            }
        },
    )
    assert "sk_secret_xyz" not in repr(err.response_body)
    assert "sk_secret_xyz" not in str(err)
    assert "victim@example.com" not in repr(err.response_body)


def test_error_message_strips_control_bytes_and_truncates() -> None:
    """Error messages with ANSI escapes / long payloads must be sanitised in str()."""
    nasty = "\x1b[31mboom\x1b[0m" + ("A" * 2000)
    err = HyperpingAPIError(message=nasty, status_code=400)
    rendered = str(err)
    assert "\x1b" not in rendered
    # Cap at 256 chars for the embedded message portion. Allow the
    # status_code prefix on top.
    assert len(rendered) <= 320


def test_rate_limit_error_does_not_expose_raw_mcp_body() -> None:
    """MCP 429 path: secret embedded in the raw body must not show up via str()/body."""
    err = HyperpingRateLimitError(
        "Rate limit exceeded",
        status_code=429,
        response_body={"echo": "Bearer sk_secret_rl"},
        retry_after=30,
    )
    assert "sk_secret_rl" not in str(err)
    # response_body is still accessible as a structured property, but its
    # sensitive payload must be redacted.
    assert "sk_secret_rl" not in repr(err.response_body)


def test_redactor_bounds_recursion_depth() -> None:
    """A pathologically deep payload must not blow the recursion limit.

    A malicious / malformed server could return JSON with thousands of
    nested levels; the redactor used to recurse without a cap, which raised
    ``RecursionError`` inside ``HyperpingAPIError.__init__`` and masked the
    real HTTP failure. With a depth cap the call returns cleanly and the
    over-deep subtree is replaced with a sentinel marker.
    """
    from hyperping._internals import redact_response_body

    deep: dict = {}
    cursor = deep
    for _ in range(5000):
        cursor["n"] = {}
        cursor = cursor["n"]
    cursor["leaf"] = "ok"

    # Must not raise RecursionError.
    redacted = redact_response_body(deep)

    # Walk down the redacted structure; at some bounded depth we should hit
    # a sentinel rather than a dict.
    saw_truncation = False
    walker: object = redacted
    for _ in range(5000):
        if isinstance(walker, dict) and walker.get("_truncated"):
            saw_truncation = True
            break
        if not isinstance(walker, dict) or "n" not in walker:
            break
        walker = walker["n"]
    assert saw_truncation, "expected a depth-cap sentinel in the redacted output"


def test_exception_with_deep_response_body_constructs_cleanly() -> None:
    """``HyperpingAPIError`` must not raise when fed a 5000-deep response body."""
    deep: dict = {}
    cursor = deep
    for _ in range(5000):
        cursor["n"] = {}
        cursor = cursor["n"]

    # Must not raise RecursionError.
    err = HyperpingAPIError(
        message="API error",
        status_code=500,
        response_body=deep,
    )
    # The structured body is still present (just truncated at some depth).
    assert err.response_body is not None


@respx.mock
def test_mcp_transport_5xx_does_not_leak_raw_server_body() -> None:
    """Non-200/429 MCP error paths must not embed the raw response text.

    The 429 path already drops the body, but the generic 5xx branch and the
    non-JSON 200 branch used to ship ``{"raw": resp.text[:500]}`` straight
    into the exception, which could carry subscriber emails or webhook URLs
    in stack traces. Drop the raw key on those paths too.
    """
    from hyperping._mcp_transport import MCP_URL, McpTransport

    respx.post(MCP_URL).mock(
        return_value=httpx.Response(
            500,
            text='{"echo":{"subscriber_email":"victim@example.com"},"hint":"Bearer sk_secret_mcp"}',
        )
    )
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    try:
        try:
            transport.call_tool("noop")
        except HyperpingAPIError as err:
            assert err.response_body in (None, {}), (
                f"raw body must be dropped, got {err.response_body!r}"
            )
            assert "victim@example.com" not in str(err)
            assert "sk_secret_mcp" not in str(err)
        else:
            raise AssertionError("expected HyperpingAPIError")
    finally:
        transport.close()


@respx.mock
def test_mcp_transport_non_json_200_does_not_leak_raw_server_body() -> None:
    """An HTTP 200 with a non-JSON body must not leak that body via the exception."""
    from hyperping._mcp_transport import MCP_URL, McpTransport

    respx.post(MCP_URL).mock(
        return_value=httpx.Response(
            200,
            text="<html>victim@example.com Bearer sk_secret_mcp2</html>",
        )
    )
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    try:
        try:
            transport.call_tool("noop")
        except HyperpingAPIError as err:
            assert err.response_body in (None, {}), (
                f"raw body must be dropped, got {err.response_body!r}"
            )
            assert "victim@example.com" not in str(err)
            assert "sk_secret_mcp2" not in str(err)
        else:
            raise AssertionError("expected HyperpingAPIError")
    finally:
        transport.close()


@respx.mock
def test_mcp_transport_invalid_tool_json_does_not_leak_raw_text() -> None:
    """The tool-response JSON parse failure must drop the raw text snippet."""
    from hyperping._mcp_transport import MCP_URL, McpTransport

    leak = "victim@example.com Bearer sk_secret_mcp3 {{{"
    respx.post(MCP_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"content": [{"type": "text", "text": leak}]},
            },
        )
    )
    transport = McpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    try:
        try:
            transport.call_tool("noop")
        except HyperpingAPIError as err:
            assert err.response_body in (None, {}), (
                f"raw text must be dropped, got {err.response_body!r}"
            )
            assert "victim@example.com" not in str(err)
            assert "sk_secret_mcp3" not in str(err)
        else:
            raise AssertionError("expected HyperpingAPIError")
    finally:
        transport.close()


@respx.mock
async def test_async_mcp_transport_5xx_does_not_leak_raw_server_body() -> None:
    """Async MCP transport 5xx path must not leak the raw body either."""
    from hyperping._async_mcp_transport import MCP_URL, AsyncMcpTransport

    respx.post(MCP_URL).mock(
        return_value=httpx.Response(
            500,
            text='{"echo":{"subscriber_email":"victim@example.com"},'
            '"hint":"Bearer sk_secret_amcp"}',
        )
    )
    transport = AsyncMcpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    try:
        try:
            await transport.call_tool("noop")
        except HyperpingAPIError as err:
            assert err.response_body in (None, {}), (
                f"raw body must be dropped, got {err.response_body!r}"
            )
            assert "victim@example.com" not in str(err)
            assert "sk_secret_amcp" not in str(err)
        else:
            raise AssertionError("expected HyperpingAPIError")
    finally:
        await transport.close()


@respx.mock
async def test_async_mcp_transport_non_json_200_does_not_leak_raw_server_body() -> None:
    from hyperping._async_mcp_transport import MCP_URL, AsyncMcpTransport

    respx.post(MCP_URL).mock(
        return_value=httpx.Response(
            200,
            text="<html>victim@example.com Bearer sk_secret_amcp2</html>",
        )
    )
    transport = AsyncMcpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    try:
        try:
            await transport.call_tool("noop")
        except HyperpingAPIError as err:
            assert err.response_body in (None, {}), (
                f"raw body must be dropped, got {err.response_body!r}"
            )
            assert "victim@example.com" not in str(err)
            assert "sk_secret_amcp2" not in str(err)
        else:
            raise AssertionError("expected HyperpingAPIError")
    finally:
        await transport.close()


@respx.mock
async def test_async_mcp_transport_invalid_tool_json_does_not_leak_raw_text() -> None:
    from hyperping._async_mcp_transport import MCP_URL, AsyncMcpTransport

    leak = "victim@example.com Bearer sk_secret_amcp3 {{{"
    respx.post(MCP_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"content": [{"type": "text", "text": leak}]},
            },
        )
    )
    transport = AsyncMcpTransport(api_key="sk_test", base_url=MCP_URL)
    transport._initialized = True
    try:
        try:
            await transport.call_tool("noop")
        except HyperpingAPIError as err:
            assert err.response_body in (None, {}), (
                f"raw text must be dropped, got {err.response_body!r}"
            )
            assert "victim@example.com" not in str(err)
            assert "sk_secret_amcp3" not in str(err)
        else:
            raise AssertionError("expected HyperpingAPIError")
    finally:
        await transport.close()


@respx.mock
def test_rest_client_400_does_not_leak_server_echoed_auth_header() -> None:
    """End-to-end: a 400 with an echoed Authorization header must not leak it."""
    respx.get(f"{API_BASE}/v1/monitors").mock(
        return_value=httpx.Response(
            400,
            json={
                "error": "bad request",
                "echo": {"headers": {"Authorization": "Bearer sk_leaked"}},
            },
        )
    )
    client = HyperpingClient(
        api_key="sk_test",
        base_url=API_BASE,
        retry_config=RetryConfig(max_retries=0),
    )
    try:
        try:
            client.list_monitors()
        except HyperpingAPIError as err:
            assert "sk_leaked" not in str(err)
            assert "sk_leaked" not in repr(err.response_body)
        else:
            raise AssertionError("expected HyperpingAPIError")
    finally:
        client.close()

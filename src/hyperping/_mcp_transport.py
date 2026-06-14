"""JSON-RPC 2.0 transport for the Hyperping MCP server."""

from __future__ import annotations

import json
import math
import re
import threading
import time
from typing import Any

import httpx2 as httpx
from pydantic import SecretStr

from hyperping._internals import validate_base_url
from hyperping._otel import get_tracer, record_error, start_rpc_span
from hyperping._version import __version__
from hyperping.endpoints import MCP_URL
from hyperping.exceptions import (
    HyperpingAPIError,
    HyperpingAuthError,
    HyperpingNotFoundError,
    HyperpingRateLimitError,
    HyperpingValidationError,
)

_PROTOCOL_VERSION = "2025-03-26"

# Tight marker: the server's observed phrasing is "rate limit exceeded ...".
# Bare "rate limit" would risk classifying messages like "rate limit
# configuration invalid" as a rate-limit error.
_MCP_RATE_LIMIT_MARKER = "rate limit exceeded"
# Accept "Retry after Ns", "Retry-After: Ns", "retry after 30 seconds", etc.
# Captures only the integer; sub-second values are floored.
_MCP_RATE_LIMIT_RETRY_AFTER_RE = re.compile(
    r"retry[\s\-]after[:\s]+(\d+)",
    re.IGNORECASE,
)
# Default cool-off when the server fails to advertise one.
_COOLOFF_DEFAULT_SECONDS = 30


class McpTransport:
    """Low-level JSON-RPC 2.0 client for the Hyperping MCP server.

    The MCP server exposes tools not available via the REST API: on-call
    schedules, anomalies, alerts, integrations, probe logs, and more.

    Uses the same Bearer token API key as the REST client.
    """

    def __init__(
        self,
        api_key: str | SecretStr,
        base_url: str = MCP_URL,
        timeout: float = 30.0,
        max_retries: int = 2,
        allow_insecure: bool = False,
    ) -> None:
        token = api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
        self._url = validate_base_url(
            base_url,
            allow_insecure=allow_insecure,
            param_name="base_url",
        )
        self._client = httpx.Client(
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            timeout=timeout,
        )
        self._initialized = False
        self._request_id = 0
        self._lock = threading.Lock()
        # Separate lock for the handshake so request-id increment and the
        # initialize() critical section don't contend.
        self._init_lock = threading.Lock()
        # Monotonic deadline (process-local). 0.0 means no latch.
        self._init_blocked_until: float = 0.0
        # Status code of the original rate-limit response that armed the
        # latch, propagated through short-circuit raises so callers can tell
        # whether they hit HTTP 429 or HTTP 200 + JSON-RPC -32000.
        self._init_blocked_status_code: int = 200
        self._init_result: dict[str, Any] = {}
        self._max_retries = max_retries
        self._tracer = get_tracer()

    def _next_id(self) -> int:
        with self._lock:
            self._request_id += 1
            return self._request_id

    def _send_rpc(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        is_notification: bool = False,
    ) -> dict[str, Any] | None:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        if not is_notification:
            payload["id"] = self._next_id()

        resp = self._client.post(self._url, content=json.dumps(payload))

        if resp.status_code in (401, 403):
            raise HyperpingAuthError("Invalid or expired API key")
        if resp.status_code == 202:
            return None  # Notification accepted
        if resp.status_code == 404:
            raise HyperpingNotFoundError(
                "Resource not found",
                status_code=404,
            )
        if resp.status_code == 429:
            retry_after = None
            raw = resp.headers.get("retry-after")
            if raw:
                try:
                    retry_after = int(raw)
                except ValueError:
                    pass
            # Drop the raw body: the server may echo request fields here, and
            # the structured exception already conveys "Rate limit exceeded"
            # plus retry_after for the caller's back-off logic.
            raise HyperpingRateLimitError(
                "Rate limit exceeded",
                retry_after=retry_after,
                status_code=429,
                response_body=None,
            )
        if resp.status_code in (400, 422):
            raise HyperpingValidationError(
                f"Validation error: HTTP {resp.status_code}",
                status_code=resp.status_code,
            )
        if resp.status_code != 200:
            # Drop the raw body for the same reason as the 429 path: the server
            # may echo subscriber emails, webhook URLs, or other PII in free-
            # form error text that the structured key-based redactor cannot
            # match. The status code in the exception is enough for callers.
            raise HyperpingAPIError(
                f"MCP server returned HTTP {resp.status_code}",
                status_code=resp.status_code,
                response_body=None,
            )

        # HTTP 200. Parse the body so we classify JSON-RPC errors (including
        # rate-limit signals) on notification responses too -- the server can
        # return 200 + JSON-RPC error on a "notifications/initialized" leg.
        try:
            data = resp.json()
        except (json.JSONDecodeError, ValueError):
            if is_notification:
                return None
            raise HyperpingAPIError(
                "MCP server returned 200 with non-JSON body",
                status_code=200,
                response_body=None,
            ) from None

        if isinstance(data, dict) and "error" in data:
            self._raise_for_jsonrpc_error(data["error"], resp.status_code)

        if is_notification:
            return None
        return data  # type: ignore[no-any-return]

    @staticmethod
    def _raise_for_jsonrpc_error(err: Any, status_code: int) -> None:
        """Map a JSON-RPC ``error`` payload to a typed exception and raise it."""
        if (
            isinstance(err, dict)
            and err.get("code") == -32000
            and isinstance(err.get("message"), str)
            and _MCP_RATE_LIMIT_MARKER in err["message"].lower()
        ):
            rl_retry_after: int | None = None
            match = _MCP_RATE_LIMIT_RETRY_AFTER_RE.search(err["message"])
            if match:
                rl_retry_after = int(match.group(1))
            raise HyperpingRateLimitError(
                err["message"],
                retry_after=rl_retry_after,
                status_code=status_code,
                response_body=err if isinstance(err, dict) else None,
            )
        code = err.get("code", "?") if isinstance(err, dict) else "?"
        message = err.get("message", "unknown") if isinstance(err, dict) else str(err)
        raise HyperpingAPIError(
            f"MCP error {code}: {message}",
            status_code=status_code,
            response_body=err if isinstance(err, dict) else None,
        )

    def initialize(self) -> dict[str, Any]:
        """Perform MCP handshake if not yet performed. Idempotent and thread-safe.

        Calling this more than once on the same transport is a no-op after the
        first successful handshake. While an ``initialize`` cool-off latch is
        active, raises :class:`HyperpingRateLimitError` without issuing any
        HTTP request.

        The cool-off latch is per-transport-instance and per-process. It does
        not coordinate across separate Python processes sharing the same API
        key; each process keeps its own latch.
        """
        # Fast path: avoid lock acquisition on every call after the handshake
        # has succeeded. ``_initialized`` is only assigned True under the lock
        # after both legs of the handshake, so a True read here is safe.
        if self._initialized:
            return self._init_result
        with self._init_lock:
            if self._initialized:
                return self._init_result
            return self._initialize_locked()

    def _initialize_locked(self) -> dict[str, Any]:
        """Perform the handshake. Assumes ``self._init_lock`` is held."""
        # ``time.monotonic`` is used deliberately over ``time.time`` so the
        # latch is immune to wall-clock jumps (NTP adjustments, suspend/resume).
        remaining = self._init_blocked_until - time.monotonic()
        if remaining > 0:
            raise HyperpingRateLimitError(
                "MCP initialize rate limit cool-off active; retry later",
                retry_after=max(math.ceil(remaining), 1),
                status_code=self._init_blocked_status_code,
            )
        try:
            result = self._send_rpc(
                "initialize",
                {
                    "protocolVersion": _PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "hyperping-python", "version": __version__},
                },
            )
            self._send_rpc("notifications/initialized", is_notification=True)
        except HyperpingRateLimitError as exc:
            # retry_after=None -> default cool-off; retry_after=0 -> no latch
            # (the server is telling us we may retry immediately); positive
            # values are honoured verbatim.
            if exc.retry_after is None:
                wait = _COOLOFF_DEFAULT_SECONDS
            else:
                wait = max(int(exc.retry_after), 0)
            self._init_blocked_until = time.monotonic() + wait
            self._init_blocked_status_code = exc.status_code or 200
            raise
        self._init_result = result.get("result", {}) if result else {}
        self._init_blocked_until = 0.0
        # Set last so the fast path in initialize() never returns a stale
        # ``_init_result``.
        self._initialized = True
        return self._init_result

    def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        """Call an MCP tool and return parsed response data.

        Auto-initializes on first call. Extracts and parses the JSON
        string from ``result.content[0].text``.

        Retries automatically on transient HTTP server errors (500, 502, 503, 504)
        up to ``max_retries`` times with exponential back-off. Rate-limit errors
        (HTTP 429 or JSON-RPC -32000) are NEVER retried at this layer; they raise
        :class:`HyperpingRateLimitError` immediately so callers can honour
        ``retry_after``.
        """
        self.initialize()

        with start_rpc_span(self._tracer, "tools/call", self._url) as span:
            last_exc: Exception | None = None
            for attempt in range(self._max_retries + 1):
                try:
                    result = self._send_rpc(
                        "tools/call",
                        {"name": tool_name, "arguments": arguments or {}},
                    )
                    break
                except HyperpingAPIError as exc:
                    if exc.status_code and exc.status_code in (500, 502, 503, 504):
                        last_exc = exc
                        if attempt < self._max_retries:
                            time.sleep(min(2**attempt, 10))
                            continue
                    record_error(span, exc)
                    raise
            else:
                if last_exc is not None:
                    record_error(span, last_exc)
                raise last_exc  # type: ignore[misc]

            if result is None:
                return None

            content = result.get("result", {}).get("content", [])
            if not content:
                return None

            text = content[0].get("text", "")
            if not text:
                return None

            try:
                return json.loads(text)
            except json.JSONDecodeError as exc:
                # Server-controlled ``text`` may carry PII; drop it instead of
                # embedding the first 500 bytes into the exception.
                raise HyperpingAPIError(
                    f"Failed to parse MCP tool response: {exc}",
                    status_code=200,
                    response_body=None,
                ) from exc

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> McpTransport:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

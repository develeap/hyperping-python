"""Async JSON-RPC 2.0 transport for the Hyperping MCP server."""

from __future__ import annotations

import asyncio
import json
import math
import re
import time
from typing import Any

import httpx
from pydantic import SecretStr

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


class AsyncMcpTransport:
    """Async low-level JSON-RPC 2.0 client for the Hyperping MCP server.

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
    ) -> None:
        token = api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
        self._url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            timeout=timeout,
        )
        self._initialized = False
        self._request_id = 0
        self._lock = asyncio.Lock()
        # Separate lock for the handshake so request-id increment and the
        # initialize() critical section don't contend.
        self._init_lock = asyncio.Lock()
        # Monotonic deadline (process-local). 0.0 means no latch.
        self._init_blocked_until: float = 0.0
        # Status code of the original rate-limit response that armed the
        # latch, propagated through short-circuit raises so callers can tell
        # whether they hit HTTP 429 or HTTP 200 + JSON-RPC -32000.
        self._init_blocked_status_code: int = 200
        self._init_result: dict[str, Any] = {}
        self._max_retries = max_retries

    async def _next_id(self) -> int:
        async with self._lock:
            self._request_id += 1
            return self._request_id

    async def _send_rpc(
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
            payload["id"] = await self._next_id()

        resp = await self._client.post(self._url, content=json.dumps(payload))

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
            raw_retry = resp.headers.get("retry-after")
            if raw_retry:
                try:
                    retry_after = int(raw_retry)
                except ValueError:
                    pass
            raise HyperpingRateLimitError(
                "Rate limit exceeded",
                retry_after=retry_after,
                status_code=429,
                response_body={"raw": resp.text[:500]},
            )
        if resp.status_code in (400, 422):
            raise HyperpingValidationError(
                f"Validation error: HTTP {resp.status_code}",
                status_code=resp.status_code,
            )
        if resp.status_code != 200:
            raise HyperpingAPIError(
                f"MCP server returned HTTP {resp.status_code}",
                status_code=resp.status_code,
                response_body={"raw": resp.text[:500]},
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
                response_body={"raw": resp.text[:500]},
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

    async def initialize(self) -> dict[str, Any]:
        """Async idempotent and concurrency-safe MCP handshake.

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
        async with self._init_lock:
            if self._initialized:
                return self._init_result
            return await self._initialize_locked()

    async def _initialize_locked(self) -> dict[str, Any]:
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
            result = await self._send_rpc(
                "initialize",
                {
                    "protocolVersion": _PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "hyperping-python", "version": __version__},
                },
            )
            await self._send_rpc("notifications/initialized", is_notification=True)
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

    async def call_tool(
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
        await self.initialize()

        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                result = await self._send_rpc(
                    "tools/call",
                    {"name": tool_name, "arguments": arguments or {}},
                )
                break
            except HyperpingAPIError as exc:
                if exc.status_code and exc.status_code in (500, 502, 503, 504):
                    last_exc = exc
                    if attempt < self._max_retries:
                        await asyncio.sleep(min(2**attempt, 10))
                        continue
                raise
        else:
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
            raise HyperpingAPIError(
                f"Failed to parse MCP tool response: {exc}",
                status_code=200,
                response_body={"raw": text[:500]},
            ) from exc

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> AsyncMcpTransport:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

"""Async JSON-RPC 2.0 transport for the Hyperping MCP server."""

from __future__ import annotations

import asyncio
import json
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
        if is_notification:
            return None

        data = resp.json()
        if "error" in data:
            err = data["error"]
            raise HyperpingAPIError(
                f"MCP error {err.get('code', '?')}: {err.get('message', 'unknown')}",
                status_code=resp.status_code,
                response_body=err,
            )
        return data  # type: ignore[no-any-return]

    async def initialize(self) -> dict[str, Any]:
        """Perform MCP handshake. Called automatically on first tool call."""
        result = await self._send_rpc(
            "initialize",
            {
                "protocolVersion": _PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "hyperping-python", "version": __version__},
            },
        )
        await self._send_rpc("notifications/initialized", is_notification=True)
        async with self._lock:
            self._initialized = True
        return result.get("result", {}) if result else {}

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        """Call an MCP tool and return parsed response data.

        Auto-initializes on first call. Extracts and parses the JSON
        string from ``result.content[0].text``.

        Retries automatically on transient server errors (HTTP 500, 502,
        503, 504) up to ``max_retries`` times with exponential back-off.
        """
        async with self._lock:
            needs_init = not self._initialized
        if needs_init:
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

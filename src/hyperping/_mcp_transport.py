"""JSON-RPC 2.0 transport for the Hyperping MCP server."""

from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import SecretStr

from hyperping._version import __version__
from hyperping.endpoints import MCP_URL
from hyperping.exceptions import HyperpingAPIError, HyperpingAuthError

_PROTOCOL_VERSION = "2025-03-26"


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
    ) -> None:
        token = api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
        self._url = base_url.rstrip("/")
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

    def _next_id(self) -> int:
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

    def initialize(self) -> dict[str, Any]:
        """Perform MCP handshake. Called automatically on first tool call."""
        result = self._send_rpc(
            "initialize",
            {
                "protocolVersion": _PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "hyperping-python", "version": __version__},
            },
        )
        self._send_rpc("notifications/initialized", is_notification=True)
        self._initialized = True
        return result.get("result", {}) if result else {}

    def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        """Call an MCP tool and return parsed response data.

        Auto-initializes on first call. Extracts and parses the JSON
        string from ``result.content[0].text``.
        """
        if not self._initialized:
            self.initialize()

        result = self._send_rpc(
            "tools/call",
            {"name": tool_name, "arguments": arguments or {}},
        )
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

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> McpTransport:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

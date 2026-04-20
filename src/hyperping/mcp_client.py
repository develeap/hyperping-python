"""High-level typed MCP client for the Hyperping MCP server.

Wraps :class:`~hyperping._mcp_transport.McpTransport` with typed convenience
methods that mirror the MCP tool names exposed by the server.

Example::

    from hyperping import HyperpingMcpClient

    with HyperpingMcpClient(api_key="sk_...") as mcp:
        summary = mcp.get_status_summary()
        schedules = mcp.list_on_call_schedules()
"""

from __future__ import annotations

from typing import Any

from pydantic import SecretStr

from hyperping._mcp_transport import McpTransport
from hyperping.endpoints import MCP_URL


class HyperpingMcpClient:
    """High-level client for Hyperping MCP server tools.

    Provides typed convenience methods for every MCP tool. All methods
    return plain dicts or lists of dicts; callers may validate further
    with Pydantic models if desired.

    Supports the same ``api_key`` formats (``str`` or ``SecretStr``) and
    context-manager pattern as :class:`~hyperping.client.HyperpingClient`.
    """

    def __init__(
        self,
        api_key: str | SecretStr,
        base_url: str = MCP_URL,
        timeout: float = 30.0,
    ) -> None:
        self._transport = McpTransport(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
        )

    # ==================== Internal ====================

    def _call(self, tool: str, args: dict[str, Any] | None = None) -> Any:
        """Call an MCP tool via the transport."""
        return self._transport.call_tool(tool, args or {})

    # ==================== Context Manager ====================

    def close(self) -> None:
        """Close the underlying HTTP transport."""
        self._transport.close()

    def __enter__(self) -> HyperpingMcpClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    # ==================== Status & Reporting ====================

    def get_status_summary(self) -> Any:
        """Get aggregate monitor status counts."""
        return self._call("get_status_summary", {})

    def get_monitor_response_time(
        self,
        monitor_uuid: str,
        **kwargs: Any,
    ) -> Any:
        """Get response time metrics for a monitor.

        Args:
            monitor_uuid: Monitor UUID.
            **kwargs: Additional arguments forwarded to the MCP tool.
        """
        return self._call(
            "get_monitor_response_time",
            {"uuid": monitor_uuid, **kwargs},
        )

    def get_monitor_mtta(
        self,
        monitor_uuid: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Get mean time to acknowledge metrics.

        Args:
            monitor_uuid: Optional monitor UUID to scope the query.
            **kwargs: Additional arguments forwarded to the MCP tool.
        """
        args: dict[str, Any] = {**kwargs}
        if monitor_uuid is not None:
            args["uuid"] = monitor_uuid
        return self._call("get_monitor_mtta", args)

    def get_monitor_mttr(
        self,
        monitor_uuid: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Get mean time to resolve metrics.

        Args:
            monitor_uuid: Optional monitor UUID to scope the query.
            **kwargs: Additional arguments forwarded to the MCP tool.
        """
        args: dict[str, Any] = {**kwargs}
        if monitor_uuid is not None:
            args["uuid"] = monitor_uuid
        return self._call("get_monitor_mttr", args)

    # ==================== Observability ====================

    def get_monitor_anomalies(self, monitor_uuid: str) -> Any:
        """Get anomalies detected for a monitor.

        Args:
            monitor_uuid: Monitor UUID.
        """
        return self._call("get_monitor_anomalies", {"uuid": monitor_uuid})

    def get_monitor_http_logs(
        self,
        monitor_uuid: str,
        **kwargs: Any,
    ) -> Any:
        """Get HTTP probe logs for a monitor.

        Args:
            monitor_uuid: Monitor UUID.
            **kwargs: Additional arguments forwarded to the MCP tool.
        """
        return self._call(
            "get_monitor_http_logs",
            {"uuid": monitor_uuid, **kwargs},
        )

    # ==================== Alerts ====================

    def list_recent_alerts(self, **kwargs: Any) -> Any:
        """List recent alert notifications.

        Args:
            **kwargs: Additional arguments forwarded to the MCP tool.
        """
        return self._call("list_recent_alerts", {**kwargs})

    # ==================== On-Call ====================

    def list_on_call_schedules(self) -> Any:
        """List all on-call schedules."""
        return self._call("list_on_call_schedules", {})

    def get_on_call_schedule(self, uuid: str) -> Any:
        """Get a single on-call schedule by UUID.

        Args:
            uuid: Schedule UUID.
        """
        return self._call("get_on_call_schedule", {"uuid": uuid})

    # ==================== Escalation Policies ====================

    def list_escalation_policies(self) -> Any:
        """List all escalation policies."""
        return self._call("list_escalation_policies", {})

    def get_escalation_policy(self, uuid: str) -> Any:
        """Get a single escalation policy by UUID.

        Args:
            uuid: Escalation policy UUID.
        """
        return self._call("get_escalation_policy", {"uuid": uuid})

    # ==================== Team ====================

    def list_team_members(self) -> Any:
        """List all team members."""
        return self._call("list_team_members", {})

    # ==================== Integrations ====================

    def list_integrations(self) -> Any:
        """List all notification channel integrations."""
        return self._call("list_integrations", {})

    def get_integration(self, uuid: str) -> Any:
        """Get a single integration by UUID.

        Args:
            uuid: Integration UUID.
        """
        return self._call("get_integration", {"uuid": uuid})

    # ==================== Outages ====================

    def get_outage_timeline(self, outage_uuid: str) -> Any:
        """Get the lifecycle timeline for an outage.

        Args:
            outage_uuid: Outage UUID.
        """
        return self._call("get_outage_timeline", {"uuid": outage_uuid})

    # ==================== Monitors ====================

    def search_monitors_by_name(self, query: str) -> Any:
        """Search monitors by name.

        Args:
            query: Search string to match against monitor names.
        """
        return self._call("search_monitors_by_name", {"query": query})

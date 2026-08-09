"""Observability tool registrations for the Hyperping MCP server.

Registers 15 tools: get_status_summary, get_monitor_response_time,
get_monitor_mtta, get_monitor_mttr, get_monitor_anomalies,
get_monitor_http_logs, list_recent_alerts, list_on_call_schedules,
get_on_call_schedule, list_escalation_policies, get_escalation_policy,
list_team_members, list_integrations, get_integration, get_outage_timeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from hyperping.mcp_client import HyperpingMcpClient


def register_observability_tools(mcp: FastMCP, mcp_client: HyperpingMcpClient) -> None:
    """Register observability tools on *mcp*."""

    @mcp.tool()
    def get_status_summary() -> dict[str, Any]:
        """Get aggregate monitor status counts (up, down, paused, total)."""
        return mcp_client.get_status_summary().model_dump()

    @mcp.tool()
    def get_monitor_response_time(monitor_uuid: str) -> dict[str, Any]:
        """Get response time metrics for a monitor."""
        return mcp_client.get_monitor_response_time(monitor_uuid).model_dump()

    @mcp.tool()
    def get_monitor_mtta(monitor_uuid: str | None = None) -> dict[str, Any]:
        """Get mean time to acknowledge metrics. Optionally scoped to a monitor UUID."""
        return mcp_client.get_monitor_mtta(monitor_uuid=monitor_uuid).model_dump()

    @mcp.tool()
    def get_monitor_mttr(monitor_uuid: str | None = None) -> dict[str, Any]:
        """Get mean time to resolve metrics. Optionally scoped to a monitor UUID."""
        return mcp_client.get_monitor_mttr(monitor_uuid=monitor_uuid).model_dump()

    @mcp.tool()
    def get_monitor_anomalies(monitor_uuid: str) -> list[dict[str, Any]]:
        """Get anomalies detected for a monitor."""
        return [a.model_dump() for a in mcp_client.get_monitor_anomalies(monitor_uuid)]

    @mcp.tool()
    def get_monitor_http_logs(monitor_uuid: str) -> dict[str, Any]:
        """Get HTTP probe logs for a monitor."""
        return mcp_client.get_monitor_http_logs(monitor_uuid).model_dump()

    @mcp.tool()
    def list_recent_alerts() -> dict[str, Any]:
        """List recent alert notifications."""
        return mcp_client.list_recent_alerts().model_dump()

    @mcp.tool()
    def list_on_call_schedules() -> list[dict[str, Any]]:
        """List all on-call schedules."""
        return [s.model_dump() for s in mcp_client.list_on_call_schedules()]

    @mcp.tool()
    def get_on_call_schedule(uuid: str) -> dict[str, Any]:
        """Get a single on-call schedule by UUID."""
        return mcp_client.get_on_call_schedule(uuid).model_dump()

    @mcp.tool()
    def list_escalation_policies() -> list[dict[str, Any]]:
        """List all escalation policies."""
        return [p.model_dump() for p in mcp_client.list_escalation_policies()]

    @mcp.tool()
    def get_escalation_policy(uuid: str) -> dict[str, Any]:
        """Get a single escalation policy by UUID."""
        return mcp_client.get_escalation_policy(uuid).model_dump()

    @mcp.tool()
    def list_team_members() -> list[dict[str, Any]]:
        """List all team members."""
        return [m.model_dump() for m in mcp_client.list_team_members()]

    @mcp.tool()
    def list_integrations() -> list[dict[str, Any]]:
        """List all notification channel integrations."""
        return [i.model_dump() for i in mcp_client.list_integrations()]

    @mcp.tool()
    def get_integration(uuid: str) -> dict[str, Any]:
        """Get a single integration by UUID."""
        return mcp_client.get_integration(uuid).model_dump()

    @mcp.tool()
    def get_outage_timeline(outage_uuid: str) -> dict[str, Any]:
        """Get the lifecycle timeline for an outage."""
        return mcp_client.get_outage_timeline(outage_uuid).model_dump()

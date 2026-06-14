"""Maintenance window tool registrations for the Hyperping MCP server.

Registers 7 tools: list_maintenance, get_maintenance, create_maintenance,
update_maintenance, delete_maintenance, get_active_maintenance,
is_monitor_in_maintenance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from hyperping.client import HyperpingClient


def register_maintenance_tools(mcp: FastMCP, client: HyperpingClient) -> None:
    """Register maintenance window tools on *mcp*."""

    @mcp.tool()
    def list_maintenance(status: str | None = None) -> list[dict[str, Any]]:
        """List maintenance windows. Filter by status: scheduled, in_progress, completed."""
        return [m.model_dump() for m in client.list_maintenance(status=status)]

    @mcp.tool()
    def get_maintenance(maintenance_id: str) -> dict[str, Any]:
        """Get a single maintenance window by UUID."""
        return client.get_maintenance(maintenance_id).model_dump()

    @mcp.tool()
    def create_maintenance(
        name: str,
        start_date: str,
        end_date: str,
        monitors: list[str],
        statuspages: list[str] | None = None,
        title: dict[str, Any] | None = None,
        text: dict[str, Any] | None = None,
        notification_option: str | None = None,
        notification_minutes: int | None = None,
    ) -> dict[str, Any]:
        """This will create a new maintenance window. title/text are LocalizedText dicts."""
        from hyperping.models import LocalizedText, MaintenanceCreate

        fields: dict[str, Any] = {
            "name": name,
            "start_date": start_date,
            "end_date": end_date,
            "monitors": monitors,
        }
        if statuspages is not None:
            fields["statuspages"] = statuspages
        if title is not None:
            fields["title"] = LocalizedText(**title)
        if text is not None:
            fields["text"] = LocalizedText(**text)
        if notification_option is not None:
            fields["notification_option"] = notification_option
        if notification_minutes is not None:
            fields["notification_minutes"] = notification_minutes
        return client.create_maintenance(MaintenanceCreate(**fields)).model_dump()

    @mcp.tool()
    def update_maintenance(
        maintenance_id: str,
        name: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        monitors: list[str] | None = None,
    ) -> dict[str, Any]:
        """Update an existing maintenance window. Only supplied fields are changed."""
        from hyperping.models import MaintenanceUpdate

        fields: dict[str, Any] = {}
        if name is not None:
            fields["name"] = name
        if start_date is not None:
            fields["start_date"] = start_date
        if end_date is not None:
            fields["end_date"] = end_date
        if monitors is not None:
            fields["monitors"] = monitors
        return client.update_maintenance(maintenance_id, MaintenanceUpdate(**fields)).model_dump()

    @mcp.tool()
    def delete_maintenance(maintenance_id: str) -> dict[str, Any]:
        """This will permanently delete a maintenance window."""
        client.delete_maintenance(maintenance_id)
        return {"success": True}

    @mcp.tool()
    def get_active_maintenance() -> list[dict[str, Any]]:
        """List currently active maintenance windows."""
        return [m.model_dump() for m in client.get_active_maintenance()]

    @mcp.tool()
    def is_monitor_in_maintenance(monitor_uuid: str) -> dict[str, Any]:
        """Check whether a monitor is currently inside an active maintenance window."""
        result = client.is_monitor_in_maintenance(monitor_uuid)
        return {"in_maintenance": result}

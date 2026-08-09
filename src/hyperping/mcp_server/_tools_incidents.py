"""Incident tool registrations for the Hyperping MCP server.

Registers 7 tools: list_incidents, get_incident, create_incident,
update_incident, add_incident_update, resolve_incident, delete_incident.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from hyperping.client import HyperpingClient


def register_incident_tools(mcp: FastMCP, client: HyperpingClient) -> None:
    """Register incident tools on *mcp*."""

    @mcp.tool()
    def list_incidents(status: str | None = None) -> list[dict[str, Any]]:
        """List incidents. Filter by status: investigating, identified, monitoring, resolved."""
        return [i.model_dump() for i in client.list_incidents(status=status)]

    @mcp.tool()
    def get_incident(incident_id: str) -> dict[str, Any]:
        """Get a single incident by UUID."""
        return client.get_incident(incident_id).model_dump()

    @mcp.tool()
    def create_incident(
        title: dict[str, Any],
        text: dict[str, Any],
        statuspages: list[str],
        type: str | None = None,
        affected_components: list[str] | None = None,
        date: str | None = None,
    ) -> dict[str, Any]:
        """This will create a new incident. title/text are LocalizedText dicts with an 'en' key."""
        from hyperping.models import IncidentCreate, LocalizedText

        fields: dict[str, Any] = {
            "title": LocalizedText(**title),
            "text": LocalizedText(**text),
            "statuspages": statuspages,
        }
        if type is not None:
            fields["type"] = type
        if affected_components is not None:
            fields["affected_components"] = affected_components
        if date is not None:
            fields["date"] = date
        return client.create_incident(IncidentCreate(**fields)).model_dump()

    @mcp.tool()
    def update_incident(
        incident_id: str,
        title: dict[str, Any] | None = None,
        type: str | None = None,
        affected_components: list[str] | None = None,
        statuspages: list[str] | None = None,
    ) -> dict[str, Any]:
        """Update an incident. title is a LocalizedText dict with an 'en' key."""
        from hyperping.models import IncidentUpdateRequest, LocalizedText

        fields: dict[str, Any] = {}
        if title is not None:
            fields["title"] = LocalizedText(**title)
        if type is not None:
            fields["type"] = type
        if affected_components is not None:
            fields["affected_components"] = affected_components
        if statuspages is not None:
            fields["statuspages"] = statuspages
        return client.update_incident(incident_id, IncidentUpdateRequest(**fields)).model_dump()

    @mcp.tool()
    def add_incident_update(
        incident_id: str,
        text: dict[str, Any],
        type: str,
        date: str,
    ) -> dict[str, Any]:
        """Add an update to an incident. text is a LocalizedText dict with 'en' key.
        type: investigating, identified, monitoring, resolved."""
        from hyperping.models import AddIncidentUpdateRequest, LocalizedText

        update = AddIncidentUpdateRequest(
            text=LocalizedText(**text),
            type=type,
            date=date,
        )
        return client.add_incident_update(incident_id, update).model_dump()

    @mcp.tool()
    def resolve_incident(incident_id: str, message: str | None = None) -> dict[str, Any]:
        """This will resolve an incident and post a resolution update."""
        return client.resolve_incident(incident_id, message=message).model_dump()

    @mcp.tool()
    def delete_incident(incident_id: str) -> dict[str, Any]:
        """This will permanently delete an incident."""
        client.delete_incident(incident_id)
        return {"success": True}

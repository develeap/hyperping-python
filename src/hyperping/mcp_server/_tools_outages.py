"""Outage tool registrations for the Hyperping MCP server.

Registers 8 tools: list_outages, get_outage, create_outage,
acknowledge_outage, resolve_outage, escalate_outage,
unacknowledge_outage, delete_outage.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from hyperping._async_client import AsyncHyperpingClient
    from hyperping.client import HyperpingClient


def register_outage_tools(
    mcp: FastMCP,
    client: HyperpingClient | AsyncHyperpingClient,
) -> None:
    """Register outage tools on *mcp*."""
    from hyperping._async_client import AsyncHyperpingClient

    if isinstance(client, AsyncHyperpingClient):

        @mcp.tool()
        async def list_outages(
            status: str = "all",
            outage_type: str = "all",
        ) -> list[dict[str, Any]]:
            """List outages. status: all, ongoing, resolved. outage_type: all, manual, monitor."""
            return [
                o.model_dump()
                for o in await client.list_outages(status=status, outage_type=outage_type)
            ]

        @mcp.tool()
        async def get_outage(outage_id: str) -> dict[str, Any]:
            """Get a single outage by UUID."""
            return (await client.get_outage(outage_id)).model_dump()

        @mcp.tool()
        async def create_outage(monitor_uuid: str) -> dict[str, Any]:
            """This will create a manual outage for a monitor."""
            return (await client.create_outage(monitor_uuid)).model_dump()

        @mcp.tool()
        async def acknowledge_outage(outage_id: str, message: str | None = None) -> dict[str, Any]:
            """Acknowledge an outage with an optional message."""
            return (await client.acknowledge_outage(outage_id, message=message)).model_dump()

        @mcp.tool()
        async def resolve_outage(outage_id: str, message: str | None = None) -> dict[str, Any]:
            """This will resolve an outage with an optional message."""
            return (await client.resolve_outage(outage_id, message=message)).model_dump()

        @mcp.tool()
        async def escalate_outage(outage_id: str) -> dict[str, Any]:
            """Escalate an outage to the next on-call tier."""
            return (await client.escalate_outage(outage_id)).model_dump()

        @mcp.tool()
        async def unacknowledge_outage(outage_id: str) -> dict[str, Any]:
            """Unacknowledge an outage."""
            return (await client.unacknowledge_outage(outage_id)).model_dump()

        @mcp.tool()
        async def delete_outage(outage_id: str) -> dict[str, Any]:
            """This will permanently delete an outage record."""
            await client.delete_outage(outage_id)
            return {"success": True}

    else:

        @mcp.tool()
        def list_outages(
            status: str = "all",
            outage_type: str = "all",
        ) -> list[dict[str, Any]]:
            """List outages. status: all, ongoing, resolved. outage_type: all, manual, monitor."""
            return [
                o.model_dump() for o in client.list_outages(status=status, outage_type=outage_type)
            ]

        @mcp.tool()
        def get_outage(outage_id: str) -> dict[str, Any]:
            """Get a single outage by UUID."""
            return client.get_outage(outage_id).model_dump()

        @mcp.tool()
        def create_outage(monitor_uuid: str) -> dict[str, Any]:
            """This will create a manual outage for a monitor."""
            return client.create_outage(monitor_uuid).model_dump()

        @mcp.tool()
        def acknowledge_outage(outage_id: str, message: str | None = None) -> dict[str, Any]:
            """Acknowledge an outage with an optional message."""
            return client.acknowledge_outage(outage_id, message=message).model_dump()

        @mcp.tool()
        def resolve_outage(outage_id: str, message: str | None = None) -> dict[str, Any]:
            """This will resolve an outage with an optional message."""
            return client.resolve_outage(outage_id, message=message).model_dump()

        @mcp.tool()
        def escalate_outage(outage_id: str) -> dict[str, Any]:
            """Escalate an outage to the next on-call tier."""
            return client.escalate_outage(outage_id).model_dump()

        @mcp.tool()
        def unacknowledge_outage(outage_id: str) -> dict[str, Any]:
            """Unacknowledge an outage."""
            return client.unacknowledge_outage(outage_id).model_dump()

        @mcp.tool()
        def delete_outage(outage_id: str) -> dict[str, Any]:
            """This will permanently delete an outage record."""
            client.delete_outage(outage_id)
            return {"success": True}

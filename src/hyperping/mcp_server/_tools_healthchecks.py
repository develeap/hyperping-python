"""Healthcheck tool registrations for the Hyperping MCP server.

Registers 7 tools: list_healthchecks, get_healthcheck, create_healthcheck,
update_healthcheck, delete_healthcheck, pause_healthcheck, resume_healthcheck.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from hyperping._async_client import AsyncHyperpingClient
    from hyperping.client import HyperpingClient


def register_healthcheck_tools(
    mcp: FastMCP,
    client: HyperpingClient | AsyncHyperpingClient,
) -> None:
    """Register healthcheck tools on *mcp*."""
    from hyperping._async_client import AsyncHyperpingClient

    if isinstance(client, AsyncHyperpingClient):

        @mcp.tool()
        async def list_healthchecks() -> list[dict[str, Any]]:
            """List all healthchecks (push-based cron/heartbeat monitors)."""
            return [h.model_dump() for h in await client.list_healthchecks()]

        @mcp.tool()
        async def get_healthcheck(healthcheck_id: str) -> dict[str, Any]:
            """Get a single healthcheck by UUID."""
            return (await client.get_healthcheck(healthcheck_id)).model_dump()

        @mcp.tool()
        async def create_healthcheck(
            name: str,
            period: int,
            grace: int,
            escalation_policy: str | None = None,
            project_uuid: str | None = None,
        ) -> dict[str, Any]:
            """This will create a new healthcheck. period and grace are in seconds."""
            from hyperping.models import HealthcheckCreate

            fields: dict[str, Any] = {"name": name, "period": period, "grace": grace}
            if escalation_policy is not None:
                fields["escalation_policy"] = escalation_policy
            if project_uuid is not None:
                fields["project_uuid"] = project_uuid
            return (await client.create_healthcheck(HealthcheckCreate(**fields))).model_dump()

        @mcp.tool()
        async def update_healthcheck(
            healthcheck_id: str,
            name: str | None = None,
            period: int | None = None,
            grace: int | None = None,
            escalation_policy: str | None = None,
        ) -> dict[str, Any]:
            """Update an existing healthcheck. Only supplied fields are changed."""
            from hyperping.models import HealthcheckUpdate

            fields: dict[str, Any] = {}
            if name is not None:
                fields["name"] = name
            if period is not None:
                fields["period"] = period
            if grace is not None:
                fields["grace"] = grace
            if escalation_policy is not None:
                fields["escalation_policy"] = escalation_policy
            return (
                await client.update_healthcheck(healthcheck_id, HealthcheckUpdate(**fields))
            ).model_dump()

        @mcp.tool()
        async def delete_healthcheck(healthcheck_id: str) -> dict[str, Any]:
            """This will permanently delete a healthcheck."""
            await client.delete_healthcheck(healthcheck_id)
            return {"success": True}

        @mcp.tool()
        async def pause_healthcheck(healthcheck_id: str) -> dict[str, Any]:
            """Pause a healthcheck so it stops alerting on missed pings."""
            return (await client.pause_healthcheck(healthcheck_id)).model_dump()

        @mcp.tool()
        async def resume_healthcheck(healthcheck_id: str) -> dict[str, Any]:
            """Resume a paused healthcheck."""
            return (await client.resume_healthcheck(healthcheck_id)).model_dump()

    else:

        @mcp.tool()
        def list_healthchecks() -> list[dict[str, Any]]:
            """List all healthchecks (push-based cron/heartbeat monitors)."""
            return [h.model_dump() for h in client.list_healthchecks()]

        @mcp.tool()
        def get_healthcheck(healthcheck_id: str) -> dict[str, Any]:
            """Get a single healthcheck by UUID."""
            return client.get_healthcheck(healthcheck_id).model_dump()

        @mcp.tool()
        def create_healthcheck(
            name: str,
            period: int,
            grace: int,
            escalation_policy: str | None = None,
            project_uuid: str | None = None,
        ) -> dict[str, Any]:
            """This will create a new healthcheck. period and grace are in seconds."""
            from hyperping.models import HealthcheckCreate

            fields: dict[str, Any] = {"name": name, "period": period, "grace": grace}
            if escalation_policy is not None:
                fields["escalation_policy"] = escalation_policy
            if project_uuid is not None:
                fields["project_uuid"] = project_uuid
            return client.create_healthcheck(HealthcheckCreate(**fields)).model_dump()

        @mcp.tool()
        def update_healthcheck(
            healthcheck_id: str,
            name: str | None = None,
            period: int | None = None,
            grace: int | None = None,
            escalation_policy: str | None = None,
        ) -> dict[str, Any]:
            """Update an existing healthcheck. Only supplied fields are changed."""
            from hyperping.models import HealthcheckUpdate

            fields: dict[str, Any] = {}
            if name is not None:
                fields["name"] = name
            if period is not None:
                fields["period"] = period
            if grace is not None:
                fields["grace"] = grace
            if escalation_policy is not None:
                fields["escalation_policy"] = escalation_policy
            return client.update_healthcheck(
                healthcheck_id, HealthcheckUpdate(**fields)
            ).model_dump()

        @mcp.tool()
        def delete_healthcheck(healthcheck_id: str) -> dict[str, Any]:
            """This will permanently delete a healthcheck."""
            client.delete_healthcheck(healthcheck_id)
            return {"success": True}

        @mcp.tool()
        def pause_healthcheck(healthcheck_id: str) -> dict[str, Any]:
            """Pause a healthcheck so it stops alerting on missed pings."""
            return client.pause_healthcheck(healthcheck_id).model_dump()

        @mcp.tool()
        def resume_healthcheck(healthcheck_id: str) -> dict[str, Any]:
            """Resume a paused healthcheck."""
            return client.resume_healthcheck(healthcheck_id).model_dump()

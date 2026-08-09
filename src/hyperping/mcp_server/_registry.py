"""Tool group registry for the Hyperping MCP server.

:func:`register_tools` is the single entry point used by the factory.
It dispatches to per-group registration functions and validates the
requested group list.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from hyperping.client import HyperpingClient
    from hyperping.mcp_client import HyperpingMcpClient

_VALID_GROUPS: frozenset[str] = frozenset(
    {
        "monitors",
        "incidents",
        "maintenance",
        "outages",
        "statuspages",
        "healthchecks",
        "observability",
    }
)


def register_tools(
    mcp: FastMCP,
    client: HyperpingClient,
    mcp_client: HyperpingMcpClient | None,
    groups: list[str] | None,
) -> None:
    """Register tool groups on *mcp*.

    Args:
        mcp: FastMCP server instance.
        client: Hyperping REST client used by most tool groups.
        mcp_client: Hyperping MCP client used by the observability group.
            When ``None``, the observability group is silently skipped even
            if it appears in *groups*.
        groups: Tool group names to register. ``None`` registers all groups.

    Raises:
        ValueError: If *groups* contains an unrecognised name.
    """
    if groups is None:
        groups = list(_VALID_GROUPS)

    unknown = set(groups) - _VALID_GROUPS
    if unknown:
        raise ValueError(
            f"Unknown tool groups: {sorted(unknown)}. Valid groups: {sorted(_VALID_GROUPS)}"
        )

    group_set = set(groups)

    if "monitors" in group_set:
        from hyperping.mcp_server._tools_monitors import register_monitor_tools

        register_monitor_tools(mcp, client, mcp_client)

    if "incidents" in group_set:
        from hyperping.mcp_server._tools_incidents import register_incident_tools

        register_incident_tools(mcp, client)

    if "maintenance" in group_set:
        from hyperping.mcp_server._tools_maintenance import register_maintenance_tools

        register_maintenance_tools(mcp, client)

    if "outages" in group_set:
        from hyperping.mcp_server._tools_outages import register_outage_tools

        register_outage_tools(mcp, client)

    if "statuspages" in group_set:
        from hyperping.mcp_server._tools_statuspages import register_statuspage_tools

        register_statuspage_tools(mcp, client)

    if "healthchecks" in group_set:
        from hyperping.mcp_server._tools_healthchecks import register_healthcheck_tools

        register_healthcheck_tools(mcp, client)

    if "observability" in group_set and mcp_client is not None:
        from hyperping.mcp_server._tools_observability import register_observability_tools

        register_observability_tools(mcp, mcp_client)

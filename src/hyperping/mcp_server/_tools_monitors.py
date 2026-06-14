"""Monitor tool registrations for the Hyperping MCP server.

Registers 10 tools: list_monitors, get_monitor, create_monitor,
update_monitor, delete_monitor, pause_monitor, resume_monitor,
get_all_reports, get_monitor_report, search_monitors_by_name.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, cast

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from hyperping._async_client import AsyncHyperpingClient
    from hyperping._async_mcp_client import AsyncHyperpingMcpClient
    from hyperping.client import HyperpingClient
    from hyperping.mcp_client import HyperpingMcpClient


def register_monitor_tools(
    mcp: FastMCP,
    client: HyperpingClient | AsyncHyperpingClient,
    mcp_client: HyperpingMcpClient | AsyncHyperpingMcpClient | None,
) -> None:
    """Register monitor tools on *mcp*."""
    from hyperping._async_client import AsyncHyperpingClient

    if isinstance(client, AsyncHyperpingClient):

        @mcp.tool()
        async def list_monitors() -> list[dict[str, Any]]:
            """List all monitors in the account."""
            return [m.model_dump() for m in await client.list_monitors()]

        @mcp.tool()
        async def get_monitor(monitor_id: str) -> dict[str, Any]:
            """Get a single monitor by UUID."""
            return (await client.get_monitor(monitor_id)).model_dump()

        @mcp.tool()
        async def create_monitor(
            name: str,
            url: str,
            protocol: str | None = None,
            http_method: str | None = None,
            check_frequency: int | None = None,
            regions: list[str] | None = None,
            request_body: str | None = None,
            follow_redirects: bool | None = None,
            expected_status_code: str | None = None,
            required_keyword: str | None = None,
            paused: bool | None = None,
            port: int | None = None,
            alerts_wait: int | None = None,
            escalation_policy: str | None = None,
            dns_record_type: str | None = None,
            dns_nameserver: str | None = None,
            dns_expected_answer: str | None = None,
        ) -> dict[str, Any]:
            """This will create a new monitor."""
            from hyperping.models import MonitorCreate

            fields: dict[str, Any] = {
                "name": name,
                "url": url,
            }
            optionals = {
                "protocol": protocol,
                "http_method": http_method,
                "check_frequency": check_frequency,
                "regions": regions,
                "request_body": request_body,
                "follow_redirects": follow_redirects,
                "expected_status_code": expected_status_code,
                "required_keyword": required_keyword,
                "paused": paused,
                "port": port,
                "alerts_wait": alerts_wait,
                "escalation_policy": escalation_policy,
                "dns_record_type": dns_record_type,
                "dns_nameserver": dns_nameserver,
                "dns_expected_answer": dns_expected_answer,
            }
            fields.update({k: v for k, v in optionals.items() if v is not None})
            return (await client.create_monitor(MonitorCreate(**fields))).model_dump()

        @mcp.tool()
        async def update_monitor(
            monitor_id: str,
            name: str | None = None,
            url: str | None = None,
            protocol: str | None = None,
            http_method: str | None = None,
            check_frequency: int | None = None,
            regions: list[str] | None = None,
            request_body: str | None = None,
            follow_redirects: bool | None = None,
            expected_status_code: str | None = None,
            required_keyword: str | None = None,
            paused: bool | None = None,
            port: int | None = None,
            alerts_wait: int | None = None,
            escalation_policy: str | None = None,
            dns_record_type: str | None = None,
            dns_nameserver: str | None = None,
            dns_expected_answer: str | None = None,
        ) -> dict[str, Any]:
            """Update an existing monitor. Only supplied fields are changed."""
            from hyperping.models import MonitorUpdate

            fields: dict[str, Any] = {}
            candidates = {
                "name": name,
                "url": url,
                "protocol": protocol,
                "http_method": http_method,
                "check_frequency": check_frequency,
                "regions": regions,
                "request_body": request_body,
                "follow_redirects": follow_redirects,
                "expected_status_code": expected_status_code,
                "required_keyword": required_keyword,
                "paused": paused,
                "port": port,
                "alerts_wait": alerts_wait,
                "escalation_policy": escalation_policy,
                "dns_record_type": dns_record_type,
                "dns_nameserver": dns_nameserver,
                "dns_expected_answer": dns_expected_answer,
            }
            fields.update({k: v for k, v in candidates.items() if v is not None})
            return (await client.update_monitor(monitor_id, MonitorUpdate(**fields))).model_dump()

        @mcp.tool()
        async def delete_monitor(monitor_id: str) -> dict[str, Any]:
            """This will permanently delete a monitor and all its historical data."""
            await client.delete_monitor(monitor_id)
            return {"success": True}

        @mcp.tool()
        async def pause_monitor(monitor_id: str) -> dict[str, Any]:
            """Pause a monitor so it stops sending checks."""
            return (await client.pause_monitor(monitor_id)).model_dump()

        @mcp.tool()
        async def resume_monitor(monitor_id: str) -> dict[str, Any]:
            """Resume a paused monitor."""
            return (await client.resume_monitor(monitor_id)).model_dump()

        @mcp.tool()
        async def get_all_reports(period: str = "30d") -> list[dict[str, Any]]:
            """Get uptime reports for all monitors. period: 1h, 24h, 7d, 30d, 90d."""
            _period = cast(Literal["1h", "24h", "7d", "30d", "90d"], period)
            return [r.model_dump() for r in await client.get_all_reports(period=_period)]

        @mcp.tool()
        async def get_monitor_report(monitor_id: str, period: str = "30d") -> dict[str, Any]:
            """Get uptime report for a single monitor. period: 1h, 24h, 7d, 30d, 90d."""
            _period = cast(Literal["1h", "24h", "7d", "30d", "90d"], period)
            return (await client.get_monitor_report(monitor_id, period=_period)).model_dump()

    else:

        @mcp.tool()
        def list_monitors() -> list[dict[str, Any]]:
            """List all monitors in the account."""
            return [m.model_dump() for m in client.list_monitors()]

        @mcp.tool()
        def get_monitor(monitor_id: str) -> dict[str, Any]:
            """Get a single monitor by UUID."""
            return client.get_monitor(monitor_id).model_dump()

        @mcp.tool()
        def create_monitor(
            name: str,
            url: str,
            protocol: str | None = None,
            http_method: str | None = None,
            check_frequency: int | None = None,
            regions: list[str] | None = None,
            request_body: str | None = None,
            follow_redirects: bool | None = None,
            expected_status_code: str | None = None,
            required_keyword: str | None = None,
            paused: bool | None = None,
            port: int | None = None,
            alerts_wait: int | None = None,
            escalation_policy: str | None = None,
            dns_record_type: str | None = None,
            dns_nameserver: str | None = None,
            dns_expected_answer: str | None = None,
        ) -> dict[str, Any]:
            """This will create a new monitor."""
            from hyperping.models import MonitorCreate

            fields: dict[str, Any] = {
                "name": name,
                "url": url,
            }
            optionals = {
                "protocol": protocol,
                "http_method": http_method,
                "check_frequency": check_frequency,
                "regions": regions,
                "request_body": request_body,
                "follow_redirects": follow_redirects,
                "expected_status_code": expected_status_code,
                "required_keyword": required_keyword,
                "paused": paused,
                "port": port,
                "alerts_wait": alerts_wait,
                "escalation_policy": escalation_policy,
                "dns_record_type": dns_record_type,
                "dns_nameserver": dns_nameserver,
                "dns_expected_answer": dns_expected_answer,
            }
            fields.update({k: v for k, v in optionals.items() if v is not None})
            return client.create_monitor(MonitorCreate(**fields)).model_dump()

        @mcp.tool()
        def update_monitor(
            monitor_id: str,
            name: str | None = None,
            url: str | None = None,
            protocol: str | None = None,
            http_method: str | None = None,
            check_frequency: int | None = None,
            regions: list[str] | None = None,
            request_body: str | None = None,
            follow_redirects: bool | None = None,
            expected_status_code: str | None = None,
            required_keyword: str | None = None,
            paused: bool | None = None,
            port: int | None = None,
            alerts_wait: int | None = None,
            escalation_policy: str | None = None,
            dns_record_type: str | None = None,
            dns_nameserver: str | None = None,
            dns_expected_answer: str | None = None,
        ) -> dict[str, Any]:
            """Update an existing monitor. Only supplied fields are changed."""
            from hyperping.models import MonitorUpdate

            fields: dict[str, Any] = {}
            candidates = {
                "name": name,
                "url": url,
                "protocol": protocol,
                "http_method": http_method,
                "check_frequency": check_frequency,
                "regions": regions,
                "request_body": request_body,
                "follow_redirects": follow_redirects,
                "expected_status_code": expected_status_code,
                "required_keyword": required_keyword,
                "paused": paused,
                "port": port,
                "alerts_wait": alerts_wait,
                "escalation_policy": escalation_policy,
                "dns_record_type": dns_record_type,
                "dns_nameserver": dns_nameserver,
                "dns_expected_answer": dns_expected_answer,
            }
            fields.update({k: v for k, v in candidates.items() if v is not None})
            return client.update_monitor(monitor_id, MonitorUpdate(**fields)).model_dump()

        @mcp.tool()
        def delete_monitor(monitor_id: str) -> dict[str, Any]:
            """This will permanently delete a monitor and all its historical data."""
            client.delete_monitor(monitor_id)
            return {"success": True}

        @mcp.tool()
        def pause_monitor(monitor_id: str) -> dict[str, Any]:
            """Pause a monitor so it stops sending checks."""
            return client.pause_monitor(monitor_id).model_dump()

        @mcp.tool()
        def resume_monitor(monitor_id: str) -> dict[str, Any]:
            """Resume a paused monitor."""
            return client.resume_monitor(monitor_id).model_dump()

        @mcp.tool()
        def get_all_reports(period: str = "30d") -> list[dict[str, Any]]:
            """Get uptime reports for all monitors. period: 1h, 24h, 7d, 30d, 90d."""
            _period = cast(Literal["1h", "24h", "7d", "30d", "90d"], period)
            return [r.model_dump() for r in client.get_all_reports(period=_period)]

        @mcp.tool()
        def get_monitor_report(monitor_id: str, period: str = "30d") -> dict[str, Any]:
            """Get uptime report for a single monitor. period: 1h, 24h, 7d, 30d, 90d."""
            _period = cast(Literal["1h", "24h", "7d", "30d", "90d"], period)
            return client.get_monitor_report(monitor_id, period=_period).model_dump()

    from hyperping._async_mcp_client import AsyncHyperpingMcpClient

    if isinstance(mcp_client, AsyncHyperpingMcpClient):

        @mcp.tool()
        async def search_monitors_by_name(query: str) -> list[dict[str, Any]]:
            """Search monitors by name substring."""
            return [m.model_dump() for m in await mcp_client.search_monitors_by_name(query)]

    else:

        @mcp.tool()
        def search_monitors_by_name(query: str) -> list[dict[str, Any]]:
            """Search monitors by name substring."""
            if mcp_client is None:
                raise RuntimeError(
                    "search_monitors_by_name requires an mcp_client. "
                    "Pass mcp_client= to create_mcp_server or supply api_key."
                )
            return [m.model_dump() for m in mcp_client.search_monitors_by_name(query)]

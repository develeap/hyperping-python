"""Status page tool registrations for the Hyperping MCP server.

Registers 8 tools: list_status_pages, get_status_page, create_status_page,
update_status_page, delete_status_page, list_subscribers, add_subscriber,
remove_subscriber.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from hyperping._async_client import AsyncHyperpingClient
    from hyperping.client import HyperpingClient


def register_statuspage_tools(
    mcp: FastMCP,
    client: HyperpingClient | AsyncHyperpingClient,
) -> None:
    """Register status page tools on *mcp*."""
    from hyperping._async_client import AsyncHyperpingClient
    from hyperping.mcp_server._annotations import ACTION, DESTRUCTIVE, MUTATING, READ_ONLY

    if isinstance(client, AsyncHyperpingClient):


        @mcp.tool(annotations=READ_ONLY)
        async def list_status_pages(search: str | None = None) -> list[dict[str, Any]]:
            """List all status pages. Optionally filter by name or subdomain."""
            return [p.model_dump() for p in await client.list_status_pages(search=search)]

        @mcp.tool(annotations=READ_ONLY)
        async def get_status_page(status_page_id: str) -> dict[str, Any]:
            """Get a single status page by UUID."""
            return (await client.get_status_page(status_page_id)).model_dump()

        @mcp.tool(annotations=MUTATING)
        async def create_status_page(
            name: str,
            subdomain: str,
            custom_domain: str | None = None,
            public: bool | None = None,
            monitors: list[str] | None = None,
        ) -> dict[str, Any]:
            """This will create a new status page."""
            from hyperping.models import StatusPageCreate

            fields: dict[str, Any] = {"name": name, "subdomain": subdomain}
            if custom_domain is not None:
                fields["custom_domain"] = custom_domain
            if public is not None:
                fields["public"] = public
            if monitors is not None:
                fields["monitors"] = monitors
            return (await client.create_status_page(StatusPageCreate(**fields))).model_dump()

        @mcp.tool(annotations=MUTATING)
        async def update_status_page(
            status_page_id: str,
            name: str | None = None,
            subdomain: str | None = None,
            custom_domain: str | None = None,
            public: bool | None = None,
            monitors: list[str] | None = None,
        ) -> dict[str, Any]:
            """Update an existing status page. Only supplied fields are changed."""
            from hyperping.models import StatusPageUpdate

            fields: dict[str, Any] = {}
            if name is not None:
                fields["name"] = name
            if subdomain is not None:
                fields["subdomain"] = subdomain
            if custom_domain is not None:
                fields["custom_domain"] = custom_domain
            if public is not None:
                fields["public"] = public
            if monitors is not None:
                fields["monitors"] = monitors
            return (
                await client.update_status_page(status_page_id, StatusPageUpdate(**fields))
            ).model_dump()

        @mcp.tool(annotations=DESTRUCTIVE)
        async def delete_status_page(status_page_id: str) -> dict[str, Any]:
            """This will permanently delete a status page."""
            await client.delete_status_page(status_page_id)
            return {"success": True}

        @mcp.tool(annotations=READ_ONLY)
        async def list_subscribers(
            status_page_id: str,
            subscriber_type: str = "all",
        ) -> list[dict[str, Any]]:
            """List subscribers for a status page. subscriber_type: all, email, sms, slack."""
            return [
                s.model_dump()
                for s in await client.list_subscribers(
                    status_page_id, subscriber_type=subscriber_type
                )
            ]

        @mcp.tool(annotations=MUTATING)
        async def add_subscriber(status_page_id: str, email: str) -> dict[str, Any]:
            """This will add an email subscriber to a status page."""
            return (await client.add_subscriber(status_page_id, email)).model_dump()

        @mcp.tool(annotations=DESTRUCTIVE)
        async def remove_subscriber(status_page_id: str, subscriber_id: str) -> dict[str, Any]:
            """This will remove a subscriber from a status page."""
            await client.remove_subscriber(status_page_id, subscriber_id)
            return {"success": True}

    else:

        @mcp.tool(annotations=READ_ONLY)
        def list_status_pages(search: str | None = None) -> list[dict[str, Any]]:
            """List all status pages. Optionally filter by name or subdomain."""
            return [p.model_dump() for p in client.list_status_pages(search=search)]

        @mcp.tool(annotations=READ_ONLY)
        def get_status_page(status_page_id: str) -> dict[str, Any]:
            """Get a single status page by UUID."""
            return client.get_status_page(status_page_id).model_dump()

        @mcp.tool(annotations=MUTATING)
        def create_status_page(
            name: str,
            subdomain: str,
            custom_domain: str | None = None,
            public: bool | None = None,
            monitors: list[str] | None = None,
        ) -> dict[str, Any]:
            """This will create a new status page."""
            from hyperping.models import StatusPageCreate

            fields: dict[str, Any] = {"name": name, "subdomain": subdomain}
            if custom_domain is not None:
                fields["custom_domain"] = custom_domain
            if public is not None:
                fields["public"] = public
            if monitors is not None:
                fields["monitors"] = monitors
            return client.create_status_page(StatusPageCreate(**fields)).model_dump()

        @mcp.tool(annotations=MUTATING)
        def update_status_page(
            status_page_id: str,
            name: str | None = None,
            subdomain: str | None = None,
            custom_domain: str | None = None,
            public: bool | None = None,
            monitors: list[str] | None = None,
        ) -> dict[str, Any]:
            """Update an existing status page. Only supplied fields are changed."""
            from hyperping.models import StatusPageUpdate

            fields: dict[str, Any] = {}
            if name is not None:
                fields["name"] = name
            if subdomain is not None:
                fields["subdomain"] = subdomain
            if custom_domain is not None:
                fields["custom_domain"] = custom_domain
            if public is not None:
                fields["public"] = public
            if monitors is not None:
                fields["monitors"] = monitors
            return client.update_status_page(status_page_id, StatusPageUpdate(**fields)).model_dump()

        @mcp.tool(annotations=DESTRUCTIVE)
        def delete_status_page(status_page_id: str) -> dict[str, Any]:
            """This will permanently delete a status page."""
            client.delete_status_page(status_page_id)
            return {"success": True}

        @mcp.tool(annotations=READ_ONLY)
        def list_subscribers(
            status_page_id: str,
            subscriber_type: str = "all",
        ) -> list[dict[str, Any]]:
            """List subscribers for a status page. subscriber_type: all, email, sms, slack."""
            return [
                s.model_dump()
                for s in client.list_subscribers(
                    status_page_id, subscriber_type=subscriber_type
                )
            ]

        @mcp.tool(annotations=MUTATING)
        def add_subscriber(status_page_id: str, email: str) -> dict[str, Any]:
            """This will add an email subscriber to a status page."""
            return client.add_subscriber(status_page_id, email).model_dump()

        @mcp.tool(annotations=DESTRUCTIVE)
        def remove_subscriber(status_page_id: str, subscriber_id: str) -> dict[str, Any]:
            """This will remove a subscriber from a status page."""
            client.remove_subscriber(status_page_id, subscriber_id)
            return {"success": True}

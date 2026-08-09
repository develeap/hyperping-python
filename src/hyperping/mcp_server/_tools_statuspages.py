"""Status page tool registrations for the Hyperping MCP server.

Registers 8 tools: list_status_pages, get_status_page, create_status_page,
update_status_page, delete_status_page, list_subscribers, add_subscriber,
remove_subscriber.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from hyperping.client import HyperpingClient


def register_statuspage_tools(mcp: FastMCP, client: HyperpingClient) -> None:
    """Register status page tools on *mcp*."""

    @mcp.tool()
    def list_status_pages(search: str | None = None) -> list[dict[str, Any]]:
        """List all status pages. Optionally filter by name or subdomain."""
        return [p.model_dump() for p in client.list_status_pages(search=search)]

    @mcp.tool()
    def get_status_page(status_page_id: str) -> dict[str, Any]:
        """Get a single status page by UUID."""
        return client.get_status_page(status_page_id).model_dump()

    @mcp.tool()
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

    @mcp.tool()
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

    @mcp.tool()
    def delete_status_page(status_page_id: str) -> dict[str, Any]:
        """This will permanently delete a status page."""
        client.delete_status_page(status_page_id)
        return {"success": True}

    @mcp.tool()
    def list_subscribers(
        status_page_id: str,
        subscriber_type: str = "all",
    ) -> list[dict[str, Any]]:
        """List subscribers for a status page. subscriber_type: all, email, sms, slack, teams."""
        return [
            s.model_dump()
            for s in client.list_subscribers(
                status_page_id, subscriber_type=subscriber_type
            )
        ]

    @mcp.tool()
    def add_subscriber(status_page_id: str, email: str) -> dict[str, Any]:
        """This will add an email subscriber to a status page."""
        return client.add_subscriber(status_page_id, email).model_dump()

    @mcp.tool()
    def remove_subscriber(status_page_id: str, subscriber_id: str) -> dict[str, Any]:
        """This will remove a subscriber from a status page."""
        client.remove_subscriber(status_page_id, subscriber_id)
        return {"success": True}

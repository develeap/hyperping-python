"""hyp statuspage subcommands."""

from __future__ import annotations

from typing import Annotated

import typer

from hyperping.cli._config import get_client
from hyperping.cli._output import print_detail, print_error, print_table
from hyperping.exceptions import HyperpingAPIError

statuspage_app = typer.Typer(name="statuspage", help="Manage status pages.")


@statuspage_app.command("show")
def statuspage_show(
    ctx: typer.Context,
    statuspage_id: Annotated[str, typer.Argument(help="Status page UUID")],
) -> None:
    """Show a status page."""
    api_key: str | None = ctx.obj.get("api_key")
    json_mode: bool = ctx.obj.get("json", False)
    client = get_client(api_key)
    try:
        page = client.get_status_page(statuspage_id)
    except HyperpingAPIError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc
    fields = {
        "uuid": page.uuid,
        "name": page.name,
        "subdomain": page.subdomain,
        "custom_domain": page.custom_domain or "",
        "public": page.public,
        "monitors": ", ".join(page.monitors),
    }
    print_detail("Status Page", fields, json_mode)


@statuspage_app.command("subscribers")
def statuspage_subscribers(
    ctx: typer.Context,
    statuspage_id: Annotated[str, typer.Argument(help="Status page UUID")],
) -> None:
    """List subscribers for a status page."""
    api_key: str | None = ctx.obj.get("api_key")
    json_mode: bool = ctx.obj.get("json", False)
    client = get_client(api_key)
    try:
        subs = client.list_subscribers(statuspage_id)
    except HyperpingAPIError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc
    columns = ["id", "email"]
    rows = [[s.id, s.email] for s in subs]
    print_table("Subscribers", columns, rows, json_mode)

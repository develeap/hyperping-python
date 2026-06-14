"""hyp tenant subcommands."""

from __future__ import annotations

import re
from typing import Annotated

import typer

from hyperping.cli._config import get_client
from hyperping.cli._output import print_detail, print_error
from hyperping.exceptions import HyperpingAPIError
from hyperping.models import MonitorCreate, StatusPageCreate, StatusPageUpdate

tenant_app = typer.Typer(name="tenant", help="Tenant onboarding operations.")


def _slugify(name: str) -> str:
    """Convert a name to a URL-safe subdomain slug."""
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug.strip())
    slug = re.sub(r"-+", "-", slug)
    return slug[:63]


@tenant_app.command("onboard")
def tenant_onboard(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Tenant name")],
    monitor_url: Annotated[
        list[str] | None,
        typer.Option("--monitor-url", help="URL to monitor (repeatable)"),
    ] = None,
) -> None:
    """Onboard a new tenant: create a status page and optional monitors."""
    api_key: str | None = ctx.obj.get("api_key")
    json_mode: bool = ctx.obj.get("json", False)
    client = get_client(api_key)

    page_create = StatusPageCreate(name=name, subdomain=_slugify(name))
    try:
        page = client.create_status_page(page_create)
    except HyperpingAPIError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc

    monitor_uuids: list[str] = []
    for url in monitor_url or []:
        mon_create = MonitorCreate(name=f"{name} - {url}", url=url)
        try:
            mon = client.create_monitor(mon_create)
        except HyperpingAPIError as exc:
            print_error(f"Failed to create monitor for {url}: {exc}")
            raise typer.Exit(code=1) from exc
        monitor_uuids.append(mon.uuid)

    if monitor_uuids:
        existing = list(page.monitors)
        try:
            page = client.update_status_page(
                page.uuid,
                StatusPageUpdate(monitors=existing + monitor_uuids),
            )
        except HyperpingAPIError as exc:
            print_error(str(exc))
            raise typer.Exit(code=1) from exc

    fields: dict[str, object] = {
        "status_page_uuid": page.uuid,
        "name": page.name,
        "subdomain": page.subdomain,
        "monitors": ", ".join(monitor_uuids) if monitor_uuids else "(none)",
    }
    print_detail("Tenant Onboarded", fields, json_mode)

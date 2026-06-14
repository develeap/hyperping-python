"""hyp monitor subcommands."""

from __future__ import annotations

from typing import Annotated

import typer

from hyperping.cli._config import get_client
from hyperping.cli._output import print_detail, print_error, print_success, print_table
from hyperping.exceptions import HyperpingAPIError
from hyperping.models import Monitor

monitor_app = typer.Typer(name="monitor", help="Manage monitors.")


def _monitor_status(m: Monitor) -> str:
    if m.paused:
        return "paused"
    return "down" if m.down else "up"


@monitor_app.command("list")
def monitor_list(ctx: typer.Context) -> None:
    """List all monitors."""
    api_key: str | None = ctx.obj.get("api_key")
    json_mode: bool = ctx.obj.get("json", False)
    client = get_client(api_key)
    monitors = client.list_monitors()
    columns = ["uuid", "name", "url", "protocol", "status"]
    rows = [[m.uuid, m.name, m.url, m.protocol, _monitor_status(m)] for m in monitors]
    print_table("Monitors", columns, rows, json_mode)


@monitor_app.command("get")
def monitor_get(
    ctx: typer.Context,
    monitor_id: Annotated[str, typer.Argument(help="Monitor UUID")],
) -> None:
    """Show a single monitor."""
    api_key: str | None = ctx.obj.get("api_key")
    json_mode: bool = ctx.obj.get("json", False)
    client = get_client(api_key)
    try:
        m = client.get_monitor(monitor_id)
    except HyperpingAPIError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc
    fields = {
        "uuid": m.uuid,
        "name": m.name,
        "url": m.url,
        "protocol": m.protocol,
        "status": _monitor_status(m),
        "check_frequency": m.check_frequency,
        "regions": ", ".join(m.regions),
    }
    print_detail("Monitor", fields, json_mode)


@monitor_app.command("pause")
def monitor_pause(
    ctx: typer.Context,
    monitor_id: Annotated[str, typer.Argument(help="Monitor UUID")],
) -> None:
    """Pause a monitor."""
    api_key: str | None = ctx.obj.get("api_key")
    client = get_client(api_key)
    try:
        m = client.pause_monitor(monitor_id)
    except HyperpingAPIError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc
    print_success(f"Monitor {m.uuid} paused (status: {_monitor_status(m)})")


@monitor_app.command("resume")
def monitor_resume(
    ctx: typer.Context,
    monitor_id: Annotated[str, typer.Argument(help="Monitor UUID")],
) -> None:
    """Resume a paused monitor."""
    api_key: str | None = ctx.obj.get("api_key")
    client = get_client(api_key)
    try:
        m = client.resume_monitor(monitor_id)
    except HyperpingAPIError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc
    print_success(f"Monitor {m.uuid} resumed (status: {_monitor_status(m)})")

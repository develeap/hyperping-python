"""Main hyp CLI application."""

from __future__ import annotations

from typing import Annotated

import typer

from hyperping._version import __version__
from hyperping.cli._incidents import incident_app
from hyperping.cli._monitors import monitor_app
from hyperping.cli._statuspages import statuspage_app
from hyperping.cli._tenant import tenant_app

app = typer.Typer(
    name="hyp",
    help="Hyperping CLI: manage monitors, incidents, and status pages.",
    no_args_is_help=True,
)

app.add_typer(monitor_app, name="monitor")
app.add_typer(incident_app, name="incident")
app.add_typer(statuspage_app, name="statuspage")
app.add_typer(tenant_app, name="tenant")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"hyp {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    api_key: Annotated[
        str | None,
        typer.Option("--api-key", envvar="HYPERPING_API_KEY", help="Hyperping API key."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON."),
    ] = False,
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version."),
    ] = None,
) -> None:
    """Hyperping CLI."""
    ctx.ensure_object(dict)
    ctx.obj["api_key"] = api_key
    ctx.obj["json"] = json_output

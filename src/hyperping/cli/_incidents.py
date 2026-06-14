"""hyp incident subcommands."""

from __future__ import annotations

from typing import Annotated

import typer

from hyperping.cli._config import get_client
from hyperping.cli._output import print_detail, print_error, print_success, print_table
from hyperping.exceptions import HyperpingAPIError
from hyperping.models import Incident, IncidentCreate, IncidentType, LocalizedText

incident_app = typer.Typer(name="incident", help="Manage incidents.")


def _incident_row(i: Incident) -> list[object]:
    return [i.uuid, i.title_en, i.type, str(i.is_resolved), i.date or ""]


@incident_app.command("list")
def incident_list(
    ctx: typer.Context,
    status: Annotated[str | None, typer.Option("--status", help="Filter by status")] = None,
) -> None:
    """List incidents."""
    api_key: str | None = ctx.obj.get("api_key")
    json_mode: bool = ctx.obj.get("json", False)
    client = get_client(api_key)
    incidents = client.list_incidents(status=status)
    columns = ["uuid", "title", "type", "resolved", "date"]
    rows = [_incident_row(i) for i in incidents]
    print_table("Incidents", columns, rows, json_mode)


@incident_app.command("create")
def incident_create(
    ctx: typer.Context,
    title: Annotated[str, typer.Option("--title", help="Incident title (English)")],
    text: Annotated[str, typer.Option("--text", help="Incident message (English)")],
    statuspage: Annotated[str, typer.Option("--statuspage", help="Status page UUID")],
    incident_type: Annotated[
        str | None, typer.Option("--type", help="Incident type: incident or outage")
    ] = None,
) -> None:
    """Create a new incident."""
    api_key: str | None = ctx.obj.get("api_key")
    json_mode: bool = ctx.obj.get("json", False)
    client = get_client(api_key)
    payload = IncidentCreate(
        title=LocalizedText.from_string(title),
        text=LocalizedText.from_string(text),
        type=IncidentType(incident_type) if incident_type else IncidentType.INCIDENT,
        statuspages=[statuspage],
    )
    try:
        incident = client.create_incident(payload)
    except HyperpingAPIError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc
    fields = {
        "uuid": incident.uuid,
        "title": incident.title_en,
        "type": incident.type,
        "resolved": incident.is_resolved,
        "date": incident.date or "",
    }
    print_detail("Incident", fields, json_mode)


@incident_app.command("resolve")
def incident_resolve(
    ctx: typer.Context,
    incident_id: Annotated[str, typer.Argument(help="Incident UUID")],
    message: Annotated[
        str | None, typer.Option("--message", help="Resolution message")
    ] = None,
) -> None:
    """Resolve an incident."""
    api_key: str | None = ctx.obj.get("api_key")
    client = get_client(api_key)
    try:
        incident = client.resolve_incident(incident_id, message=message)
    except HyperpingAPIError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc
    print_success(f"Incident {incident.uuid} resolved.")

"""CLI output formatters: rich tables, panels, and JSON."""

from __future__ import annotations

import json
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

_console = Console()
_err_console = Console(stderr=True)


def print_table(
    title: str,
    columns: list[str],
    rows: list[list[Any]],
    json_mode: bool,
) -> None:
    """Render a list of rows as a rich table or a JSON array."""
    if json_mode:
        data = [dict(zip(columns, row)) for row in rows]
        typer.echo(json.dumps(data, indent=2, default=str))
        return

    table = Table(title=title, show_header=True, header_style="bold")
    for col in columns:
        table.add_column(col)
    for row in rows:
        table.add_row(*[str(v) if v is not None else "" for v in row])
    _console.print(table)


def print_detail(
    title: str,
    fields: dict[str, Any],
    json_mode: bool,
) -> None:
    """Render a single record as a rich panel or a JSON object."""
    if json_mode:
        typer.echo(json.dumps(fields, indent=2, default=str))
        return

    lines = "\n".join(f"[bold]{k}[/bold]: {v}" for k, v in fields.items())
    _console.print(Panel(lines, title=title))


def print_success(message: str) -> None:
    """Print a success message."""
    _console.print(f"[green]{message}[/green]")


def print_error(message: str) -> None:
    """Print an error message to stderr."""
    _err_console.print(f"[red]{message}[/red]")

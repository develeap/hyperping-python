"""CLI client factory and API key resolution."""

from __future__ import annotations

import os

import typer

from hyperping.client import HyperpingClient


def get_client(api_key: str | None) -> HyperpingClient:
    """Resolve API key and return a configured client.

    Resolution order: explicit flag value, then HYPERPING_API_KEY env var.
    Raises typer.BadParameter if no key is available.
    """
    key = api_key or os.environ.get("HYPERPING_API_KEY")
    if not key:
        raise typer.BadParameter(
            "API key required. Pass --api-key or set HYPERPING_API_KEY.",
            param_hint="--api-key",
        )
    return HyperpingClient(api_key=key)

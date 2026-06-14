"""CLI entrypoint for the Hyperping MCP server.

Run with::

    python -m hyperping.mcp_server --api-key sk_...
    python -m hyperping.mcp_server --api-key sk_... --transport sse --port 8080
    python -m hyperping.mcp_server --api-key sk_... --tools monitors,incidents
"""

from __future__ import annotations

import argparse
import os

from hyperping.mcp_server import create_mcp_server


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m hyperping.mcp_server",
        description="Start the Hyperping MCP server.",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Hyperping API key. Falls back to the HYPERPING_API_KEY environment variable.",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="MCP transport to use (default: stdio).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for the SSE transport (default: 8080).",
    )
    parser.add_argument(
        "--tools",
        default=None,
        help=(
            "Comma-separated list of tool groups to enable. "
            "Valid groups: monitors, incidents, maintenance, outages, "
            "statuspages, healthchecks, observability. "
            "Omit to enable all groups."
        ),
    )
    parser.add_argument(
        "--name",
        default="hyperping",
        help="Server name (default: hyperping).",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """Parse arguments and start the MCP server."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    api_key = args.api_key or os.environ.get("HYPERPING_API_KEY")
    if not api_key:
        parser.error(
            "API key is required. Pass --api-key or set the HYPERPING_API_KEY environment variable."
        )

    tools: list[str] | None = None
    if args.tools:
        tools = [t.strip() for t in args.tools.split(",") if t.strip()]

    server = create_mcp_server(api_key=api_key, tools=tools, name=args.name)

    server.run(transport=args.transport)


if __name__ == "__main__":
    main()

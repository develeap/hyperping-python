"""MCP server factory for the Hyperping SDK.

Exposes a single public entry point, :func:`create_mcp_server`, that builds
a :class:`~mcp.server.fastmcp.FastMCP` instance pre-loaded with Hyperping
tools grouped by resource type.

Example::

    from hyperping.mcp_server import create_mcp_server

    server = create_mcp_server(api_key="sk_...")
    server.run()
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from hyperping._async_client import AsyncHyperpingClient
    from hyperping._async_mcp_client import AsyncHyperpingMcpClient
    from hyperping.client import HyperpingClient
    from hyperping.mcp_client import HyperpingMcpClient


def create_mcp_server(
    api_key: str | None = None,
    client: HyperpingClient | AsyncHyperpingClient | None = None,
    mcp_client: HyperpingMcpClient | AsyncHyperpingMcpClient | None = None,
    tools: list[str] | None = None,
    name: str = "hyperping",
) -> FastMCP:
    """Create a FastMCP server pre-loaded with Hyperping tools.

    Args:
        api_key: Hyperping API key. Used to create internal REST and MCP
            clients when *client* and *mcp_client* are not supplied.
            When only *api_key* is provided, sync clients are created.
        client: Pre-configured :class:`~hyperping.client.HyperpingClient` or
            :class:`~hyperping._async_client.AsyncHyperpingClient`.
            Takes precedence over *api_key* for REST operations. When an
            async client is passed, all REST tools are registered as
            coroutine functions so FastMCP can run them on the event loop.
        mcp_client: Pre-configured :class:`~hyperping.mcp_client.HyperpingMcpClient`
            or :class:`~hyperping._async_mcp_client.AsyncHyperpingMcpClient`.
            Required for the observability tool group. When ``None`` and
            *api_key* is provided, a sync client is created internally. When
            ``None`` and only *client* is provided, the observability group
            is skipped. When an async client is passed, observability tools
            are registered as coroutines.
        tools: List of tool group names to register. ``None`` (default)
            registers all groups. Valid group names: ``monitors``,
            ``incidents``, ``maintenance``, ``outages``, ``statuspages``,
            ``healthchecks``, ``observability``.
        name: Server name passed to FastMCP. Defaults to ``"hyperping"``.

    Returns:
        Configured :class:`~mcp.server.fastmcp.FastMCP` instance.

    Raises:
        ImportError: If the ``mcp`` package is not installed.
        ValueError: If neither *api_key* nor *client* is provided, or if
            *tools* contains an unrecognised group name.
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise ImportError(
            "The mcp package is required. Install with: pip install 'hyperping[mcp-server]'"
        ) from exc

    if client is None and api_key is None:
        raise ValueError("Provide api_key or a pre-configured client.")

    if client is None:
        from hyperping.client import HyperpingClient

        client = HyperpingClient(api_key=api_key)  # type: ignore[arg-type]

    if mcp_client is None and api_key is not None:
        from hyperping.mcp_client import HyperpingMcpClient

        mcp_client = HyperpingMcpClient(api_key=api_key)

    server = FastMCP(name)

    from hyperping.mcp_server._registry import register_tools

    register_tools(server, client, mcp_client, tools)
    return server


__all__ = ["create_mcp_server"]

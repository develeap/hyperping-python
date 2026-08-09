"""Tests for create_mcp_server factory (T1)."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture()
def mock_client():
    from hyperping.client import HyperpingClient

    return MagicMock(spec=HyperpingClient)


@pytest.fixture()
def mock_mcp_client():
    from hyperping.mcp_client import HyperpingMcpClient

    return MagicMock(spec=HyperpingMcpClient)


class TestCreateServerFactory:
    def test_create_server_with_api_key(self):
        """create_mcp_server with api_key creates a FastMCP server."""
        from mcp.server.fastmcp import FastMCP

        from hyperping.mcp_server import create_mcp_server

        with (
            patch("hyperping.client.HyperpingClient") as mock_client_cls,
            patch("hyperping.mcp_client.HyperpingMcpClient") as mock_mcp_cls,
        ):
            mock_client_cls.return_value = MagicMock()
            mock_mcp_cls.return_value = MagicMock()
            server = create_mcp_server(api_key="sk_test")

        assert isinstance(server, FastMCP)

    def test_create_server_with_client(self, mock_client, mock_mcp_client):
        """create_mcp_server with pre-configured clients creates a FastMCP server."""
        from mcp.server.fastmcp import FastMCP

        from hyperping.mcp_server import create_mcp_server

        server = create_mcp_server(client=mock_client, mcp_client=mock_mcp_client)
        assert isinstance(server, FastMCP)

    def test_create_server_with_mcp_client(self, mock_client, mock_mcp_client):
        """create_mcp_server accepts a pre-configured HyperpingMcpClient."""
        from mcp.server.fastmcp import FastMCP

        from hyperping.mcp_server import create_mcp_server

        server = create_mcp_server(client=mock_client, mcp_client=mock_mcp_client)
        assert isinstance(server, FastMCP)

    def test_create_server_no_credentials_raises(self):
        """create_mcp_server without api_key or client raises ValueError."""
        from hyperping.mcp_server import create_mcp_server

        with pytest.raises(ValueError, match="api_key"):
            create_mcp_server()

    def test_import_error_without_mcp(self, mock_client):
        """create_mcp_server raises ImportError when mcp package is absent."""
        from hyperping.mcp_server import create_mcp_server

        with patch.dict(sys.modules, {"mcp": None, "mcp.server": None, "mcp.server.fastmcp": None}):
            with pytest.raises(ImportError, match="mcp package"):
                create_mcp_server(client=mock_client)

    def test_create_server_custom_name(self, mock_client, mock_mcp_client):
        """create_mcp_server sets server name correctly."""
        from hyperping.mcp_server import create_mcp_server

        server = create_mcp_server(client=mock_client, mcp_client=mock_mcp_client, name="my-server")
        assert server.name == "my-server"

    def test_create_server_default_name(self, mock_client, mock_mcp_client):
        """Default server name is 'hyperping'."""
        from hyperping.mcp_server import create_mcp_server

        server = create_mcp_server(client=mock_client, mcp_client=mock_mcp_client)
        assert server.name == "hyperping"

    def test_create_server_invalid_group_raises(self, mock_client, mock_mcp_client):
        """create_mcp_server raises ValueError for unrecognised tool group names."""
        from hyperping.mcp_server import create_mcp_server

        with pytest.raises(ValueError, match="Unknown tool groups"):
            create_mcp_server(client=mock_client, mcp_client=mock_mcp_client, tools=["bogus"])

    def test_create_server_with_tool_filter(self, mock_client, mock_mcp_client):
        """tools=['monitors'] registers exactly the monitor group (10 tools)."""
        from hyperping.mcp_server import create_mcp_server

        server = create_mcp_server(
            client=mock_client, mcp_client=mock_mcp_client, tools=["monitors"]
        )
        tool_names = {t.name for t in server._tool_manager.list_tools()}
        assert "list_monitors" in tool_names
        assert "list_incidents" not in tool_names
        assert len(tool_names) == 10

    def test_total_tool_count(self, mock_client, mock_mcp_client):
        """Default server registers exactly 62 tools across all groups."""
        from hyperping.mcp_server import create_mcp_server

        server = create_mcp_server(client=mock_client, mcp_client=mock_mcp_client)
        assert len(server._tool_manager.list_tools()) == 62

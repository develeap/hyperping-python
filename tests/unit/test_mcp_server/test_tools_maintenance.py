"""Tests for maintenance tools (T4)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def _call(server, tool_name, **kwargs):
    """Call a registered tool function by name directly."""
    tool = next(t for t in server._tool_manager.list_tools() if t.name == tool_name)
    return tool.fn(**kwargs)


@pytest.fixture()
def mock_client():
    from hyperping.client import HyperpingClient

    return MagicMock(spec=HyperpingClient)


@pytest.fixture()
def server(mock_client):
    from hyperping.mcp_server import create_mcp_server

    return create_mcp_server(client=mock_client, tools=["maintenance"])


class TestMaintenanceTools:
    def test_all_maintenance_tools_count(self, server):
        assert len(server._tool_manager.list_tools()) == 7

    def test_list_maintenance_delegates(self, server, mock_client):
        mock_client.list_maintenance.return_value = []
        _call(server, "list_maintenance")
        mock_client.list_maintenance.assert_called_once_with(status=None)

    def test_is_monitor_in_maintenance_delegates(self, server, mock_client):
        mock_client.is_monitor_in_maintenance.return_value = True
        result = _call(server, "is_monitor_in_maintenance", monitor_uuid="uuid-1")
        mock_client.is_monitor_in_maintenance.assert_called_once_with("uuid-1")
        assert result["in_maintenance"] is True


async def _call_async(server, tool_name, **kwargs):
    tool = next(t for t in server._tool_manager.list_tools() if t.name == tool_name)
    return await tool.fn(**kwargs)


@pytest.fixture()
def mock_async_client():
    from hyperping._async_client import AsyncHyperpingClient

    return MagicMock(spec=AsyncHyperpingClient)


@pytest.fixture()
def async_server(mock_async_client):
    from hyperping.mcp_server import create_mcp_server

    return create_mcp_server(client=mock_async_client, tools=["maintenance"])


class TestMaintenanceToolsAsync:
    async def test_list_maintenance_async_delegates(self, async_server, mock_async_client):
        from unittest.mock import AsyncMock

        mock_async_client.list_maintenance = AsyncMock(return_value=[])

        await _call_async(async_server, "list_maintenance")
        mock_async_client.list_maintenance.assert_called_once()

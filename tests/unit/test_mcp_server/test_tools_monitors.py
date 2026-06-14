"""Tests for monitor tools (T2)."""

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
def mock_mcp_client():
    from hyperping.mcp_client import HyperpingMcpClient

    return MagicMock(spec=HyperpingMcpClient)


@pytest.fixture()
def server(mock_client, mock_mcp_client):
    from hyperping.mcp_server import create_mcp_server

    return create_mcp_server(client=mock_client, mcp_client=mock_mcp_client, tools=["monitors"])


class TestMonitorTools:
    def test_all_monitor_tools_count(self, server):
        assert len(server._tool_manager.list_tools()) == 10

    def test_list_monitors_registered(self, server):
        names = {t.name for t in server._tool_manager.list_tools()}
        assert "list_monitors" in names

    def test_list_monitors_delegates(self, server, mock_client):
        monitor = MagicMock()
        monitor.model_dump.return_value = {"uuid": "abc", "name": "test"}
        mock_client.list_monitors.return_value = [monitor]

        result = _call(server, "list_monitors")
        mock_client.list_monitors.assert_called_once()
        assert result[0]["uuid"] == "abc"

    def test_get_monitor_accepts_id(self, server, mock_client):
        monitor = MagicMock()
        monitor.model_dump.return_value = {"uuid": "abc"}
        mock_client.get_monitor.return_value = monitor

        _call(server, "get_monitor", monitor_id="abc")
        mock_client.get_monitor.assert_called_once_with("abc")

    def test_create_monitor_delegates(self, server, mock_client):
        monitor = MagicMock()
        monitor.model_dump.return_value = {"uuid": "new", "name": "m1"}
        mock_client.create_monitor.return_value = monitor

        _call(server, "create_monitor", name="m1", url="https://example.com")
        mock_client.create_monitor.assert_called_once()

    def test_delete_monitor_returns_success(self, server, mock_client):
        mock_client.delete_monitor.return_value = None

        result = _call(server, "delete_monitor", monitor_id="abc")
        mock_client.delete_monitor.assert_called_once_with("abc")
        assert result.get("success") is True

    def test_delete_monitor_description_warns(self, server):
        tool = next(t for t in server._tool_manager.list_tools() if t.name == "delete_monitor")
        assert tool.description is not None
        assert "delete" in tool.description.lower() or "This will" in tool.description

    def test_search_monitors_delegates_to_mcp_client(self, server, mock_mcp_client):
        m = MagicMock()
        m.model_dump.return_value = {"uuid": "abc", "name": "my monitor"}
        mock_mcp_client.search_monitors_by_name.return_value = [m]

        _call(server, "search_monitors_by_name", query="my")
        mock_mcp_client.search_monitors_by_name.assert_called_once_with("my")


async def _call_async(server, tool_name, **kwargs):
    tool = next(t for t in server._tool_manager.list_tools() if t.name == tool_name)
    return await tool.fn(**kwargs)


@pytest.fixture()
def mock_async_client():
    from hyperping._async_client import AsyncHyperpingClient

    return MagicMock(spec=AsyncHyperpingClient)


@pytest.fixture()
def mock_async_mcp_client():
    from hyperping._async_mcp_client import AsyncHyperpingMcpClient

    return MagicMock(spec=AsyncHyperpingMcpClient)


@pytest.fixture()
def async_server(mock_async_client, mock_async_mcp_client):
    from hyperping.mcp_server import create_mcp_server

    return create_mcp_server(
        client=mock_async_client, mcp_client=mock_async_mcp_client, tools=["monitors"]
    )


class TestMonitorToolsAsync:
    async def test_list_monitors_async_delegates(self, async_server, mock_async_client):
        from unittest.mock import AsyncMock

        monitor = MagicMock()
        monitor.model_dump.return_value = {"uuid": "abc", "name": "test"}
        mock_async_client.list_monitors = AsyncMock(return_value=[monitor])

        result = await _call_async(async_server, "list_monitors")
        mock_async_client.list_monitors.assert_called_once()
        assert result[0]["uuid"] == "abc"

    async def test_get_monitor_async_delegates(self, async_server, mock_async_client):
        from unittest.mock import AsyncMock

        monitor = MagicMock()
        monitor.model_dump.return_value = {"uuid": "abc"}
        mock_async_client.get_monitor = AsyncMock(return_value=monitor)

        await _call_async(async_server, "get_monitor", monitor_id="abc")
        mock_async_client.get_monitor.assert_called_once_with("abc")

    async def test_create_monitor_async_delegates(self, async_server, mock_async_client):
        from unittest.mock import AsyncMock

        monitor = MagicMock()
        monitor.model_dump.return_value = {"uuid": "new", "name": "m1"}
        mock_async_client.create_monitor = AsyncMock(return_value=monitor)

        await _call_async(async_server, "create_monitor", name="m1", url="https://example.com")
        mock_async_client.create_monitor.assert_called_once()

    async def test_delete_monitor_async_delegates(self, async_server, mock_async_client):
        from unittest.mock import AsyncMock

        mock_async_client.delete_monitor = AsyncMock(return_value=None)

        result = await _call_async(async_server, "delete_monitor", monitor_id="abc")
        mock_async_client.delete_monitor.assert_called_once_with("abc")
        assert result.get("success") is True

    async def test_search_monitors_by_name_async_delegates(
        self, async_server, mock_async_mcp_client
    ):
        from unittest.mock import AsyncMock

        m = MagicMock()
        m.model_dump.return_value = {"uuid": "abc", "name": "my monitor"}
        mock_async_mcp_client.search_monitors_by_name = AsyncMock(return_value=[m])

        await _call_async(async_server, "search_monitors_by_name", query="my")
        mock_async_mcp_client.search_monitors_by_name.assert_called_once_with("my")

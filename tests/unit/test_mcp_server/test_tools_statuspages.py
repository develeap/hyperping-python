"""Tests for status page tools (T6)."""

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

    return create_mcp_server(client=mock_client, tools=["statuspages"])


class TestStatusPageTools:
    def test_all_statuspage_tools_count(self, server):
        assert len(server._tool_manager.list_tools()) == 8

    def test_list_status_pages_delegates(self, server, mock_client):
        mock_client.list_status_pages.return_value = []
        _call(server, "list_status_pages")
        mock_client.list_status_pages.assert_called_once()

    def test_add_subscriber_delegates(self, server, mock_client):
        subscriber = MagicMock()
        subscriber.model_dump.return_value = {"email": "a@b.com"}
        mock_client.add_subscriber.return_value = subscriber

        _call(server, "add_subscriber", status_page_id="sp1", email="a@b.com")
        mock_client.add_subscriber.assert_called_once_with("sp1", "a@b.com")


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

    return create_mcp_server(client=mock_async_client, tools=["statuspages"])


class TestStatusPageToolsAsync:
    async def test_list_status_pages_async_delegates(self, async_server, mock_async_client):
        from unittest.mock import AsyncMock

        mock_async_client.list_status_pages = AsyncMock(return_value=[])

        await _call_async(async_server, "list_status_pages")
        mock_async_client.list_status_pages.assert_called_once()

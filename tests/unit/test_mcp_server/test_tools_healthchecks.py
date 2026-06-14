"""Tests for healthcheck tools (T7)."""

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

    return create_mcp_server(client=mock_client, tools=["healthchecks"])


class TestHealthcheckTools:
    def test_all_healthcheck_tools_count(self, server):
        assert len(server._tool_manager.list_tools()) == 7

    def test_list_healthchecks_delegates(self, server, mock_client):
        mock_client.list_healthchecks.return_value = []
        _call(server, "list_healthchecks")
        mock_client.list_healthchecks.assert_called_once()

    def test_pause_healthcheck_delegates(self, server, mock_client):
        hc = MagicMock()
        hc.model_dump.return_value = {"uuid": "hc1", "paused": True}
        mock_client.pause_healthcheck.return_value = hc

        _call(server, "pause_healthcheck", healthcheck_id="hc1")
        mock_client.pause_healthcheck.assert_called_once_with("hc1")


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

    return create_mcp_server(client=mock_async_client, tools=["healthchecks"])


class TestHealthcheckToolsAsync:
    async def test_list_healthchecks_async_delegates(self, async_server, mock_async_client):
        from unittest.mock import AsyncMock

        mock_async_client.list_healthchecks = AsyncMock(return_value=[])

        await _call_async(async_server, "list_healthchecks")
        mock_async_client.list_healthchecks.assert_called_once()

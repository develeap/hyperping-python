"""Tests for outage tools (T5)."""

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

    return create_mcp_server(client=mock_client, tools=["outages"])


class TestOutageTools:
    def test_all_outage_tools_count(self, server):
        assert len(server._tool_manager.list_tools()) == 8

    def test_acknowledge_outage_delegates(self, server, mock_client):
        outage = MagicMock()
        outage.model_dump.return_value = {"uuid": "out1"}
        mock_client.acknowledge_outage.return_value = outage

        _call(server, "acknowledge_outage", outage_id="out1")
        mock_client.acknowledge_outage.assert_called_once()

    def test_escalate_outage_delegates(self, server, mock_client):
        outage = MagicMock()
        outage.model_dump.return_value = {"uuid": "out1"}
        mock_client.escalate_outage.return_value = outage

        _call(server, "escalate_outage", outage_id="out1")
        mock_client.escalate_outage.assert_called_once_with("out1")


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

    return create_mcp_server(client=mock_async_client, tools=["outages"])


class TestOutageToolsAsync:
    async def test_list_outages_async_delegates(self, async_server, mock_async_client):
        from unittest.mock import AsyncMock

        mock_async_client.list_outages = AsyncMock(return_value=[])

        await _call_async(async_server, "list_outages")
        mock_async_client.list_outages.assert_called_once()

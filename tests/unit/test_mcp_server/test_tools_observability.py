"""Tests for observability tools (T8)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def _call(server, tool_name, **kwargs):
    """Call a registered tool function by name directly."""
    tool = next(t for t in server._tool_manager.list_tools() if t.name == tool_name)
    return tool.fn(**kwargs)


@pytest.fixture()
def mock_mcp_client():
    from hyperping.mcp_client import HyperpingMcpClient

    return MagicMock(spec=HyperpingMcpClient)


@pytest.fixture()
def server(mock_mcp_client):
    from hyperping.client import HyperpingClient
    from hyperping.mcp_server import create_mcp_server

    mock_client = MagicMock(spec=HyperpingClient)
    return create_mcp_server(
        client=mock_client, mcp_client=mock_mcp_client, tools=["observability"]
    )


class TestObservabilityTools:
    def test_all_observability_tools_count(self, server):
        assert len(server._tool_manager.list_tools()) == 15

    def test_get_status_summary_delegates(self, server, mock_mcp_client):
        summary = MagicMock()
        summary.model_dump.return_value = {"total": 5, "up": 4, "down": 1}
        mock_mcp_client.get_status_summary.return_value = summary

        _call(server, "get_status_summary")
        mock_mcp_client.get_status_summary.assert_called_once()

    def test_list_on_call_schedules_delegates(self, server, mock_mcp_client):
        mock_mcp_client.list_on_call_schedules.return_value = []
        _call(server, "list_on_call_schedules")
        mock_mcp_client.list_on_call_schedules.assert_called_once()

    def test_all_observability_tools_read_only(self, server):
        write_words = {"create", "update", "delete", "post", "put", "patch"}
        for tool in server._tool_manager.list_tools():
            desc = (tool.description or "").lower()
            assert not any(w in desc.split() for w in write_words), (
                f"Observability tool {tool.name!r} description suggests write: {tool.description!r}"
            )

    def test_skipped_when_no_mcp_client(self):
        from hyperping.client import HyperpingClient
        from hyperping.mcp_server import create_mcp_server

        mock_client = MagicMock(spec=HyperpingClient)
        server = create_mcp_server(client=mock_client, tools=["observability"])
        assert len(server._tool_manager.list_tools()) == 0


async def _call_async(server, tool_name, **kwargs):
    tool = next(t for t in server._tool_manager.list_tools() if t.name == tool_name)
    return await tool.fn(**kwargs)


@pytest.fixture()
def mock_async_mcp_client():
    from hyperping._async_mcp_client import AsyncHyperpingMcpClient

    return MagicMock(spec=AsyncHyperpingMcpClient)


@pytest.fixture()
def async_server(mock_async_mcp_client):
    from hyperping.client import HyperpingClient
    from hyperping.mcp_server import create_mcp_server

    mock_client = MagicMock(spec=HyperpingClient)
    return create_mcp_server(
        client=mock_client, mcp_client=mock_async_mcp_client, tools=["observability"]
    )


class TestObservabilityToolsAsync:
    async def test_get_status_summary_async_delegates(self, async_server, mock_async_mcp_client):
        from unittest.mock import AsyncMock

        summary = MagicMock()
        summary.model_dump.return_value = {"total": 5, "up": 4, "down": 1}
        mock_async_mcp_client.get_status_summary = AsyncMock(return_value=summary)

        await _call_async(async_server, "get_status_summary")
        mock_async_mcp_client.get_status_summary.assert_called_once()

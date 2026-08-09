"""Tests for incident tools (T3)."""

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

    return create_mcp_server(client=mock_client, tools=["incidents"])


class TestIncidentTools:
    def test_all_incident_tools_count(self, server):
        assert len(server._tool_manager.list_tools()) == 7

    def test_create_incident_delegates(self, server, mock_client):
        incident = MagicMock()
        incident.model_dump.return_value = {"uuid": "inc1"}
        mock_client.create_incident.return_value = incident

        _call(
            server,
            "create_incident",
            title={"en": "Outage"},
            text={"en": "We are investigating."},
            statuspages=["sp1"],
        )
        mock_client.create_incident.assert_called_once()

    def test_resolve_incident_delegates(self, server, mock_client):
        incident = MagicMock()
        incident.model_dump.return_value = {"uuid": "inc1"}
        mock_client.resolve_incident.return_value = incident

        _call(server, "resolve_incident", incident_id="inc1")
        mock_client.resolve_incident.assert_called_once()

    def test_delete_incident_description_warns(self, server):
        tool = next(t for t in server._tool_manager.list_tools() if t.name == "delete_incident")
        assert tool.description is not None
        lower = tool.description.lower()
        assert "delete" in lower or "this will" in lower

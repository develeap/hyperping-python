"""Tests for ToolAnnotations constants and per-tool annotation coverage."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


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

    return create_mcp_server(client=mock_client, mcp_client=mock_mcp_client)


# ---------------------------------------------------------------------------
# T1: annotation constants have correct hint values
# ---------------------------------------------------------------------------


class TestAnnotationConstants:
    def test_read_only_hints(self):
        from hyperping.mcp_server._annotations import READ_ONLY

        assert READ_ONLY.readOnlyHint is True
        assert READ_ONLY.destructiveHint is False
        assert READ_ONLY.idempotentHint is True
        assert READ_ONLY.openWorldHint is True

    def test_mutating_hints(self):
        from hyperping.mcp_server._annotations import MUTATING

        assert MUTATING.readOnlyHint is False
        assert MUTATING.destructiveHint is False
        assert MUTATING.idempotentHint is True
        assert MUTATING.openWorldHint is True

    def test_destructive_hints(self):
        from hyperping.mcp_server._annotations import DESTRUCTIVE

        assert DESTRUCTIVE.readOnlyHint is False
        assert DESTRUCTIVE.destructiveHint is True
        assert DESTRUCTIVE.idempotentHint is False
        assert DESTRUCTIVE.openWorldHint is True

    def test_action_hints(self):
        from hyperping.mcp_server._annotations import ACTION

        assert ACTION.readOnlyHint is False
        assert ACTION.destructiveHint is True
        assert ACTION.idempotentHint is True
        assert ACTION.openWorldHint is True


# ---------------------------------------------------------------------------
# T2: all registered tools carry annotations
# ---------------------------------------------------------------------------


class TestToolAnnotationCoverage:
    def test_no_unannotated_tools(self, server):
        for tool in server._tool_manager.list_tools():
            assert tool.annotations is not None, f"{tool.name} has no annotations"

    @pytest.mark.parametrize(
        "tool_name",
        [
            "list_monitors",
            "get_monitor",
            "get_all_reports",
            "get_monitor_report",
            "search_monitors_by_name",
            "list_incidents",
            "get_incident",
            "list_maintenance",
            "get_maintenance",
            "get_active_maintenance",
            "is_monitor_in_maintenance",
            "list_outages",
            "get_outage",
            "list_status_pages",
            "get_status_page",
            "list_subscribers",
            "list_healthchecks",
            "get_healthcheck",
            "get_status_summary",
            "get_monitor_response_time",
            "get_monitor_mtta",
            "get_monitor_mttr",
            "get_monitor_anomalies",
            "get_monitor_http_logs",
            "list_recent_alerts",
            "list_on_call_schedules",
            "get_on_call_schedule",
            "list_escalation_policies",
            "get_escalation_policy",
            "list_team_members",
            "list_integrations",
            "get_integration",
            "get_outage_timeline",
        ],
    )
    def test_read_only_tools_have_read_only_annotation(self, server, tool_name):
        tool_map = {t.name: t for t in server._tool_manager.list_tools()}
        assert tool_name in tool_map, f"Tool {tool_name!r} not found in server"
        ann = tool_map[tool_name].annotations
        assert ann is not None
        assert ann.readOnlyHint is True, f"{tool_name}: readOnlyHint should be True"
        assert ann.destructiveHint is False, f"{tool_name}: destructiveHint should be False"

    @pytest.mark.parametrize(
        "tool_name",
        [
            "delete_monitor",
            "resolve_incident",
            "delete_incident",
            "delete_maintenance",
            "escalate_outage",
            "resolve_outage",
            "delete_outage",
            "remove_subscriber",
            "delete_status_page",
            "delete_healthcheck",
        ],
    )
    def test_destructive_tools_have_destructive_annotation(self, server, tool_name):
        tool_map = {t.name: t for t in server._tool_manager.list_tools()}
        assert tool_name in tool_map, f"Tool {tool_name!r} not found in server"
        ann = tool_map[tool_name].annotations
        assert ann is not None
        assert ann.destructiveHint is True, f"{tool_name}: destructiveHint should be True"
        assert ann.idempotentHint is False, f"{tool_name}: idempotentHint should be False"

    @pytest.mark.parametrize(
        "tool_name",
        [
            "pause_monitor",
            "resume_monitor",
            "acknowledge_outage",
            "unacknowledge_outage",
            "pause_healthcheck",
            "resume_healthcheck",
        ],
    )
    def test_action_tools_have_action_annotation(self, server, tool_name):
        tool_map = {t.name: t for t in server._tool_manager.list_tools()}
        assert tool_name in tool_map, f"Tool {tool_name!r} not found in server"
        ann = tool_map[tool_name].annotations
        assert ann is not None
        assert ann.destructiveHint is True, f"{tool_name}: destructiveHint should be True"
        assert ann.idempotentHint is True, f"{tool_name}: idempotentHint should be True"

    @pytest.mark.parametrize(
        "tool_name",
        [
            "create_monitor",
            "update_monitor",
            "create_incident",
            "update_incident",
            "add_incident_update",
            "create_maintenance",
            "update_maintenance",
            "create_outage",
            "create_status_page",
            "update_status_page",
            "add_subscriber",
            "create_healthcheck",
            "update_healthcheck",
        ],
    )
    def test_mutating_tools_have_mutating_annotation(self, server, tool_name):
        tool_map = {t.name: t for t in server._tool_manager.list_tools()}
        assert tool_name in tool_map, f"Tool {tool_name!r} not found in server"
        ann = tool_map[tool_name].annotations
        assert ann is not None
        assert ann.readOnlyHint is False, f"{tool_name}: readOnlyHint should be False"
        assert ann.destructiveHint is False, f"{tool_name}: destructiveHint should be False"


# ---------------------------------------------------------------------------
# T4: annotation constants are importable from package
# ---------------------------------------------------------------------------


class TestAnnotationsImportableFromPackage:
    def test_annotations_importable(self):
        from mcp.types import ToolAnnotations

        from hyperping.mcp_server import ACTION, DESTRUCTIVE, MUTATING, READ_ONLY

        assert isinstance(READ_ONLY, ToolAnnotations)
        assert isinstance(MUTATING, ToolAnnotations)
        assert isinstance(DESTRUCTIVE, ToolAnnotations)
        assert isinstance(ACTION, ToolAnnotations)

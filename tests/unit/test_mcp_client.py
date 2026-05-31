"""Tests for the high-level MCP client."""

from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest
import respx

from hyperping._mcp_transport import MCP_URL
from hyperping.exceptions import HyperpingRateLimitError
from hyperping.mcp_client import HyperpingMcpClient
from hyperping.models._integration_models import Integration
from hyperping.models._monitor_models import Monitor
from hyperping.models._observability_models import MonitorAnomaly, ProbeLogResponse
from hyperping.models._oncall_models import EscalationPolicy, OnCallSchedule, TeamMember
from hyperping.models._outage_models import OutageTimeline
from hyperping.models._reporting_models import (
    AlertHistory,
    MttaReport,
    MttrReport,
    ResponseTimeReport,
    StatusSummary,
)


def make_client() -> HyperpingMcpClient:
    client = HyperpingMcpClient(api_key="sk_test")
    client._transport = MagicMock()
    return client


def test_get_status_summary():
    client = make_client()
    client._transport.call_tool.return_value = {
        "total": 5,
        "up": 3,
        "down": 1,
        "paused": 1,
        "unknown": 0,
    }
    result = client.get_status_summary()
    assert isinstance(result, StatusSummary)
    assert result.total == 5
    client._transport.call_tool.assert_called_once_with("get_status_summary", {})


def test_list_on_call_schedules():
    client = make_client()
    client._transport.call_tool.return_value = {
        "schedules": [{"uuid": "s1", "name": "Primary"}],
    }
    result = client.list_on_call_schedules()
    assert len(result) == 1
    assert isinstance(result[0], OnCallSchedule)
    client._transport.call_tool.assert_called_once_with("list_on_call_schedules", {})


def test_list_team_members_bare_array():
    client = make_client()
    client._transport.call_tool.return_value = [
        {"uuid": "u1", "email": "a@b.com", "name": "A"},
    ]
    result = client.list_team_members()
    assert len(result) == 1
    assert isinstance(result[0], TeamMember)
    assert result[0].email == "a@b.com"
    client._transport.call_tool.assert_called_once_with("list_team_members", {})


def test_search_monitors():
    client = make_client()
    client._transport.call_tool.return_value = [
        {"uuid": "m1", "name": "API", "url": "https://api.example.com", "protocol": "http"},
    ]
    result = client.search_monitors_by_name("API")
    assert len(result) == 1
    assert isinstance(result[0], Monitor)
    client._transport.call_tool.assert_called_once_with("search_monitors_by_name", {"query": "API"})


def test_get_outage_timeline():
    client = make_client()
    client._transport.call_tool.return_value = {
        "outage": {"uuid": "o1"},
        "monitor": {"uuid": "m1"},
        "escalationPolicy": None,
        "timeline": [{"type": "detected", "timestamp": "2026-01-01T00:00:00Z"}],
    }
    result = client.get_outage_timeline("outage_123")
    assert isinstance(result, OutageTimeline)
    assert len(result.timeline) == 1
    client._transport.call_tool.assert_called_once_with(
        "get_outage_timeline", {"uuid": "outage_123"}
    )


def test_get_monitor_anomalies():
    client = make_client()
    client._transport.call_tool.return_value = {
        "anomalies": [
            {
                "id": 1,
                "timestamp": "2026-01-01",
                "type": "flapping",
                "value": 0.5,
                "baseline": 0,
                "score": 0.5,
            }
        ],
    }
    result = client.get_monitor_anomalies("mon_123")
    assert len(result) == 1
    assert isinstance(result[0], MonitorAnomaly)
    client._transport.call_tool.assert_called_once_with(
        "get_monitor_anomalies", {"uuid": "mon_123"}
    )


def test_context_manager():
    with HyperpingMcpClient(api_key="sk_test") as client:
        assert client is not None


def test_get_monitor_response_time():
    client = make_client()
    client._transport.call_tool.return_value = {
        "timeGroups": [{"time": "2026-01-01", "avgResponseTime": 120, "count": 10}],
    }
    result = client.get_monitor_response_time("mon_1")
    assert isinstance(result, ResponseTimeReport)
    assert result.time_groups[0].avg_response_time == 120
    client._transport.call_tool.assert_called_once_with(
        "get_monitor_response_time", {"uuid": "mon_1"}
    )


def test_get_monitor_mtta_with_uuid():
    client = make_client()
    client._transport.call_tool.return_value = {
        "monitors": [],
        "totalAcknowledged": 0,
        "mtta": 45,
    }
    result = client.get_monitor_mtta(monitor_uuid="mon_1")
    assert isinstance(result, MttaReport)
    assert result.mtta == 45
    client._transport.call_tool.assert_called_once_with("get_monitor_mtta", {"uuid": "mon_1"})


def test_get_monitor_mtta_without_uuid():
    client = make_client()
    client._transport.call_tool.return_value = {
        "monitors": [],
        "totalAcknowledged": 0,
        "mtta": 60,
    }
    result = client.get_monitor_mtta()
    assert isinstance(result, MttaReport)
    client._transport.call_tool.assert_called_once_with("get_monitor_mtta", {})


def test_get_monitor_mttr():
    client = make_client()
    client._transport.call_tool.return_value = {
        "monitors": [],
        "totalOutages": 1,
        "totalOutagesLength": 90,
        "mttr": 90,
        "mtta": 0,
    }
    result = client.get_monitor_mttr(monitor_uuid="mon_1")
    assert isinstance(result, MttrReport)
    assert result.mttr == 90
    client._transport.call_tool.assert_called_once_with("get_monitor_mttr", {"uuid": "mon_1"})


def test_get_monitor_http_logs():
    client = make_client()
    client._transport.call_tool.return_value = {
        "pings": [
            {
                "statusCode": 200,
                "elapsedTime": 5,
                "location": "nyc",
                "date": "2026-01-01",
                "isError": 0,
                "continent": "na",
                "bytes": 100,
                "headers": "",
                "id": "log1",
            }
        ],
        "anomalies": [],
        "pagination": {},
        "totals": {},
    }
    result = client.get_monitor_http_logs("mon_1")
    assert isinstance(result, ProbeLogResponse)
    assert result.pings[0].status_code == 200
    client._transport.call_tool.assert_called_once_with("get_monitor_http_logs", {"uuid": "mon_1"})


def test_list_recent_alerts():
    client = make_client()
    client._transport.call_tool.return_value = {
        "timeGroups": [{"time": "2026-01-01", "count": 3}],
    }
    result = client.list_recent_alerts()
    assert isinstance(result, AlertHistory)
    client._transport.call_tool.assert_called_once_with("list_recent_alerts", {})


def test_get_on_call_schedule():
    client = make_client()
    client._transport.call_tool.return_value = {"uuid": "s1", "name": "Primary"}
    result = client.get_on_call_schedule("s1")
    assert isinstance(result, OnCallSchedule)
    client._transport.call_tool.assert_called_once_with("get_on_call_schedule", {"uuid": "s1"})


def test_list_escalation_policies():
    client = make_client()
    client._transport.call_tool.return_value = [
        {"uuid": "ep1", "name": "Default", "steps": []},
    ]
    result = client.list_escalation_policies()
    assert len(result) == 1
    assert isinstance(result[0], EscalationPolicy)
    client._transport.call_tool.assert_called_once_with("list_escalation_policies", {})


def test_get_escalation_policy():
    client = make_client()
    client._transport.call_tool.return_value = {
        "uuid": "ep1",
        "name": "Default",
        "steps": [],
    }
    result = client.get_escalation_policy("ep1")
    assert isinstance(result, EscalationPolicy)
    client._transport.call_tool.assert_called_once_with("get_escalation_policy", {"uuid": "ep1"})


def test_list_integrations():
    client = make_client()
    client._transport.call_tool.return_value = [
        {"uuid": "int1", "name": "Slack", "type": "slack", "active": True},
    ]
    result = client.list_integrations()
    assert len(result) == 1
    assert isinstance(result[0], Integration)
    client._transport.call_tool.assert_called_once_with("list_integrations", {})


def test_get_integration():
    client = make_client()
    client._transport.call_tool.return_value = {
        "uuid": "int1",
        "name": "Slack",
        "type": "slack",
        "active": True,
    }
    result = client.get_integration("int1")
    assert isinstance(result, Integration)
    client._transport.call_tool.assert_called_once_with("get_integration", {"uuid": "int1"})


# -- ensure_initialized() (Task 9 / Tests 14, 15) ----------------------------


def test_ensure_initialized_delegates_to_transport():
    client = make_client()
    client.ensure_initialized()
    client._transport.initialize.assert_called_once_with()


def test_ensure_initialized_propagates_rate_limit():
    client = make_client()
    client._transport.initialize.side_effect = HyperpingRateLimitError(
        "rate limited on initialize", retry_after=30, status_code=200,
    )
    with pytest.raises(HyperpingRateLimitError) as exc_info:
        client.ensure_initialized()
    assert exc_info.value.retry_after == 30
    assert exc_info.value.status_code == 200


@respx.mock
def test_ensure_initialized_real_transport_is_idempotent():
    """Calling ensure_initialized twice through the real transport POSTs only once."""
    route = respx.post(MCP_URL).mock(
        side_effect=[
            httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-03-26"}},
            ),
            httpx.Response(202),
        ],
    )
    client = HyperpingMcpClient(api_key="sk_test", base_url=MCP_URL)
    client.ensure_initialized()
    client.ensure_initialized()
    assert route.call_count == 2  # one initialize, one notification
    client.close()


# -- Docs artifact gate (Task 10/11 / Test 30) -------------------------------


def _repo_root() -> Path:
    # tests/unit/test_mcp_client.py -> repo root
    return Path(__file__).resolve().parents[2]


def test_readme_contains_mcp_rate_limits_section():
    """README must document the MCP rate limit guidance shipped in this change."""
    readme = (_repo_root() / "README.md").read_text(encoding="utf-8")
    assert "### MCP rate limits and connection lifecycle" in readme, (
        "README is missing the 'MCP rate limits and connection lifecycle' section"
    )


def test_changelog_documents_mcp_rate_limit_work():
    """CHANGELOG must continue to document the MCP rate-limit work shipped in
    v1.7.0 (ensure_initialized, JSON-RPC -32000 classification, README guidance).
    Scans the entire file so subsequent releases that roll the top section over
    do not silently drop the historical entry.
    """
    changelog = (_repo_root() / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "ensure_initialized" in changelog, (
        "CHANGELOG must mention ensure_initialized() somewhere"
    )
    assert "rate limit" in changelog.lower(), (
        "CHANGELOG must mention rate-limit handling somewhere"
    )

"""Tests for the high-level MCP client."""

from unittest.mock import MagicMock

from hyperping.mcp_client import HyperpingMcpClient


def make_client() -> HyperpingMcpClient:
    client = HyperpingMcpClient(api_key="sk_test")
    client._transport = MagicMock()
    return client


def test_get_status_summary():
    client = make_client()
    client._transport.call_tool.return_value = {"total": 5, "up": 3, "down": 1, "paused": 1}
    result = client.get_status_summary()
    assert result["total"] == 5
    client._transport.call_tool.assert_called_once_with("get_status_summary", {})


def test_list_on_call_schedules():
    client = make_client()
    client._transport.call_tool.return_value = [{"uuid": "s1", "name": "Primary"}]
    result = client.list_on_call_schedules()
    assert len(result) == 1
    assert result[0]["uuid"] == "s1"
    client._transport.call_tool.assert_called_once_with("list_on_call_schedules", {})


def test_list_team_members_bare_array():
    client = make_client()
    client._transport.call_tool.return_value = [{"uuid": "u1", "email": "a@b.com"}]
    result = client.list_team_members()
    assert len(result) == 1
    client._transport.call_tool.assert_called_once_with("list_team_members", {})


def test_search_monitors():
    client = make_client()
    client._transport.call_tool.return_value = [{"uuid": "m1", "name": "API"}]
    result = client.search_monitors_by_name("API")
    assert len(result) == 1
    client._transport.call_tool.assert_called_once_with("search_monitors_by_name", {"query": "API"})


def test_get_outage_timeline():
    client = make_client()
    client._transport.call_tool.return_value = {
        "events": [{"type": "detected", "timestamp": "2026-01-01T00:00:00Z"}]
    }
    result = client.get_outage_timeline("outage_123")
    assert "events" in result
    client._transport.call_tool.assert_called_once_with(
        "get_outage_timeline", {"uuid": "outage_123"}
    )


def test_get_monitor_anomalies():
    client = make_client()
    client._transport.call_tool.return_value = [{"type": "flapping", "startedAt": "2026-01-01"}]
    result = client.get_monitor_anomalies("mon_123")
    assert len(result) == 1
    client._transport.call_tool.assert_called_once_with(
        "get_monitor_anomalies", {"uuid": "mon_123"}
    )


def test_context_manager():
    with HyperpingMcpClient(api_key="sk_test") as client:
        assert client is not None


def test_get_monitor_response_time():
    client = make_client()
    client._transport.call_tool.return_value = {"p50": 120, "p95": 350}
    result = client.get_monitor_response_time("mon_1")
    assert result["p50"] == 120
    client._transport.call_tool.assert_called_once_with(
        "get_monitor_response_time", {"uuid": "mon_1"}
    )


def test_get_monitor_mtta_with_uuid():
    client = make_client()
    client._transport.call_tool.return_value = {"mtta": 45}
    result = client.get_monitor_mtta(monitor_uuid="mon_1")
    assert result["mtta"] == 45
    client._transport.call_tool.assert_called_once_with("get_monitor_mtta", {"uuid": "mon_1"})


def test_get_monitor_mtta_without_uuid():
    client = make_client()
    client._transport.call_tool.return_value = {"mtta": 60}
    result = client.get_monitor_mtta()
    assert result["mtta"] == 60
    client._transport.call_tool.assert_called_once_with("get_monitor_mtta", {})


def test_get_monitor_mttr():
    client = make_client()
    client._transport.call_tool.return_value = {"mttr": 90}
    result = client.get_monitor_mttr(monitor_uuid="mon_1")
    assert result["mttr"] == 90
    client._transport.call_tool.assert_called_once_with("get_monitor_mttr", {"uuid": "mon_1"})


def test_get_monitor_http_logs():
    client = make_client()
    client._transport.call_tool.return_value = [{"status": 200, "latency": 123}]
    result = client.get_monitor_http_logs("mon_1")
    assert len(result) == 1
    client._transport.call_tool.assert_called_once_with("get_monitor_http_logs", {"uuid": "mon_1"})


def test_list_recent_alerts():
    client = make_client()
    client._transport.call_tool.return_value = {"alerts": [{"uuid": "a1"}]}
    result = client.list_recent_alerts()
    assert "alerts" in result
    client._transport.call_tool.assert_called_once_with("list_recent_alerts", {})


def test_get_on_call_schedule():
    client = make_client()
    client._transport.call_tool.return_value = {"uuid": "s1", "name": "Primary"}
    result = client.get_on_call_schedule("s1")
    assert result["uuid"] == "s1"
    client._transport.call_tool.assert_called_once_with("get_on_call_schedule", {"uuid": "s1"})


def test_list_escalation_policies():
    client = make_client()
    client._transport.call_tool.return_value = [{"uuid": "ep1"}]
    result = client.list_escalation_policies()
    assert len(result) == 1
    client._transport.call_tool.assert_called_once_with("list_escalation_policies", {})


def test_get_escalation_policy():
    client = make_client()
    client._transport.call_tool.return_value = {"uuid": "ep1", "name": "Default"}
    result = client.get_escalation_policy("ep1")
    assert result["uuid"] == "ep1"
    client._transport.call_tool.assert_called_once_with("get_escalation_policy", {"uuid": "ep1"})


def test_list_integrations():
    client = make_client()
    client._transport.call_tool.return_value = [{"uuid": "int1", "type": "slack"}]
    result = client.list_integrations()
    assert len(result) == 1
    client._transport.call_tool.assert_called_once_with("list_integrations", {})


def test_get_integration():
    client = make_client()
    client._transport.call_tool.return_value = {"uuid": "int1", "type": "slack"}
    result = client.get_integration("int1")
    assert result["uuid"] == "int1"
    client._transport.call_tool.assert_called_once_with("get_integration", {"uuid": "int1"})

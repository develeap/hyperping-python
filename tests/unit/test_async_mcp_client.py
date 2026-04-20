"""Tests for the async high-level MCP client."""

from unittest.mock import AsyncMock

import pytest

from hyperping._async_mcp_client import AsyncHyperpingMcpClient
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


def make_client() -> AsyncHyperpingMcpClient:
    client = AsyncHyperpingMcpClient(api_key="sk_test")
    client._transport = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_get_status_summary():
    client = make_client()
    client._transport.call_tool.return_value = {
        "total": 5,
        "up": 3,
        "down": 1,
        "paused": 1,
        "unknown": 0,
    }
    result = await client.get_status_summary()
    assert isinstance(result, StatusSummary)
    assert result.total == 5
    client._transport.call_tool.assert_called_once_with("get_status_summary", {})


@pytest.mark.asyncio
async def test_list_on_call_schedules():
    client = make_client()
    client._transport.call_tool.return_value = {
        "schedules": [{"uuid": "s1", "name": "Primary"}],
    }
    result = await client.list_on_call_schedules()
    assert len(result) == 1
    assert isinstance(result[0], OnCallSchedule)
    client._transport.call_tool.assert_called_once_with("list_on_call_schedules", {})


@pytest.mark.asyncio
async def test_list_team_members_bare_array():
    client = make_client()
    client._transport.call_tool.return_value = [
        {"uuid": "u1", "email": "a@b.com", "name": "A"},
    ]
    result = await client.list_team_members()
    assert len(result) == 1
    assert isinstance(result[0], TeamMember)
    assert result[0].email == "a@b.com"
    client._transport.call_tool.assert_called_once_with("list_team_members", {})


@pytest.mark.asyncio
async def test_search_monitors():
    client = make_client()
    client._transport.call_tool.return_value = [
        {
            "uuid": "m1",
            "name": "API",
            "url": "https://api.example.com",
            "protocol": "http",
        },
    ]
    result = await client.search_monitors_by_name("API")
    assert len(result) == 1
    assert isinstance(result[0], Monitor)
    client._transport.call_tool.assert_called_once_with("search_monitors_by_name", {"query": "API"})


@pytest.mark.asyncio
async def test_get_outage_timeline():
    client = make_client()
    client._transport.call_tool.return_value = {
        "outage": {"uuid": "o1"},
        "monitor": {"uuid": "m1"},
        "escalationPolicy": None,
        "timeline": [{"type": "detected", "timestamp": "2026-01-01T00:00:00Z"}],
    }
    result = await client.get_outage_timeline("outage_123")
    assert isinstance(result, OutageTimeline)
    assert len(result.timeline) == 1
    client._transport.call_tool.assert_called_once_with(
        "get_outage_timeline", {"uuid": "outage_123"}
    )


@pytest.mark.asyncio
async def test_get_monitor_anomalies():
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
    result = await client.get_monitor_anomalies("mon_123")
    assert len(result) == 1
    assert isinstance(result[0], MonitorAnomaly)
    client._transport.call_tool.assert_called_once_with(
        "get_monitor_anomalies", {"uuid": "mon_123"}
    )


@pytest.mark.asyncio
async def test_context_manager():
    async with AsyncHyperpingMcpClient(api_key="sk_test") as client:
        assert client is not None


@pytest.mark.asyncio
async def test_get_monitor_response_time():
    client = make_client()
    client._transport.call_tool.return_value = {
        "timeGroups": [{"time": "2026-01-01", "avgResponseTime": 120, "count": 10}],
    }
    result = await client.get_monitor_response_time("mon_1")
    assert isinstance(result, ResponseTimeReport)
    assert result.time_groups[0].avg_response_time == 120
    client._transport.call_tool.assert_called_once_with(
        "get_monitor_response_time", {"uuid": "mon_1"}
    )


@pytest.mark.asyncio
async def test_get_monitor_mtta_with_uuid():
    client = make_client()
    client._transport.call_tool.return_value = {
        "monitors": [],
        "totalAcknowledged": 0,
        "mtta": 45,
    }
    result = await client.get_monitor_mtta(monitor_uuid="mon_1")
    assert isinstance(result, MttaReport)
    assert result.mtta == 45
    client._transport.call_tool.assert_called_once_with("get_monitor_mtta", {"uuid": "mon_1"})


@pytest.mark.asyncio
async def test_get_monitor_mtta_without_uuid():
    client = make_client()
    client._transport.call_tool.return_value = {
        "monitors": [],
        "totalAcknowledged": 0,
        "mtta": 60,
    }
    result = await client.get_monitor_mtta()
    assert isinstance(result, MttaReport)
    client._transport.call_tool.assert_called_once_with("get_monitor_mtta", {})


@pytest.mark.asyncio
async def test_get_monitor_mttr():
    client = make_client()
    client._transport.call_tool.return_value = {
        "monitors": [],
        "totalOutages": 1,
        "totalOutagesLength": 90,
        "mttr": 90,
        "mtta": 0,
    }
    result = await client.get_monitor_mttr(monitor_uuid="mon_1")
    assert isinstance(result, MttrReport)
    assert result.mttr == 90
    client._transport.call_tool.assert_called_once_with("get_monitor_mttr", {"uuid": "mon_1"})


@pytest.mark.asyncio
async def test_get_monitor_http_logs():
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
    result = await client.get_monitor_http_logs("mon_1")
    assert isinstance(result, ProbeLogResponse)
    assert result.pings[0].status_code == 200
    client._transport.call_tool.assert_called_once_with("get_monitor_http_logs", {"uuid": "mon_1"})


@pytest.mark.asyncio
async def test_list_recent_alerts():
    client = make_client()
    client._transport.call_tool.return_value = {
        "timeGroups": [{"time": "2026-01-01", "count": 3}],
    }
    result = await client.list_recent_alerts()
    assert isinstance(result, AlertHistory)
    client._transport.call_tool.assert_called_once_with("list_recent_alerts", {})


@pytest.mark.asyncio
async def test_get_on_call_schedule():
    client = make_client()
    client._transport.call_tool.return_value = {"uuid": "s1", "name": "Primary"}
    result = await client.get_on_call_schedule("s1")
    assert isinstance(result, OnCallSchedule)
    client._transport.call_tool.assert_called_once_with("get_on_call_schedule", {"uuid": "s1"})


@pytest.mark.asyncio
async def test_list_escalation_policies():
    client = make_client()
    client._transport.call_tool.return_value = [
        {"uuid": "ep1", "name": "Default", "steps": []},
    ]
    result = await client.list_escalation_policies()
    assert len(result) == 1
    assert isinstance(result[0], EscalationPolicy)
    client._transport.call_tool.assert_called_once_with("list_escalation_policies", {})


@pytest.mark.asyncio
async def test_get_escalation_policy():
    client = make_client()
    client._transport.call_tool.return_value = {
        "uuid": "ep1",
        "name": "Default",
        "steps": [],
    }
    result = await client.get_escalation_policy("ep1")
    assert isinstance(result, EscalationPolicy)
    client._transport.call_tool.assert_called_once_with("get_escalation_policy", {"uuid": "ep1"})


@pytest.mark.asyncio
async def test_list_integrations():
    client = make_client()
    client._transport.call_tool.return_value = [
        {"uuid": "int1", "name": "Slack", "type": "slack", "active": True},
    ]
    result = await client.list_integrations()
    assert len(result) == 1
    assert isinstance(result[0], Integration)
    client._transport.call_tool.assert_called_once_with("list_integrations", {})


@pytest.mark.asyncio
async def test_get_integration():
    client = make_client()
    client._transport.call_tool.return_value = {
        "uuid": "int1",
        "name": "Slack",
        "type": "slack",
        "active": True,
    }
    result = await client.get_integration("int1")
    assert isinstance(result, Integration)
    client._transport.call_tool.assert_called_once_with("get_integration", {"uuid": "int1"})

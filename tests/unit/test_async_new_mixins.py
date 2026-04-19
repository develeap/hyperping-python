"""Tests for new async mixins: reporting, observability, on-call, integrations."""

import httpx
import pytest
import pytest_asyncio
import respx

from hyperping._async_client import AsyncHyperpingClient
from hyperping.client import RetryConfig
from hyperping.endpoints import API_BASE, Endpoint


@pytest_asyncio.fixture
async def async_client():
    """Async client with retries disabled."""
    client = AsyncHyperpingClient(
        api_key="sk_test_key",
        base_url=API_BASE,
        retry_config=RetryConfig(max_retries=0),
    )
    yield client
    await client.close()


# ==================== Reporting ====================


class TestAsyncReporting:
    @respx.mock
    @pytest.mark.asyncio
    async def test_get_status_summary(self, async_client):
        respx.get(f"{API_BASE}{Endpoint.STATUS_SUMMARY}").mock(
            return_value=httpx.Response(
                200,
                json={
                    "totalMonitors": 10,
                    "upCount": 8,
                    "downCount": 1,
                    "pausedCount": 1,
                },
            )
        )
        result = await async_client.get_status_summary()
        assert result.total_monitors == 10
        assert result.up_count == 8

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_monitor_response_time(self, async_client):
        respx.get(f"{API_BASE}/v2/reporting/response-time/mon_1").mock(
            return_value=httpx.Response(200, json={"p50": 45.0, "p95": 120.0})
        )
        result = await async_client.get_monitor_response_time("mon_1")
        assert result["p50"] == 45.0

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_monitor_mtta(self, async_client):
        respx.get(f"{API_BASE}/v2/reporting/mtta/mon_1").mock(
            return_value=httpx.Response(200, json={"mtta_seconds": 120.0})
        )
        result = await async_client.get_monitor_mtta("mon_1")
        assert result["mtta_seconds"] == 120.0


# ==================== Observability ====================


class TestAsyncObservability:
    @respx.mock
    @pytest.mark.asyncio
    async def test_get_monitor_anomalies(self, async_client):
        respx.get(f"{API_BASE}{Endpoint.MONITORS}/mon_1/anomalies").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "anomalyType": "flapping",
                        "startedAt": "2026-01-01T00:00:00Z",
                        "severity": "warning",
                    }
                ],
            )
        )
        result = await async_client.get_monitor_anomalies("mon_1")
        assert len(result) == 1
        assert result[0].anomaly_type == "flapping"

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_monitor_http_logs(self, async_client):
        respx.get(f"{API_BASE}{Endpoint.MONITORS}/mon_1/http-logs").mock(
            return_value=httpx.Response(
                200,
                json=[{"status": 200, "location": "london", "responseTimeMs": 45.2}],
            )
        )
        result = await async_client.get_monitor_http_logs("mon_1")
        assert len(result) == 1
        assert result[0].response_time_ms == 45.2

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_recent_alerts(self, async_client):
        respx.get(f"{API_BASE}{Endpoint.ALERTS}").mock(
            return_value=httpx.Response(
                200,
                json=[{"uuid": "a1", "channel": "slack", "sentAt": "2026-01-01T00:00:00Z"}],
            )
        )
        result = await async_client.list_recent_alerts()
        assert len(result) == 1
        assert result[0].channel == "slack"


# ==================== On-call ====================


class TestAsyncOnCall:
    @respx.mock
    @pytest.mark.asyncio
    async def test_list_on_call_schedules(self, async_client):
        respx.get(f"{API_BASE}{Endpoint.ON_CALL_SCHEDULES}").mock(
            return_value=httpx.Response(
                200,
                json=[{"uuid": "s1", "name": "Primary", "currentOnCall": "alice"}],
            )
        )
        result = await async_client.list_on_call_schedules()
        assert len(result) == 1
        assert result[0].current_on_call == "alice"

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_on_call_schedule(self, async_client):
        respx.get(f"{API_BASE}{Endpoint.ON_CALL_SCHEDULES}/s1").mock(
            return_value=httpx.Response(
                200,
                json={"uuid": "s1", "name": "Primary", "currentOnCall": "bob"},
            )
        )
        result = await async_client.get_on_call_schedule("s1")
        assert result.current_on_call == "bob"

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_escalation_policies(self, async_client):
        respx.get(f"{API_BASE}{Endpoint.ESCALATION_POLICIES}").mock(
            return_value=httpx.Response(
                200, json=[{"uuid": "p1", "name": "Default", "steps": []}]
            )
        )
        result = await async_client.list_escalation_policies()
        assert len(result) == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_escalation_policy(self, async_client):
        respx.get(f"{API_BASE}{Endpoint.ESCALATION_POLICIES}/p1").mock(
            return_value=httpx.Response(
                200, json={"uuid": "p1", "name": "Tiered", "steps": [{"level": 1}]}
            )
        )
        result = await async_client.get_escalation_policy("p1")
        assert result.name == "Tiered"

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_team_members(self, async_client):
        respx.get(f"{API_BASE}{Endpoint.TEAM_MEMBERS}").mock(
            return_value=httpx.Response(
                200, json=[{"name": "Alice", "email": "alice@example.com"}]
            )
        )
        result = await async_client.list_team_members()
        assert len(result) == 1
        assert result[0]["name"] == "Alice"


# ==================== Integrations ====================


class TestAsyncIntegrations:
    @respx.mock
    @pytest.mark.asyncio
    async def test_list_integrations(self, async_client):
        respx.get(f"{API_BASE}{Endpoint.INTEGRATIONS}").mock(
            return_value=httpx.Response(
                200,
                json=[{"uuid": "i1", "name": "Slack", "type": "slack", "active": True}],
            )
        )
        result = await async_client.list_integrations()
        assert len(result) == 1
        assert result[0].integration_type == "slack"

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_integration(self, async_client):
        respx.get(f"{API_BASE}{Endpoint.INTEGRATIONS}/i1").mock(
            return_value=httpx.Response(
                200,
                json={"uuid": "i1", "name": "PD", "type": "pagerduty", "active": False},
            )
        )
        result = await async_client.get_integration("i1")
        assert result.integration_type == "pagerduty"
        assert result.active is False


# ==================== Async outage/monitor extensions ====================


class TestAsyncOutageExtensions:
    @respx.mock
    @pytest.mark.asyncio
    async def test_get_outage_timeline(self, async_client):
        respx.get(f"{API_BASE}{Endpoint.OUTAGES}/out_1/timeline").mock(
            return_value=httpx.Response(
                200,
                json={
                    "events": [
                        {
                            "eventType": "detection",
                            "timestamp": "2026-01-01T00:00:00Z",
                            "detail": "Probe failed",
                        }
                    ]
                },
            )
        )
        result = await async_client.get_outage_timeline("out_1")
        assert result.outage_uuid == "out_1"
        assert len(result.events) == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_monitor_outages(self, async_client):
        respx.get(f"{API_BASE}{Endpoint.OUTAGES}").mock(
            return_value=httpx.Response(
                200, json=[{"uuid": "out_1", "monitorUuid": "mon_1"}]
            )
        )
        result = await async_client.get_monitor_outages("mon_1")
        assert len(result) == 1


class TestAsyncMonitorExtensions:
    @respx.mock
    @pytest.mark.asyncio
    async def test_search_monitors_by_name(self, async_client):
        respx.get(f"{API_BASE}{Endpoint.MONITORS}/search").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "uuid": "mon_1",
                        "name": "API Monitor",
                        "url": "https://api.example.com",
                        "down": False,
                        "paused": False,
                    }
                ],
            )
        )
        result = await async_client.search_monitors_by_name("API")
        assert len(result) == 1
        assert result[0].name == "API Monitor"

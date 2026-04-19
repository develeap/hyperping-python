"""Tests for observability mixin API methods."""

import httpx
import pytest
import respx

from hyperping.client import HyperpingClient
from hyperping.endpoints import API_BASE, Endpoint
from hyperping.models._observability_models import (
    AlertNotification,
    MonitorAnomaly,
    ProbeLog,
)


class TestGetMonitorAnomalies:
    """Tests for get_monitor_anomalies()."""

    @respx.mock
    def test_success(self, client: HyperpingClient) -> None:
        """Test successful anomaly retrieval."""
        mock_response = [
            {
                "anomalyType": "flapping",
                "startedAt": "2026-01-01T00:00:00Z",
                "severity": "warning",
            }
        ]
        respx.get(f"{API_BASE}{Endpoint.MONITORS}/uuid_1/anomalies").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        result = client.get_monitor_anomalies("uuid_1")

        assert len(result) == 1
        assert isinstance(result[0], MonitorAnomaly)
        assert result[0].anomaly_type == "flapping"
        assert result[0].started_at == "2026-01-01T00:00:00Z"
        assert result[0].severity == "warning"

    @respx.mock
    def test_empty_returns_empty_list(self, client: HyperpingClient) -> None:
        """Test that an empty response returns an empty list."""
        respx.get(f"{API_BASE}{Endpoint.MONITORS}/uuid_1/anomalies").mock(
            return_value=httpx.Response(200, json=[])
        )

        result = client.get_monitor_anomalies("uuid_1")
        assert result == []

    @respx.mock
    def test_404_returns_empty_list(self, client: HyperpingClient) -> None:
        """Test that 404 returns empty list instead of raising."""
        respx.get(f"{API_BASE}{Endpoint.MONITORS}/uuid_nope/anomalies").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )

        result = client.get_monitor_anomalies("uuid_nope")
        assert result == []

    def test_invalid_id_raises_value_error(self, client: HyperpingClient) -> None:
        """Test that an invalid ID raises ValueError."""
        with pytest.raises(ValueError, match="Invalid monitor_uuid"):
            client.get_monitor_anomalies("../bad")


class TestGetMonitorHttpLogs:
    """Tests for get_monitor_http_logs()."""

    @respx.mock
    def test_success(self, client: HyperpingClient) -> None:
        """Test successful HTTP log retrieval."""
        mock_response = [
            {
                "status": 200,
                "location": "london",
                "responseTimeMs": 45.2,
            }
        ]
        respx.get(f"{API_BASE}{Endpoint.MONITORS}/uuid_1/http-logs").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        result = client.get_monitor_http_logs("uuid_1")

        assert len(result) == 1
        assert isinstance(result[0], ProbeLog)
        assert result[0].status == 200
        assert result[0].location == "london"
        assert result[0].response_time_ms == 45.2

    @respx.mock
    def test_with_level_param(self, client: HyperpingClient) -> None:
        """Test that level param is forwarded in query string."""
        respx.get(f"{API_BASE}{Endpoint.MONITORS}/uuid_1/http-logs").mock(
            return_value=httpx.Response(200, json=[])
        )

        client.get_monitor_http_logs("uuid_1", level="error")

        request = respx.calls.last.request
        assert "level=error" in str(request.url)

    @respx.mock
    def test_empty_returns_empty_list(self, client: HyperpingClient) -> None:
        """Test that an empty response returns an empty list."""
        respx.get(f"{API_BASE}{Endpoint.MONITORS}/uuid_1/http-logs").mock(
            return_value=httpx.Response(200, json=[])
        )

        result = client.get_monitor_http_logs("uuid_1")
        assert result == []

    @respx.mock
    def test_404_returns_empty_list(self, client: HyperpingClient) -> None:
        """Test that 404 returns empty list instead of raising."""
        respx.get(f"{API_BASE}{Endpoint.MONITORS}/uuid_nope/http-logs").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )

        result = client.get_monitor_http_logs("uuid_nope")
        assert result == []

    def test_invalid_id_raises_value_error(self, client: HyperpingClient) -> None:
        """Test that an invalid ID raises ValueError."""
        with pytest.raises(ValueError, match="Invalid monitor_uuid"):
            client.get_monitor_http_logs("../bad")


class TestListRecentAlerts:
    """Tests for list_recent_alerts()."""

    @respx.mock
    def test_success(self, client: HyperpingClient) -> None:
        """Test successful alert listing."""
        mock_response = [
            {
                "uuid": "a1",
                "channel": "slack",
                "sentAt": "2026-01-01T00:00:00Z",
            }
        ]
        respx.get(f"{API_BASE}{Endpoint.ALERTS}").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        result = client.list_recent_alerts()

        assert len(result) == 1
        assert isinstance(result[0], AlertNotification)
        assert result[0].uuid == "a1"
        assert result[0].channel == "slack"
        assert result[0].sent_at == "2026-01-01T00:00:00Z"

    @respx.mock
    def test_with_time_params(self, client: HyperpingClient) -> None:
        """Test that from_dt and to_dt are forwarded as query params."""
        respx.get(f"{API_BASE}{Endpoint.ALERTS}").mock(
            return_value=httpx.Response(200, json=[])
        )

        client.list_recent_alerts(
            from_dt="2026-01-01T00:00:00Z",
            to_dt="2026-01-31T23:59:59Z",
        )

        request = respx.calls.last.request
        url_str = str(request.url)
        assert "from=2026-01-01" in url_str
        assert "to=2026-01-31" in url_str

    @respx.mock
    def test_with_monitor_uuids(self, client: HyperpingClient) -> None:
        """Test that monitor_uuids are comma-joined in query params."""
        respx.get(f"{API_BASE}{Endpoint.ALERTS}").mock(
            return_value=httpx.Response(200, json=[])
        )

        client.list_recent_alerts(monitor_uuids=["mon_1", "mon_2"])

        request = respx.calls.last.request
        url_str = str(request.url)
        assert "monitor_uuids=mon_1" in url_str or "monitor_uuids=mon_1%2Cmon_2" in url_str

    @respx.mock
    def test_empty_returns_empty_list(self, client: HyperpingClient) -> None:
        """Test that an empty response returns an empty list."""
        respx.get(f"{API_BASE}{Endpoint.ALERTS}").mock(
            return_value=httpx.Response(200, json=[])
        )

        result = client.list_recent_alerts()
        assert result == []

    @respx.mock
    def test_404_returns_empty_list(self, client: HyperpingClient) -> None:
        """Test that 404 returns empty list instead of raising."""
        respx.get(f"{API_BASE}{Endpoint.ALERTS}").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )

        result = client.list_recent_alerts()
        assert result == []

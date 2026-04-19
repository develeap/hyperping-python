"""Tests for reporting mixin API methods."""

import httpx
import pytest
import respx

from hyperping.client import HyperpingClient
from hyperping.endpoints import API_BASE, Endpoint
from hyperping.exceptions import HyperpingNotFoundError
from hyperping.models._reporting_models import StatusSummary


class TestGetStatusSummary:
    """Tests for get_status_summary()."""

    @respx.mock
    def test_success(self, client: HyperpingClient) -> None:
        """Test successful status summary retrieval."""
        mock_response = {
            "totalMonitors": 10,
            "upCount": 8,
            "downCount": 1,
            "pausedCount": 1,
            "downMonitors": [],
        }
        respx.get(f"{API_BASE}{Endpoint.STATUS_SUMMARY}").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        result = client.get_status_summary()

        assert isinstance(result, StatusSummary)
        assert result.total_monitors == 10
        assert result.up_count == 8
        assert result.down_count == 1
        assert result.paused_count == 1
        assert result.down_monitors == []

    @respx.mock
    def test_not_found(self, client: HyperpingClient) -> None:
        """Test 404 raises HyperpingNotFoundError."""
        respx.get(f"{API_BASE}{Endpoint.STATUS_SUMMARY}").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )

        with pytest.raises(HyperpingNotFoundError):
            client.get_status_summary()


class TestGetMonitorResponseTime:
    """Tests for get_monitor_response_time()."""

    @respx.mock
    def test_success(self, client: HyperpingClient) -> None:
        """Test successful response time retrieval."""
        mock_response = {"p50": 45.0, "p95": 120.0}
        respx.get(f"{API_BASE}/v2/reporting/response-time/uuid_1").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        result = client.get_monitor_response_time("uuid_1")

        assert isinstance(result, dict)
        assert result["p50"] == 45.0
        assert result["p95"] == 120.0

    @respx.mock
    def test_default_period_is_24h(self, client: HyperpingClient) -> None:
        """Test that the default period query param is 24h."""
        respx.get(f"{API_BASE}/v2/reporting/response-time/uuid_1").mock(
            return_value=httpx.Response(200, json={"p50": 45.0})
        )

        client.get_monitor_response_time("uuid_1")

        request = respx.calls.last.request
        assert "period=24h" in str(request.url)

    @respx.mock
    def test_custom_period(self, client: HyperpingClient) -> None:
        """Test that a custom period is forwarded as a query param."""
        respx.get(f"{API_BASE}/v2/reporting/response-time/uuid_1").mock(
            return_value=httpx.Response(200, json={"p50": 45.0})
        )

        client.get_monitor_response_time("uuid_1", period="7d")

        request = respx.calls.last.request
        assert "period=7d" in str(request.url)

    def test_invalid_id_raises_value_error(self, client: HyperpingClient) -> None:
        """Test that an invalid ID with path traversal raises ValueError."""
        with pytest.raises(ValueError, match="Invalid monitor_uuid"):
            client.get_monitor_response_time("../bad")


class TestGetMonitorMtta:
    """Tests for get_monitor_mtta()."""

    @respx.mock
    def test_success(self, client: HyperpingClient) -> None:
        """Test successful MTTA retrieval."""
        mock_response = {"mtta_seconds": 120.0}
        respx.get(f"{API_BASE}/v2/reporting/mtta/uuid_1").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        result = client.get_monitor_mtta("uuid_1")

        assert isinstance(result, dict)
        assert result["mtta_seconds"] == 120.0

    @respx.mock
    def test_default_period_is_30d(self, client: HyperpingClient) -> None:
        """Test that the default period query param is 30d."""
        respx.get(f"{API_BASE}/v2/reporting/mtta/uuid_1").mock(
            return_value=httpx.Response(200, json={"mtta_seconds": 120.0})
        )

        client.get_monitor_mtta("uuid_1")

        request = respx.calls.last.request
        assert "period=30d" in str(request.url)

    @respx.mock
    def test_custom_period(self, client: HyperpingClient) -> None:
        """Test that a custom period is forwarded as a query param."""
        respx.get(f"{API_BASE}/v2/reporting/mtta/uuid_1").mock(
            return_value=httpx.Response(200, json={"mtta_seconds": 60.0})
        )

        client.get_monitor_mtta("uuid_1", period="7d")

        request = respx.calls.last.request
        assert "period=7d" in str(request.url)

    def test_invalid_id_raises_value_error(self, client: HyperpingClient) -> None:
        """Test that an invalid ID with path traversal raises ValueError."""
        with pytest.raises(ValueError, match="Invalid monitor_uuid"):
            client.get_monitor_mtta("../bad")

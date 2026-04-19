"""Tests for outage management API methods."""

import httpx
import pytest
import respx

from hyperping.client import HyperpingClient
from hyperping.endpoints import API_BASE, Endpoint
from hyperping.exceptions import HyperpingNotFoundError
from hyperping.models import Outage, OutageAction, OutageTimeline


class TestOutageAPIClient:
    """Tests for outage API operations."""

    @respx.mock
    def test_list_outages_success(self, client: HyperpingClient) -> None:
        """Test listing outages."""
        mock_response = {
            "outages": [
                {"uuid": "out_1", "monitor_uuid": "mon_1", "status": "active"},
                {"uuid": "out_2", "monitor_uuid": "mon_2", "status": "acknowledged"},
            ]
        }
        respx.get(f"{API_BASE}{Endpoint.OUTAGES}").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        outages = client.list_outages()
        assert len(outages) == 2
        assert outages[0].uuid == "out_1"

    @respx.mock
    def test_list_outages_as_list(self, client: HyperpingClient) -> None:
        """Test listing outages when API returns a raw list."""
        mock_response = [
            {"uuid": "out_1", "monitor_uuid": "mon_1", "status": "active"},
        ]
        respx.get(f"{API_BASE}{Endpoint.OUTAGES}").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        outages = client.list_outages()
        assert len(outages) == 1
        assert outages[0].uuid == "out_1"

    @respx.mock
    def test_list_outages_empty(self, client: HyperpingClient) -> None:
        """Test listing with no outages."""
        respx.get(f"{API_BASE}{Endpoint.OUTAGES}").mock(
            return_value=httpx.Response(200, json={"outages": []})
        )
        outages = client.list_outages()
        assert outages == []

    @respx.mock
    def test_list_outages_returns_empty_on_404(self, client: HyperpingClient) -> None:
        """Test that 404 returns empty list instead of raising."""
        respx.get(f"{API_BASE}{Endpoint.OUTAGES}").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )
        outages = client.list_outages()
        assert outages == []

    @respx.mock
    def test_acknowledge_outage_no_message(self, client: HyperpingClient) -> None:
        """Test acknowledging outage without a message."""
        respx.post(f"{API_BASE}{Endpoint.OUTAGES}/out_1/acknowledge").mock(
            return_value=httpx.Response(200, json={"status": "acknowledged"})
        )
        result = client.acknowledge_outage("out_1")
        assert isinstance(result, OutageAction)
        assert result.status == "acknowledged"

    @respx.mock
    def test_acknowledge_outage_with_message(self, client: HyperpingClient) -> None:
        """Test acknowledging outage with a message."""
        respx.post(f"{API_BASE}{Endpoint.OUTAGES}/out_1/acknowledge").mock(
            return_value=httpx.Response(200, json={"status": "acknowledged"})
        )
        result = client.acknowledge_outage("out_1", message="On it")
        assert isinstance(result, OutageAction)
        assert result.status == "acknowledged"

    @respx.mock
    def test_acknowledge_outage_not_found(self, client: HyperpingClient) -> None:
        """Test acknowledging a non-existent outage."""
        respx.post(
            f"{API_BASE}{Endpoint.OUTAGES}/out_nope/acknowledge"
        ).mock(return_value=httpx.Response(404, json={"error": "Not found"}))
        with pytest.raises(HyperpingNotFoundError):
            client.acknowledge_outage("out_nope")

    @respx.mock
    def test_resolve_outage_no_message(self, client: HyperpingClient) -> None:
        """Test resolving outage without a message."""
        respx.post(f"{API_BASE}{Endpoint.OUTAGES}/out_1/resolve").mock(
            return_value=httpx.Response(200, json={"status": "resolved"})
        )
        result = client.resolve_outage("out_1")
        assert isinstance(result, OutageAction)
        assert result.status == "resolved"

    @respx.mock
    def test_resolve_outage_with_message(self, client: HyperpingClient) -> None:
        """Test resolving outage with a message."""
        respx.post(f"{API_BASE}{Endpoint.OUTAGES}/out_1/resolve").mock(
            return_value=httpx.Response(200, json={"status": "resolved"})
        )
        result = client.resolve_outage("out_1", message="Fixed the issue")
        assert isinstance(result, OutageAction)
        assert result.status == "resolved"

    @respx.mock
    def test_resolve_outage_not_found(self, client: HyperpingClient) -> None:
        """Test resolving a non-existent outage."""
        respx.post(f"{API_BASE}{Endpoint.OUTAGES}/out_nope/resolve").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )
        with pytest.raises(HyperpingNotFoundError):
            client.resolve_outage("out_nope")

    @respx.mock
    def test_escalate_outage(self, client: HyperpingClient) -> None:
        """Test escalating an outage."""
        respx.post(f"{API_BASE}{Endpoint.OUTAGES}/out_1/escalate").mock(
            return_value=httpx.Response(200, json={"status": "escalated"})
        )
        result = client.escalate_outage("out_1")
        assert isinstance(result, OutageAction)
        assert result.status == "escalated"

    @respx.mock
    def test_escalate_outage_not_found(self, client: HyperpingClient) -> None:
        """Test escalating a non-existent outage."""
        respx.post(f"{API_BASE}{Endpoint.OUTAGES}/out_nope/escalate").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )
        with pytest.raises(HyperpingNotFoundError):
            client.escalate_outage("out_nope")


class TestGetOutageTimeline:
    """Tests for get_outage_timeline method."""

    @respx.mock
    def test_success(self, client: HyperpingClient) -> None:
        """Test retrieving an outage timeline with events."""
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

        result = client.get_outage_timeline("out_1")

        assert isinstance(result, OutageTimeline)
        assert result.outage_uuid == "out_1"
        assert len(result.events) == 1
        assert result.events[0].event_type == "detection"
        assert result.events[0].timestamp == "2026-01-01T00:00:00Z"
        assert result.events[0].detail == "Probe failed"

    @respx.mock
    def test_not_found(self, client: HyperpingClient) -> None:
        """Test 404 raises HyperpingNotFoundError."""
        respx.get(f"{API_BASE}{Endpoint.OUTAGES}/out_x/timeline").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )

        with pytest.raises(HyperpingNotFoundError):
            client.get_outage_timeline("out_x")

    def test_invalid_id(self, client: HyperpingClient) -> None:
        """Test that a path-traversal ID raises ValueError."""
        with pytest.raises(ValueError):
            client.get_outage_timeline("../bad")


class TestGetMonitorOutages:
    """Tests for get_monitor_outages method."""

    @respx.mock
    def test_success(self, client: HyperpingClient) -> None:
        """Test retrieving outages scoped to a monitor."""
        respx.get(f"{API_BASE}{Endpoint.OUTAGES}").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "uuid": "out_10",
                        "monitorUuid": "mon_1",
                        "status": "active",
                        "acknowledged": False,
                        "resolved": False,
                    },
                    {
                        "uuid": "out_11",
                        "monitorUuid": "mon_1",
                        "status": "resolved",
                        "acknowledged": True,
                        "resolved": True,
                    },
                ],
            )
        )

        result = client.get_monitor_outages("mon_1")

        assert len(result) == 2
        assert all(isinstance(o, Outage) for o in result)
        assert result[0].uuid == "out_10"
        assert result[1].uuid == "out_11"

    @respx.mock
    def test_empty_on_404(self, client: HyperpingClient) -> None:
        """Test that 404 returns an empty list."""
        respx.get(f"{API_BASE}{Endpoint.OUTAGES}").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )

        result = client.get_monitor_outages("mon_1")
        assert result == []

    def test_invalid_id(self, client: HyperpingClient) -> None:
        """Test that a path-traversal monitor UUID raises ValueError."""
        with pytest.raises(ValueError):
            client.get_monitor_outages("../bad")

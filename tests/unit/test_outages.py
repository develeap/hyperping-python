"""Tests for outage management API methods."""

import httpx
import pytest
import respx

from hyperping.client import HyperpingClient
from hyperping.endpoints import API_BASE, Endpoint
from hyperping.exceptions import HyperpingNotFoundError


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
        assert result["status"] == "acknowledged"

    @respx.mock
    def test_acknowledge_outage_with_message(self, client: HyperpingClient) -> None:
        """Test acknowledging outage with a message."""
        respx.post(f"{API_BASE}{Endpoint.OUTAGES}/out_1/acknowledge").mock(
            return_value=httpx.Response(200, json={"status": "acknowledged"})
        )
        result = client.acknowledge_outage("out_1", message="On it")
        assert result["status"] == "acknowledged"

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
        assert result["status"] == "resolved"

    @respx.mock
    def test_resolve_outage_with_message(self, client: HyperpingClient) -> None:
        """Test resolving outage with a message."""
        respx.post(f"{API_BASE}{Endpoint.OUTAGES}/out_1/resolve").mock(
            return_value=httpx.Response(200, json={"status": "resolved"})
        )
        result = client.resolve_outage("out_1", message="Fixed the issue")
        assert result["status"] == "resolved"

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
        assert result["status"] == "escalated"

    @respx.mock
    def test_escalate_outage_not_found(self, client: HyperpingClient) -> None:
        """Test escalating a non-existent outage."""
        respx.post(f"{API_BASE}{Endpoint.OUTAGES}/out_nope/escalate").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )
        with pytest.raises(HyperpingNotFoundError):
            client.escalate_outage("out_nope")

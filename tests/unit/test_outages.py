"""Tests for outage management API methods."""

import httpx
import pytest
import respx

from hyperping.client import HyperpingClient
from hyperping.endpoints import API_BASE, Endpoint
from hyperping.exceptions import HyperpingNotFoundError
from hyperping.models import OutageAction


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
        respx.post(f"{API_BASE}{Endpoint.OUTAGES}/out_nope/acknowledge").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )
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

    def test_list_outages_invalid_status(self, client: HyperpingClient) -> None:
        """list_outages raises ValueError for unrecognised status."""
        with pytest.raises(ValueError, match="Invalid status"):
            client.list_outages(status="bad_status")

    def test_list_outages_invalid_outage_type(self, client: HyperpingClient) -> None:
        """list_outages raises ValueError for unrecognised outage_type."""
        with pytest.raises(ValueError, match="Invalid outage_type"):
            client.list_outages(outage_type="bad_type")

    @respx.mock
    def test_unacknowledge_outage(self, client: HyperpingClient) -> None:
        """Test unacknowledging an outage."""
        respx.post(f"{API_BASE}{Endpoint.OUTAGES}/out_1/unacknowledge").mock(
            return_value=httpx.Response(200, json={"status": "unacknowledged"})
        )
        result = client.unacknowledge_outage("out_1")
        assert isinstance(result, OutageAction)
        assert result.status == "unacknowledged"

    @respx.mock
    def test_unacknowledge_outage_not_found(self, client: HyperpingClient) -> None:
        """Test unacknowledging a non-existent outage."""
        respx.post(f"{API_BASE}{Endpoint.OUTAGES}/out_nope/unacknowledge").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )
        with pytest.raises(HyperpingNotFoundError):
            client.unacknowledge_outage("out_nope")

    @respx.mock
    def test_delete_outage(self, client: HyperpingClient) -> None:
        """Test deleting an outage."""
        respx.delete(f"{API_BASE}{Endpoint.OUTAGES}/out_1").mock(return_value=httpx.Response(204))
        result = client.delete_outage("out_1")
        assert result is None

    @respx.mock
    def test_delete_outage_not_found(self, client: HyperpingClient) -> None:
        """Test deleting a non-existent outage."""
        respx.delete(f"{API_BASE}{Endpoint.OUTAGES}/out_nope").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )
        with pytest.raises(HyperpingNotFoundError):
            client.delete_outage("out_nope")

    @respx.mock
    def test_create_outage(self, client: HyperpingClient) -> None:
        """Test creating a manual outage."""
        from hyperping.models import Outage

        respx.post(f"{API_BASE}{Endpoint.OUTAGES}").mock(
            return_value=httpx.Response(
                201,
                json={"uuid": "out_new", "monitor_uuid": "mon_1", "status": "active"},
            )
        )
        result = client.create_outage("mon_1")
        assert isinstance(result, Outage)
        assert result.uuid == "out_new"
        assert result.monitor_uuid == "mon_1"

    @respx.mock
    def test_get_outage(self, client: HyperpingClient) -> None:
        """Test getting a single outage by ID."""
        from hyperping.models import Outage

        respx.get(f"{API_BASE}{Endpoint.OUTAGES}/out_1").mock(
            return_value=httpx.Response(
                200,
                json={"uuid": "out_1", "monitor_uuid": "mon_1", "status": "active"},
            )
        )
        result = client.get_outage("out_1")
        assert isinstance(result, Outage)
        assert result.uuid == "out_1"

    @respx.mock
    def test_get_outage_not_found(self, client: HyperpingClient) -> None:
        """Test getting a non-existent outage."""
        respx.get(f"{API_BASE}{Endpoint.OUTAGES}/out_nope").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )
        with pytest.raises(HyperpingNotFoundError):
            client.get_outage("out_nope")

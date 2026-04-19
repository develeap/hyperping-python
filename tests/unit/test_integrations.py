"""Tests for integrations API methods."""

import httpx
import pytest
import respx

from hyperping.client import HyperpingClient
from hyperping.endpoints import API_BASE, Endpoint
from hyperping.exceptions import HyperpingNotFoundError
from hyperping.models._integration_models import Integration


class TestListIntegrations:
    """Tests for list_integrations()."""

    @respx.mock
    def test_success(self, client: HyperpingClient) -> None:
        """Test listing integrations returns parsed models."""
        respx.get(f"{API_BASE}{Endpoint.INTEGRATIONS}").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "uuid": "i1",
                        "name": "Slack",
                        "type": "slack",
                        "active": True,
                    }
                ],
            )
        )

        result = client.list_integrations()
        assert len(result) == 1
        assert isinstance(result[0], Integration)
        assert result[0].uuid == "i1"
        assert result[0].name == "Slack"
        # Verify "type" alias maps to integration_type field
        assert result[0].integration_type == "slack"
        assert result[0].active is True

    @respx.mock
    def test_empty(self, client: HyperpingClient) -> None:
        """Test listing when no integrations exist returns empty list."""
        respx.get(f"{API_BASE}{Endpoint.INTEGRATIONS}").mock(
            return_value=httpx.Response(200, json=[])
        )
        result = client.list_integrations()
        assert result == []

    @respx.mock
    def test_returns_empty_on_404(self, client: HyperpingClient) -> None:
        """Test that 404 returns empty list instead of raising."""
        respx.get(f"{API_BASE}{Endpoint.INTEGRATIONS}").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )
        result = client.list_integrations()
        assert result == []


class TestGetIntegration:
    """Tests for get_integration()."""

    @respx.mock
    def test_success(self, client: HyperpingClient) -> None:
        """Test getting a single integration."""
        respx.get(f"{API_BASE}{Endpoint.INTEGRATIONS}/i1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "uuid": "i1",
                    "name": "Slack",
                    "type": "slack",
                    "active": True,
                },
            )
        )

        result = client.get_integration("i1")
        assert isinstance(result, Integration)
        assert result.uuid == "i1"
        assert result.name == "Slack"
        assert result.integration_type == "slack"
        assert result.active is True

    @respx.mock
    def test_not_found(self, client: HyperpingClient) -> None:
        """Test that 404 raises HyperpingNotFoundError."""
        respx.get(f"{API_BASE}{Endpoint.INTEGRATIONS}/i_nope").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )
        with pytest.raises(HyperpingNotFoundError):
            client.get_integration("i_nope")

    def test_invalid_id(self, client: HyperpingClient) -> None:
        """Test that path-traversal ID raises ValueError."""
        with pytest.raises(ValueError):
            client.get_integration("../bad")

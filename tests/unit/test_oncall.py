"""Tests for on-call API methods (schedules, escalation policies, team members)."""

import httpx
import pytest
import respx

from hyperping.client import HyperpingClient
from hyperping.endpoints import API_BASE, Endpoint
from hyperping.exceptions import HyperpingNotFoundError
from hyperping.models._oncall_models import EscalationPolicy, OnCallSchedule


class TestListOnCallSchedules:
    """Tests for list_on_call_schedules()."""

    @respx.mock
    def test_success(self, client: HyperpingClient) -> None:
        """Test listing on-call schedules returns parsed models."""
        respx.get(f"{API_BASE}{Endpoint.ON_CALL_SCHEDULES}").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "uuid": "s1",
                        "name": "Primary",
                        "currentOnCall": "alice",
                    }
                ],
            )
        )

        result = client.list_on_call_schedules()
        assert len(result) == 1
        assert isinstance(result[0], OnCallSchedule)
        assert result[0].uuid == "s1"
        assert result[0].name == "Primary"
        # Verify camelCase alias is correctly mapped to snake_case field
        assert result[0].current_on_call == "alice"

    @respx.mock
    def test_empty(self, client: HyperpingClient) -> None:
        """Test listing when no schedules exist returns empty list."""
        respx.get(f"{API_BASE}{Endpoint.ON_CALL_SCHEDULES}").mock(
            return_value=httpx.Response(200, json=[])
        )
        result = client.list_on_call_schedules()
        assert result == []

    @respx.mock
    def test_returns_empty_on_404(self, client: HyperpingClient) -> None:
        """Test that 404 returns empty list instead of raising."""
        respx.get(f"{API_BASE}{Endpoint.ON_CALL_SCHEDULES}").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )
        result = client.list_on_call_schedules()
        assert result == []


class TestGetOnCallSchedule:
    """Tests for get_on_call_schedule()."""

    @respx.mock
    def test_success(self, client: HyperpingClient) -> None:
        """Test getting a single on-call schedule."""
        respx.get(f"{API_BASE}{Endpoint.ON_CALL_SCHEDULES}/s1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "uuid": "s1",
                    "name": "Primary",
                    "currentOnCall": "bob",
                },
            )
        )

        result = client.get_on_call_schedule("s1")
        assert isinstance(result, OnCallSchedule)
        assert result.uuid == "s1"
        assert result.name == "Primary"
        assert result.current_on_call == "bob"

    @respx.mock
    def test_not_found(self, client: HyperpingClient) -> None:
        """Test that 404 raises HyperpingNotFoundError."""
        respx.get(f"{API_BASE}{Endpoint.ON_CALL_SCHEDULES}/s_nope").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )
        with pytest.raises(HyperpingNotFoundError):
            client.get_on_call_schedule("s_nope")

    def test_invalid_id(self, client: HyperpingClient) -> None:
        """Test that path-traversal ID raises ValueError."""
        with pytest.raises(ValueError):
            client.get_on_call_schedule("../bad")


class TestListEscalationPolicies:
    """Tests for list_escalation_policies()."""

    @respx.mock
    def test_success(self, client: HyperpingClient) -> None:
        """Test listing escalation policies returns parsed models."""
        respx.get(f"{API_BASE}{Endpoint.ESCALATION_POLICIES}").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "uuid": "p1",
                        "name": "Default",
                        "steps": [{"level": 1}],
                    }
                ],
            )
        )

        result = client.list_escalation_policies()
        assert len(result) == 1
        assert isinstance(result[0], EscalationPolicy)
        assert result[0].uuid == "p1"
        assert result[0].name == "Default"
        assert result[0].steps == [{"level": 1}]

    @respx.mock
    def test_empty(self, client: HyperpingClient) -> None:
        """Test listing when no policies exist returns empty list."""
        respx.get(f"{API_BASE}{Endpoint.ESCALATION_POLICIES}").mock(
            return_value=httpx.Response(200, json=[])
        )
        result = client.list_escalation_policies()
        assert result == []

    @respx.mock
    def test_returns_empty_on_404(self, client: HyperpingClient) -> None:
        """Test that 404 returns empty list instead of raising."""
        respx.get(f"{API_BASE}{Endpoint.ESCALATION_POLICIES}").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )
        result = client.list_escalation_policies()
        assert result == []


class TestGetEscalationPolicy:
    """Tests for get_escalation_policy()."""

    @respx.mock
    def test_success(self, client: HyperpingClient) -> None:
        """Test getting a single escalation policy."""
        respx.get(f"{API_BASE}{Endpoint.ESCALATION_POLICIES}/p1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "uuid": "p1",
                    "name": "Default",
                    "steps": [{"level": 1}, {"level": 2}],
                },
            )
        )

        result = client.get_escalation_policy("p1")
        assert isinstance(result, EscalationPolicy)
        assert result.uuid == "p1"
        assert result.name == "Default"
        assert len(result.steps) == 2

    @respx.mock
    def test_not_found(self, client: HyperpingClient) -> None:
        """Test that 404 raises HyperpingNotFoundError."""
        respx.get(f"{API_BASE}{Endpoint.ESCALATION_POLICIES}/p_nope").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )
        with pytest.raises(HyperpingNotFoundError):
            client.get_escalation_policy("p_nope")

    def test_invalid_id(self, client: HyperpingClient) -> None:
        """Test that path-traversal ID raises ValueError."""
        with pytest.raises(ValueError):
            client.get_escalation_policy("../bad")


class TestListTeamMembers:
    """Tests for list_team_members()."""

    @respx.mock
    def test_success(self, client: HyperpingClient) -> None:
        """Test listing team members returns raw dicts."""
        respx.get(f"{API_BASE}{Endpoint.TEAM_MEMBERS}").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {"name": "Alice", "email": "alice@example.com"},
                ],
            )
        )

        result = client.list_team_members()
        assert len(result) == 1
        assert isinstance(result[0], dict)
        assert result[0]["name"] == "Alice"
        assert result[0]["email"] == "alice@example.com"

    @respx.mock
    def test_empty(self, client: HyperpingClient) -> None:
        """Test listing when no team members exist returns empty list."""
        respx.get(f"{API_BASE}{Endpoint.TEAM_MEMBERS}").mock(
            return_value=httpx.Response(200, json=[])
        )
        result = client.list_team_members()
        assert result == []

    @respx.mock
    def test_returns_empty_on_404(self, client: HyperpingClient) -> None:
        """Test that 404 returns empty list instead of raising."""
        respx.get(f"{API_BASE}{Endpoint.TEAM_MEMBERS}").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )
        result = client.list_team_members()
        assert result == []

"""Tests for healthcheck management API methods."""

import httpx
import pytest
import respx

from hyperping.client import HyperpingClient
from hyperping.endpoints import API_BASE, Endpoint
from hyperping.exceptions import HyperpingAPIError, HyperpingNotFoundError
from hyperping.models import Healthcheck, HealthcheckCreate, HealthcheckUpdate

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_HC_ENDPOINT = f"{API_BASE}{Endpoint.HEALTHCHECKS}"

_HC_FIXTURE: dict = {
    "uuid": "hc_abc123",
    "name": "Daily job",
    "period": 86400,
    "grace": 3600,
    "escalation_policy": None,
    "project_uuid": None,
    "is_paused": False,
    "is_down": False,
    "last_pinged_at": None,
}


def _make_hc(**overrides: object) -> dict:
    """Return a healthcheck dict with optional field overrides."""
    return {**_HC_FIXTURE, **overrides}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestListHealthchecks:
    """Tests for list_healthchecks()."""

    @respx.mock
    def test_returns_list_of_healthchecks(self, client: HyperpingClient) -> None:
        """Returns a list of Healthcheck objects when API responds normally."""
        respx.get(_HC_ENDPOINT).mock(
            return_value=httpx.Response(200, json=[_make_hc(), _make_hc(uuid="hc_def456")])
        )

        result = client.list_healthchecks()

        assert len(result) == 2
        assert all(isinstance(hc, Healthcheck) for hc in result)
        assert result[0].uuid == "hc_abc123"
        assert result[1].uuid == "hc_def456"

    @respx.mock
    def test_returns_list_from_healthchecks_key(self, client: HyperpingClient) -> None:
        """Handles API response wrapped in a 'healthchecks' key."""
        respx.get(_HC_ENDPOINT).mock(
            return_value=httpx.Response(200, json={"healthchecks": [_make_hc()]})
        )

        result = client.list_healthchecks()

        assert len(result) == 1
        assert result[0].uuid == "hc_abc123"

    @respx.mock
    def test_returns_empty_list_on_404(self, client: HyperpingClient) -> None:
        """Returns empty list instead of raising on 404 (consistent with list_outages)."""
        respx.get(_HC_ENDPOINT).mock(return_value=httpx.Response(404, json={"error": "Not found"}))

        result = client.list_healthchecks()

        assert result == []

    @respx.mock
    def test_returns_empty_list_when_response_is_empty_list(self, client: HyperpingClient) -> None:
        """Returns empty list when API returns an empty array."""
        respx.get(_HC_ENDPOINT).mock(return_value=httpx.Response(200, json=[]))

        result = client.list_healthchecks()

        assert result == []


class TestGetHealthcheck:
    """Tests for get_healthcheck()."""

    @respx.mock
    def test_returns_healthcheck(self, client: HyperpingClient) -> None:
        """Returns a Healthcheck object for a valid ID."""
        respx.get(f"{_HC_ENDPOINT}/hc_abc123").mock(
            return_value=httpx.Response(200, json=_make_hc())
        )

        result = client.get_healthcheck("hc_abc123")

        assert isinstance(result, Healthcheck)
        assert result.uuid == "hc_abc123"
        assert result.name == "Daily job"
        assert result.period == 86400
        assert result.grace == 3600

    @respx.mock
    def test_raises_not_found(self, client: HyperpingClient) -> None:
        """Raises HyperpingNotFoundError when healthcheck does not exist."""
        respx.get(f"{_HC_ENDPOINT}/hc_nope").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )

        with pytest.raises(HyperpingNotFoundError):
            client.get_healthcheck("hc_nope")

    def test_raises_on_empty_id(self, client: HyperpingClient) -> None:
        """Raises ValueError when healthcheck_id is empty."""
        with pytest.raises(ValueError):
            client.get_healthcheck("")


class TestCreateHealthcheck:
    """Tests for create_healthcheck()."""

    @respx.mock
    def test_returns_created_healthcheck(self, client: HyperpingClient) -> None:
        """Returns the created Healthcheck from the API response."""
        respx.post(_HC_ENDPOINT).mock(return_value=httpx.Response(201, json=_make_hc()))

        payload = HealthcheckCreate(name="Daily job", period=86400, grace=3600)
        result = client.create_healthcheck(payload)

        assert isinstance(result, Healthcheck)
        assert result.uuid == "hc_abc123"
        assert result.name == "Daily job"

    @respx.mock
    def test_excludes_none_fields_from_payload(self, client: HyperpingClient) -> None:
        """Payload sent to the API omits None optional fields."""
        route = respx.post(_HC_ENDPOINT).mock(return_value=httpx.Response(201, json=_make_hc()))

        payload = HealthcheckCreate(name="Hourly job", period=3600, grace=300)
        client.create_healthcheck(payload)

        sent_body = route.calls[0].request
        import json as json_module

        body = json_module.loads(sent_body.content)
        assert "escalation_policy" not in body
        assert "project_uuid" not in body


class TestUpdateHealthcheck:
    """Tests for update_healthcheck()."""

    @respx.mock
    def test_returns_updated_healthcheck(self, client: HyperpingClient) -> None:
        """Returns the updated Healthcheck from the API response."""
        updated = _make_hc(name="Updated job", period=3600)
        respx.put(f"{_HC_ENDPOINT}/hc_abc123").mock(return_value=httpx.Response(200, json=updated))

        update = HealthcheckUpdate(name="Updated job", period=3600)
        result = client.update_healthcheck("hc_abc123", update)

        assert isinstance(result, Healthcheck)
        assert result.name == "Updated job"
        assert result.period == 3600

    @respx.mock
    def test_raises_not_found(self, client: HyperpingClient) -> None:
        """Raises HyperpingNotFoundError when healthcheck does not exist."""
        respx.put(f"{_HC_ENDPOINT}/hc_nope").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )

        with pytest.raises(HyperpingNotFoundError):
            client.update_healthcheck("hc_nope", HealthcheckUpdate(name="x"))

    def test_raises_on_empty_id(self, client: HyperpingClient) -> None:
        """Raises ValueError when healthcheck_id is empty."""
        with pytest.raises(ValueError):
            client.update_healthcheck("", HealthcheckUpdate(name="x"))


class TestDeleteHealthcheck:
    """Tests for delete_healthcheck()."""

    @respx.mock
    def test_returns_none_on_success(self, client: HyperpingClient) -> None:
        """Returns None after a successful delete."""
        respx.delete(f"{_HC_ENDPOINT}/hc_abc123").mock(return_value=httpx.Response(204))

        result = client.delete_healthcheck("hc_abc123")

        assert result is None

    @respx.mock
    def test_raises_not_found(self, client: HyperpingClient) -> None:
        """Raises HyperpingNotFoundError when healthcheck does not exist."""
        respx.delete(f"{_HC_ENDPOINT}/hc_nope").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )

        with pytest.raises(HyperpingNotFoundError):
            client.delete_healthcheck("hc_nope")

    def test_raises_on_empty_id(self, client: HyperpingClient) -> None:
        """Raises ValueError when healthcheck_id is empty."""
        with pytest.raises(ValueError):
            client.delete_healthcheck("")


class TestPauseHealthcheck:
    """Tests for pause_healthcheck()."""

    @respx.mock
    def test_returns_healthcheck(self, client: HyperpingClient) -> None:
        """Returns a Healthcheck (not None) after pausing."""
        paused = _make_hc(is_paused=True)
        respx.post(f"{_HC_ENDPOINT}/hc_abc123/pause").mock(
            return_value=httpx.Response(200, json=paused)
        )

        result = client.pause_healthcheck("hc_abc123")

        assert isinstance(result, Healthcheck)
        assert result.is_paused is True

    @respx.mock
    def test_raises_not_found(self, client: HyperpingClient) -> None:
        """Raises HyperpingNotFoundError when healthcheck does not exist."""
        respx.post(f"{_HC_ENDPOINT}/hc_nope/pause").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )

        with pytest.raises(HyperpingNotFoundError):
            client.pause_healthcheck("hc_nope")

    def test_raises_on_empty_id(self, client: HyperpingClient) -> None:
        """Raises ValueError when healthcheck_id is empty."""
        with pytest.raises(ValueError):
            client.pause_healthcheck("")


class TestResumeHealthcheck:
    """Tests for resume_healthcheck()."""

    @respx.mock
    def test_returns_healthcheck(self, client: HyperpingClient) -> None:
        """Returns a Healthcheck (not None) after resuming."""
        resumed = _make_hc(is_paused=False)
        respx.post(f"{_HC_ENDPOINT}/hc_abc123/resume").mock(
            return_value=httpx.Response(200, json=resumed)
        )

        result = client.resume_healthcheck("hc_abc123")

        assert isinstance(result, Healthcheck)
        assert result.is_paused is False

    @respx.mock
    def test_raises_not_found(self, client: HyperpingClient) -> None:
        """Raises HyperpingNotFoundError when healthcheck does not exist."""
        respx.post(f"{_HC_ENDPOINT}/hc_nope/resume").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )

        with pytest.raises(HyperpingNotFoundError):
            client.resume_healthcheck("hc_nope")

    def test_raises_on_empty_id(self, client: HyperpingClient) -> None:
        """Raises ValueError when healthcheck_id is empty."""
        with pytest.raises(ValueError):
            client.resume_healthcheck("")


class TestErrorHandling:
    """Tests for non-404 error propagation."""

    @respx.mock
    def test_server_error_is_raised_not_swallowed(self, client: HyperpingClient) -> None:
        """Non-404 errors on list_healthchecks are raised, not silently swallowed."""
        respx.get(_HC_ENDPOINT).mock(
            return_value=httpx.Response(500, json={"error": "Internal Server Error"})
        )

        with pytest.raises(HyperpingAPIError):
            client.list_healthchecks()

    @respx.mock
    def test_server_error_on_get_is_raised(self, client: HyperpingClient) -> None:
        """Non-404 server errors on get_healthcheck are raised."""
        respx.get(f"{_HC_ENDPOINT}/hc_abc123").mock(
            return_value=httpx.Response(500, json={"error": "Internal Server Error"})
        )

        with pytest.raises(HyperpingAPIError):
            client.get_healthcheck("hc_abc123")

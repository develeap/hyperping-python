"""Tests for incident models and API methods."""

from datetime import UTC, datetime

import httpx
import pytest
import respx

from hyperping.client import HyperpingClient
from hyperping.endpoints import API_BASE, Endpoint
from hyperping.exceptions import (
    HyperpingNotFoundError,
    HyperpingPartialBatchError,
    HyperpingValidationError,
)
from hyperping.models import (
    AddIncidentUpdateRequest,
    Incident,
    IncidentCreate,
    IncidentType,
    IncidentUpdateRequest,
    IncidentUpdateType,
    LocalizedText,
)


class TestIncidentModels:
    """Tests for incident models (v3 API)."""

    def test_incident_create_minimal(self) -> None:
        """Test creating incident with minimal fields."""
        incident = IncidentCreate(
            title=LocalizedText(en="Test Incident"),
            text=LocalizedText(en="Initial message"),
            type=IncidentType.INCIDENT,
            statuspages=["sp_test"],
        )
        assert incident.title.en == "Test Incident"
        assert incident.type == IncidentType.INCIDENT

    def test_incident_create_full(self) -> None:
        """Test creating incident with all fields."""
        incident = IncidentCreate(
            title=LocalizedText(en="Critical Outage"),
            text=LocalizedText(en="Complete service outage"),
            type=IncidentType.OUTAGE,
            statuspages=["sp_test"],
            affected_components=["comp_123", "comp_456"],
        )
        assert incident.type == IncidentType.OUTAGE
        assert len(incident.affected_components) == 2

    def test_incident_parse_response(self) -> None:
        """Test parsing incident API response (v3 format)."""
        data = {
            "uuid": "inci_abc123",
            "date": "2024-01-15T10:30:00Z",
            "title": {"en": "Test Incident"},
            "text": {"en": "Initial message"},
            "type": "incident",
            "affectedComponents": ["comp_123"],
            "statuspages": ["sp_test"],
            "updates": [],
        }
        incident = Incident.model_validate(data)
        assert incident.uuid == "inci_abc123"
        assert incident.is_resolved is False

    def test_incident_is_resolved(self) -> None:
        """Test is_resolved property (checks for resolved update)."""
        data = {
            "uuid": "inci_resolved",
            "date": "2024-01-15T10:30:00Z",
            "title": {"en": "Resolved Incident"},
            "text": {"en": "Issue resolved"},
            "type": "incident",
            "affectedComponents": [],
            "statuspages": [],
            "updates": [
                {
                    "uuid": "upd_1",
                    "date": "2024-01-15T11:00:00Z",
                    "text": {"en": "Issue has been resolved"},
                    "type": "resolved",
                }
            ],
        }
        incident = Incident.model_validate(data)
        assert incident.is_resolved is True

    def test_incident_update_create(self) -> None:
        """Test incident update model (v3 format)."""
        update = AddIncidentUpdateRequest(
            text=LocalizedText(en="Root cause identified"),
            type=IncidentUpdateType.IDENTIFIED,
            date=datetime.now(UTC).isoformat(),
        )
        assert update.text.en == "Root cause identified"
        assert update.type == IncidentUpdateType.IDENTIFIED


class TestIncidentAPIClient:
    """Tests for incident API operations (v3 API)."""

    @respx.mock
    def test_list_incidents(self, client: HyperpingClient) -> None:
        """Test listing incidents (M17: using Endpoint enum)."""
        mock_response = [
            {
                "uuid": "inci_1",
                "date": "2024-01-15T10:00:00Z",
                "title": {"en": "Incident 1"},
                "text": {"en": "Investigating"},
                "type": "incident",
                "affectedComponents": [],
                "statuspages": [],
                "updates": [],
            },
            {
                "uuid": "inci_2",
                "date": "2024-01-15T09:00:00Z",
                "title": {"en": "Incident 2"},
                "text": {"en": "Resolved"},
                "type": "outage",
                "affectedComponents": [],
                "statuspages": [],
                "updates": [
                    {
                        "uuid": "upd_1",
                        "date": "2024-01-15T10:00:00Z",
                        "text": {"en": "Resolved"},
                        "type": "resolved",
                    }
                ],
            },
        ]
        respx.get(f"{API_BASE}{Endpoint.INCIDENTS}").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        incidents = client.list_incidents()
        assert len(incidents) == 2
        assert incidents[0].uuid == "inci_1"

    @respx.mock
    def test_create_incident(self, client: HyperpingClient) -> None:
        """Test creating an incident."""
        create_response = {
            "message": "Incident created successfully",
            "uuid": "inci_new",
        }
        get_response = {
            "uuid": "inci_new",
            "date": "2024-01-15T10:00:00Z",
            "title": {"en": "New Incident"},
            "text": {"en": "Testing"},
            "type": "incident",
            "affectedComponents": [],
            "statuspages": ["sp_test"],
            "updates": [],
        }
        respx.post(f"{API_BASE}{Endpoint.INCIDENTS}").mock(
            return_value=httpx.Response(201, json=create_response)
        )
        respx.get(f"{API_BASE}{Endpoint.INCIDENTS}/inci_new").mock(
            return_value=httpx.Response(200, json=get_response)
        )

        incident = IncidentCreate(
            title=LocalizedText(en="New Incident"),
            text=LocalizedText(en="Testing"),
            type=IncidentType.INCIDENT,
            statuspages=["sp_test"],
        )
        created = client.create_incident(incident)

        assert created.uuid == "inci_new"
        assert created.title.en == "New Incident"

    @respx.mock
    def test_add_incident_update(self, client: HyperpingClient) -> None:
        """Test adding update to incident."""
        full_incident = {
            "uuid": "inci_updated",
            "date": "2024-01-15T10:00:00Z",
            "title": {"en": "Updated Incident"},
            "text": {"en": "Initial text"},
            "type": "incident",
            "affectedComponents": [],
            "statuspages": [],
            "updates": [
                {
                    "uuid": "upd_1",
                    "date": "2024-01-15T11:00:00Z",
                    "text": {"en": "Root cause identified"},
                    "type": "identified",
                }
            ],
        }
        respx.post(f"{API_BASE}{Endpoint.INCIDENTS}/inci_updated/updates").mock(
            return_value=httpx.Response(200, json={"message": "Update added"})
        )
        respx.get(f"{API_BASE}{Endpoint.INCIDENTS}/inci_updated").mock(
            return_value=httpx.Response(200, json=full_incident)
        )

        update = AddIncidentUpdateRequest(
            text=LocalizedText(en="Root cause identified"),
            type=IncidentUpdateType.IDENTIFIED,
            date=datetime.now(UTC).isoformat(),
        )
        updated = client.add_incident_update("inci_updated", update)
        assert updated.uuid == "inci_updated"

    @respx.mock
    def test_resolve_incident(self, client: HyperpingClient) -> None:
        """Test resolving an incident."""
        resolved_incident = {
            "uuid": "inci_resolved",
            "date": "2024-01-15T10:00:00Z",
            "title": {"en": "Resolved"},
            "text": {"en": "All good"},
            "type": "incident",
            "affectedComponents": [],
            "statuspages": [],
            "updates": [
                {
                    "uuid": "upd_resolve",
                    "date": "2024-01-15T12:00:00Z",
                    "text": {"en": "Resolved"},
                    "type": "resolved",
                }
            ],
        }
        respx.post(f"{API_BASE}{Endpoint.INCIDENTS}/inci_resolved/updates").mock(
            return_value=httpx.Response(200, json={"message": "Updated"})
        )
        respx.get(f"{API_BASE}{Endpoint.INCIDENTS}/inci_resolved").mock(
            return_value=httpx.Response(200, json=resolved_incident)
        )

        result = client.resolve_incident("inci_resolved")
        assert result.is_resolved

    @respx.mock
    def test_delete_incident(self, client: HyperpingClient) -> None:
        """Test deleting an incident."""
        respx.delete(f"{API_BASE}{Endpoint.INCIDENTS}/inci_del").mock(
            return_value=httpx.Response(204)
        )
        client.delete_incident("inci_del")  # Should not raise

    @respx.mock
    def test_list_incidents_with_status_filter(self, client: HyperpingClient) -> None:
        """Test listing incidents with status filter."""
        respx.get(f"{API_BASE}{Endpoint.INCIDENTS}").mock(return_value=httpx.Response(200, json=[]))
        incidents = client.list_incidents(status="investigating")
        assert incidents == []

    # ==================== M21: update_incident coverage ====================

    @respx.mock
    def test_update_incident_changes_title(self, client: HyperpingClient) -> None:
        """Test that update_incident sends a PUT and returns the updated incident (M21)."""
        updated_response = {
            "uuid": "inci_upd",
            "date": "2024-01-15T10:00:00Z",
            "title": {"en": "New Title"},
            "text": {"en": "Body"},
            "type": "incident",
            "affectedComponents": [],
            "statuspages": ["sp_1"],
            "updates": [],
        }
        respx.put(f"{API_BASE}{Endpoint.INCIDENTS}/inci_upd").mock(
            return_value=httpx.Response(200, json=updated_response)
        )

        result = client.update_incident(
            "inci_upd",
            IncidentUpdateRequest(title=LocalizedText(en="New Title")),
        )

        assert result.uuid == "inci_upd"
        assert result.title.en == "New Title"

    @respx.mock
    def test_update_incident_not_found(self, client: HyperpingClient) -> None:
        """Test that update_incident raises HyperpingNotFoundError on 404 (M21)."""
        respx.put(f"{API_BASE}{Endpoint.INCIDENTS}/inci_missing").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )

        with pytest.raises(HyperpingNotFoundError):
            client.update_incident(
                "inci_missing",
                IncidentUpdateRequest(title=LocalizedText(en="Title")),
            )


class TestCreateIncidents:
    """create_incidents() chunking, guard, and partial-failure behavior."""

    def _incident(self, n_pages: int) -> IncidentCreate:
        return IncidentCreate(
            title=LocalizedText(en="X"),
            text=LocalizedText(en="Y"),
            type=IncidentType.INCIDENT,
            statuspages=[f"sp_{i}" for i in range(n_pages)],
        )

    def test_create_incident_rejects_over_cap(self, client: HyperpingClient) -> None:
        with pytest.raises(HyperpingValidationError, match="at most 51 status pages"):
            client.create_incident(self._incident(52))

    def test_create_incidents_rejects_bad_chunk_size(self, client: HyperpingClient) -> None:
        with pytest.raises(HyperpingValidationError, match="chunk_size"):
            client.create_incidents(self._incident(1), chunk_size=99)

    @respx.mock
    def test_create_incidents_chunks_statuspages(self, client: HyperpingClient) -> None:
        import json

        route = respx.post(f"{API_BASE}{Endpoint.INCIDENTS}").mock(
            return_value=httpx.Response(201, json={"message": "ok", "uuid": "inci_x"})
        )
        respx.get(f"{API_BASE}{Endpoint.INCIDENTS}/inci_x").mock(
            return_value=httpx.Response(
                200,
                json={
                    "uuid": "inci_x",
                    "date": "2024-01-15T10:00:00Z",
                    "title": {"en": "X"},
                    "text": {"en": "Y"},
                    "type": "incident",
                    "affectedComponents": [],
                    "statuspages": [],
                    "updates": [],
                },
            )
        )
        result = client.create_incidents(self._incident(60))
        assert len(result) == 2
        assert route.call_count == 2
        sizes = [len(json.loads(c.request.content)["statuspages"]) for c in route.calls]
        assert sizes == [51, 9]

    @respx.mock
    def test_create_incidents_partial_failure(self, client: HyperpingClient) -> None:
        posts = {"n": 0}

        def post_side(request: httpx.Request) -> httpx.Response:
            posts["n"] += 1
            if posts["n"] == 1:
                return httpx.Response(201, json={"message": "ok", "uuid": "inci_1"})
            return httpx.Response(500, json={"error": "boom"})

        respx.post(f"{API_BASE}{Endpoint.INCIDENTS}").mock(side_effect=post_side)
        respx.get(f"{API_BASE}{Endpoint.INCIDENTS}/inci_1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "uuid": "inci_1",
                    "date": "2024-01-15T10:00:00Z",
                    "title": {"en": "X"},
                    "text": {"en": "Y"},
                    "type": "incident",
                    "affectedComponents": [],
                    "statuspages": [],
                    "updates": [],
                },
            )
        )
        with pytest.raises(HyperpingPartialBatchError) as ei:
            client.create_incidents(self._incident(60))
        assert len(ei.value.created) == 1
        assert ei.value.total == 2

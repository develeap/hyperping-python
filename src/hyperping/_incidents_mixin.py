"""Incident operations mixin for HyperpingClient.

Provides CRUD methods for Hyperping incidents (v3 API). Mixed into
:class:`~hyperping.client.HyperpingClient` at class definition time.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from hyperping._protocols import _ClientProtocol
from hyperping._utils import expect_dict, parse_list, unwrap_list, validate_id
from hyperping.endpoints import Endpoint
from hyperping.models import (
    AddIncidentUpdateRequest,  # canonical name (M18)
    Incident,
    IncidentCreate,
    IncidentUpdateRequest,
    IncidentUpdateType,  # canonical name (M18)
    LocalizedText,
)

logger = logging.getLogger(__name__)


class IncidentsMixin(_ClientProtocol):
    """Incident-related API operations."""

    def list_incidents(self, status: str | None = None) -> list[Incident]:
        """List all incidents.

        Args:
            status: Filter by status (``investigating``, ``identified``,
                ``monitoring``, ``resolved``).

        Returns:
            List of :class:`Incident` objects. Incidents that fail to parse
            are silently skipped with a warning log.

        Raises:
            HyperpingAuthError: If the API key is invalid.
            HyperpingAPIError: On unexpected API errors.
        """
        params = {}
        if status:
            params["status"] = status

        response = self._request(
            "GET", Endpoint.INCIDENTS, params=params or None  # M20
        )
        return parse_list(unwrap_list(response, "incidents"), Incident, "incident")

    def get_incident(self, incident_id: str) -> Incident:
        """Get a single incident by ID.

        Args:
            incident_id: Incident ID

        Returns:
            Incident object

        Raises:
            HyperpingNotFoundError: If incident not found
        """
        validate_id(incident_id, "incident_id")  # H8
        response = self._request("GET", f"{Endpoint.INCIDENTS}/{incident_id}")
        return Incident.model_validate(expect_dict(response, "get_incident"))

    def create_incident(self, incident: IncidentCreate) -> Incident:
        """Create a new incident.

        Args:
            incident: Incident creation data.

        Returns:
            Created :class:`Incident` object.

        Raises:
            HyperpingValidationError: If the payload fails server-side validation.
            HyperpingAPIError: On unexpected API errors.

        Note:
            v3 API returns {"message": "...", "uuid": "..."} on create,
            not the full incident object. The full incident is fetched after creation.
        """
        payload = incident.model_dump(exclude_none=True, by_alias=True, mode="json")
        response = expect_dict(
            self._request("POST", Endpoint.INCIDENTS, json=payload),
            "create_incident",
        )
        # v3 API returns minimal response with just uuid
        if "uuid" in response and "title" not in response:
            # Fetch the full incident after creation
            return self.get_incident(response["uuid"])
        return Incident.model_validate(response)

    def update_incident(
        self,
        incident_id: str,
        update: IncidentUpdateRequest,
    ) -> Incident:
        """Update an existing incident.

        Args:
            incident_id: Incident UUID.
            update: Fields to update.

        Returns:
            Updated :class:`Incident` object.

        Raises:
            HyperpingNotFoundError: If the incident does not exist.
            HyperpingValidationError: If the payload fails server-side validation.
            HyperpingAPIError: On unexpected API errors.
        """
        validate_id(incident_id, "incident_id")  # H8
        payload = update.model_dump(exclude_none=True, by_alias=True)
        response = expect_dict(
            self._request("PUT", f"{Endpoint.INCIDENTS}/{incident_id}", json=payload),
            "update_incident",
        )
        return Incident.model_validate(response)

    def add_incident_update(
        self,
        incident_id: str,
        update: AddIncidentUpdateRequest,
    ) -> Incident:
        """Add an update to an incident.

        Args:
            incident_id: Incident UUID.
            update: Update data with message and new status.

        Returns:
            Updated :class:`Incident` object (re-fetched after posting the update).

        Raises:
            HyperpingNotFoundError: If the incident does not exist.
            HyperpingAPIError: On unexpected API errors.
        """
        validate_id(incident_id, "incident_id")  # H8
        payload = update.model_dump(exclude_none=True, by_alias=True)
        url = f"{Endpoint.INCIDENTS}/{incident_id}/updates"
        self._request("POST", url, json=payload)  # Returns {"message": "..."} — not a full Incident
        return self.get_incident(incident_id)

    def resolve_incident(self, incident_id: str, message: str | None = None) -> Incident:
        """Resolve an incident.

        Args:
            incident_id: Incident UUID.
            message: Optional resolution message. Defaults to
                ``"This incident has been resolved."``.

        Returns:
            Resolved :class:`Incident` object.

        Raises:
            HyperpingNotFoundError: If the incident does not exist.
            HyperpingAPIError: On unexpected API errors.
        """
        update = AddIncidentUpdateRequest(
            text=LocalizedText(en=message or "This incident has been resolved."),
            type=IncidentUpdateType.RESOLVED,
            date=datetime.now(UTC).isoformat(),
        )
        return self.add_incident_update(incident_id, update)

    def delete_incident(self, incident_id: str) -> None:
        """Delete an incident.

        Args:
            incident_id: Incident ID

        Raises:
            HyperpingNotFoundError: If incident not found
        """
        validate_id(incident_id, "incident_id")  # H8
        self._request("DELETE", f"{Endpoint.INCIDENTS}/{incident_id}")

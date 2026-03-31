"""Incident operations mixin for HyperpingClient.

Provides CRUD methods for Hyperping incidents (v3 API). Mixed into
:class:`~hyperping.client.HyperpingClient` at class definition time.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from hyperping.endpoints import Endpoint
from hyperping.models import (
    AddIncidentUpdateRequest,
    Incident,
    IncidentCreate,
    IncidentStatus,
    IncidentUpdateCreate,
    IncidentUpdateRequest,
    LocalizedText,
)

logger = logging.getLogger(__name__)


class IncidentsMixin:
    """Incident-related API operations."""

    def _request(  # type: ignore[empty-body]
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...  # provided by HyperpingClient

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

        response = self._request("GET", Endpoint.INCIDENTS, params=params if params else None)

        # Handle different response formats
        if isinstance(response, list):
            incidents_data = response
        elif "incidents" in response:
            incidents_data = response["incidents"]
        else:
            incidents_data = response.get("data", [])

        incidents = []
        skipped = 0
        for data in incidents_data:
            try:
                incidents.append(Incident.model_validate(data))
            except (ValueError, ValidationError) as e:
                skipped += 1
                logger.warning(f"Failed to parse incident data: {e}", extra={"data": data})

        if skipped:
            logger.warning(
                f"{skipped} of {len(incidents_data)} incidents could not be parsed and were skipped"
            )

        return incidents

    def get_incident(self, incident_id: str) -> Incident:
        """Get a single incident by ID.

        Args:
            incident_id: Incident ID

        Returns:
            Incident object

        Raises:
            HyperpingNotFoundError: If incident not found
        """
        response = self._request("GET", f"{Endpoint.INCIDENTS}/{incident_id}")
        return Incident.model_validate(response)

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
        response = self._request("POST", Endpoint.INCIDENTS, json=payload)
        # v3 API returns minimal response with just uuid
        if "uuid" in response and "title" not in response:
            # Fetch the full incident after creation
            return self.get_incident(response["uuid"])
        return Incident.model_validate(response)

    def update_incident(self, incident_id: str, update: IncidentUpdateRequest) -> Incident:
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
        payload = update.model_dump(exclude_none=True, by_alias=True)
        response = self._request("PUT", f"{Endpoint.INCIDENTS}/{incident_id}", json=payload)
        return Incident.model_validate(response)

    def add_incident_update(
        self,
        incident_id: str,
        update: IncidentUpdateCreate,
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
            type=IncidentStatus.RESOLVED,
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
        self._request("DELETE", f"{Endpoint.INCIDENTS}/{incident_id}")

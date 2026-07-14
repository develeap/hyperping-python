"""Async incident operations mixin for AsyncHyperpingClient.

Provides CRUD methods for Hyperping incidents (v3 API). Mixed into
:class:`~hyperping._async_client.AsyncHyperpingClient` at class definition time.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from hyperping._incidents_mixin import MAX_STATUSPAGES_PER_INCIDENT
from hyperping._protocols import _AsyncClientProtocol
from hyperping._utils import expect_dict, parse_list, unwrap_list, validate_id
from hyperping.endpoints import Endpoint
from hyperping.exceptions import (
    HyperpingAPIError,
    HyperpingPartialBatchError,
    HyperpingValidationError,
)
from hyperping.models import (
    AddIncidentUpdateRequest,
    Incident,
    IncidentCreate,
    IncidentUpdateRequest,
    IncidentUpdateType,
    LocalizedText,
)

logger = logging.getLogger(__name__)


class AsyncIncidentsMixin(_AsyncClientProtocol):
    """Async incident-related API operations."""

    async def list_incidents(self, status: str | None = None) -> list[Incident]:
        """List all incidents.

        Args:
            status: Filter by status (``investigating``, ``identified``,
                ``monitoring``, ``resolved``).

        Returns:
            List of :class:`Incident` objects.

        Raises:
            HyperpingAuthError: If the API key is invalid.
            HyperpingAPIError: On unexpected API errors.
        """
        params = {}
        if status:
            params["status"] = status

        response = await self._request("GET", Endpoint.INCIDENTS, params=params or None)
        return parse_list(unwrap_list(response, "incidents"), Incident, "incident")

    async def get_incident(self, incident_id: str) -> Incident:
        """Get a single incident by ID.

        Args:
            incident_id: Incident ID

        Returns:
            Incident object

        Raises:
            HyperpingNotFoundError: If incident not found
        """
        validate_id(incident_id, "incident_id")
        response = await self._request("GET", f"{Endpoint.INCIDENTS}/{incident_id}")
        return Incident.model_validate(expect_dict(response, "get_incident"))

    async def create_incident(self, incident: IncidentCreate) -> Incident:
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
        n_statuspages = len(incident.statuspages or [])
        if n_statuspages > MAX_STATUSPAGES_PER_INCIDENT:
            raise HyperpingValidationError(
                f"An incident can reference at most {MAX_STATUSPAGES_PER_INCIDENT} "
                f"status pages, but {n_statuspages} were supplied. Above this limit "
                f"Hyperping's API is expected to accept the create (returns a uuid) but "
                f"silently fail to persist it. Use create_incidents() to split the "
                f"status pages across multiple incidents."
            )
        payload = incident.model_dump(exclude_none=True, by_alias=True, mode="json")
        response = expect_dict(
            await self._request("POST", Endpoint.INCIDENTS, json=payload),
            "create_incident",
        )
        if "uuid" in response and "title" not in response:
            return await self.get_incident(response["uuid"])
        return Incident.model_validate(response)

    async def create_incidents(
        self,
        incident: IncidentCreate,
        *,
        chunk_size: int = MAX_STATUSPAGES_PER_INCIDENT,
    ) -> list[Incident]:
        """Async mirror of
        :meth:`~hyperping._incidents_mixin.IncidentsMixin.create_incidents`.
        """
        if not 1 <= chunk_size <= MAX_STATUSPAGES_PER_INCIDENT:
            raise HyperpingValidationError(
                f"chunk_size must be between 1 and "
                f"{MAX_STATUSPAGES_PER_INCIDENT}, got {chunk_size}."
            )
        pages = list(incident.statuspages or [])
        if len(pages) <= chunk_size:
            return [await self.create_incident(incident)]
        chunks = [pages[i : i + chunk_size] for i in range(0, len(pages), chunk_size)]
        created: list[Incident] = []
        for idx, chunk_pages in enumerate(chunks):
            chunk = incident.model_copy(update={"statuspages": chunk_pages})
            try:
                created.append(await self.create_incident(chunk))
            except HyperpingAPIError as exc:
                raise HyperpingPartialBatchError(
                    f"create_incidents failed on incident {idx + 1} of "
                    f"{len(chunks)}: {exc}. {len(created)} incident(s) were already "
                    f"created and remain live.",
                    created=created,
                    completed=len(created),
                    total=len(chunks),
                ) from exc
        return created

    async def update_incident(
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
        validate_id(incident_id, "incident_id")
        payload = update.model_dump(exclude_none=True, by_alias=True)
        response = expect_dict(
            await self._request("PUT", f"{Endpoint.INCIDENTS}/{incident_id}", json=payload),
            "update_incident",
        )
        return Incident.model_validate(response)

    async def add_incident_update(
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
        validate_id(incident_id, "incident_id")
        payload = update.model_dump(exclude_none=True, by_alias=True)
        url = f"{Endpoint.INCIDENTS}/{incident_id}/updates"
        await self._request("POST", url, json=payload)
        return await self.get_incident(incident_id)

    async def resolve_incident(self, incident_id: str, message: str | None = None) -> Incident:
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
        return await self.add_incident_update(incident_id, update)

    async def delete_incident(self, incident_id: str) -> None:
        """Delete an incident.

        Args:
            incident_id: Incident ID

        Raises:
            HyperpingNotFoundError: If incident not found
        """
        validate_id(incident_id, "incident_id")
        await self._request("DELETE", f"{Endpoint.INCIDENTS}/{incident_id}")

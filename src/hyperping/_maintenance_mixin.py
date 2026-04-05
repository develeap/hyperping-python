"""Maintenance operations mixin for HyperpingClient.

Provides CRUD methods for Hyperping maintenance windows (v1 API). Mixed into
:class:`~hyperping.client.HyperpingClient` at class definition time.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from hyperping._protocols import _ClientProtocol
from hyperping._utils import expect_dict, parse_list, unwrap_list, validate_id
from hyperping.endpoints import Endpoint
from hyperping.models import (
    Maintenance,
    MaintenanceCreate,
    MaintenanceUpdate,
)

logger = logging.getLogger(__name__)


class MaintenanceMixin(_ClientProtocol):
    """Maintenance-related API operations."""

    def list_maintenance(self, status: str | None = None) -> list[Maintenance]:
        """List all maintenance windows.

        Args:
            status: Filter by status (``scheduled``, ``in_progress``, ``completed``).

        Returns:
            List of :class:`Maintenance` objects. Windows that fail to parse
            are silently skipped with a warning log.

        Raises:
            HyperpingAuthError: If the API key is invalid.
            HyperpingAPIError: On unexpected API errors.
        """
        params = {}
        if status:
            params["status"] = status

        response = self._request(
            "GET", Endpoint.MAINTENANCE, params=params or None  # M20
        )

        # API returns {"maintenanceWindows": [...]} as of current version
        raw = unwrap_list(response, "maintenanceWindows")
        if not raw and isinstance(response, dict) and "maintenance" in response:
            raw = response["maintenance"]

        return parse_list(raw, Maintenance, "maintenance window")

    def get_maintenance(self, maintenance_id: str) -> Maintenance:
        """Get a single maintenance window by ID.

        Args:
            maintenance_id: Maintenance ID

        Returns:
            Maintenance object

        Raises:
            HyperpingNotFoundError: If maintenance not found
        """
        validate_id(maintenance_id, "maintenance_id")  # H8
        response = self._request("GET", f"{Endpoint.MAINTENANCE}/{maintenance_id}")
        return Maintenance.model_validate(expect_dict(response, "get_maintenance"))

    def create_maintenance(self, maintenance: MaintenanceCreate) -> Maintenance:
        """Create a new maintenance window.

        Args:
            maintenance: Maintenance creation data.

        Returns:
            Created :class:`Maintenance` object.

        Raises:
            HyperpingValidationError: If the payload fails server-side validation.
            HyperpingAPIError: On unexpected API errors.

        Note:
            v1 API returns {"uuid": "..."} on create, not the full maintenance object.
            The full maintenance window is fetched after creation.
        """
        payload = maintenance.model_dump(exclude_none=True, by_alias=True, mode="json")
        response = expect_dict(
            self._request("POST", Endpoint.MAINTENANCE, json=payload),
            "create_maintenance",
        )
        # v1 API returns minimal response with just uuid
        if "uuid" in response and "name" not in response:
            # Fetch the full maintenance after creation
            return self.get_maintenance(response["uuid"])
        return Maintenance.model_validate(response)

    def update_maintenance(
        self,
        maintenance_id: str,
        update: MaintenanceUpdate,
        raise_on_conflict: bool = False,
    ) -> Maintenance:
        """Update an existing maintenance window.

        The v1 API PUT requires a full payload (partial updates return 401).
        We fetch the current state and merge the supplied fields before sending.

        Concurrency note: this method performs a non-atomic read-modify-write.
        If two callers update the same window concurrently, the later write
        silently wins. ``raise_on_conflict`` is reserved for future ETag-based
        optimistic locking and has no effect today (H6).

        Args:
            maintenance_id: Maintenance ID
            update: Fields to update (only non-None fields are applied)
            raise_on_conflict: Reserved for future ETag support (no-op today).

        Returns:
            Updated Maintenance object
        """
        validate_id(maintenance_id, "maintenance_id")  # H8
        current = self.get_maintenance(maintenance_id)
        partial = update.model_dump(exclude_none=True, by_alias=True, mode="json")

        payload: dict[str, object] = {
            "name": current.name,
            "start_date": current.start_date,
            "end_date": current.end_date,
            "monitors": current.monitors,
        }
        payload.update(partial)

        response = expect_dict(
            self._request("PUT", f"{Endpoint.MAINTENANCE}/{maintenance_id}", json=payload),
            "update_maintenance",
        )
        return Maintenance.model_validate(response)

    def delete_maintenance(self, maintenance_id: str) -> None:
        """Delete a maintenance window.

        Args:
            maintenance_id: Maintenance ID

        Raises:
            HyperpingNotFoundError: If maintenance not found
        """
        validate_id(maintenance_id, "maintenance_id")  # H8
        self._request("DELETE", f"{Endpoint.MAINTENANCE}/{maintenance_id}")

    def get_active_maintenance(self) -> list[Maintenance]:
        """Get currently active maintenance windows.

        Returns:
            List of active :class:`Maintenance` objects.

        Raises:
            HyperpingAuthError: If the API key is invalid.
            HyperpingAPIError: On unexpected API errors.
        """
        all_maintenance = self.list_maintenance()
        now = datetime.now(UTC)

        return [m for m in all_maintenance if m.is_active(now)]

    def is_monitor_in_maintenance(self, monitor_uuid: str) -> bool:
        """Check if a monitor is currently in a maintenance window.

        Args:
            monitor_uuid: Monitor UUID to check.

        Returns:
            ``True`` if the monitor is in an active maintenance window.

        Raises:
            HyperpingAuthError: If the API key is invalid.
            HyperpingAPIError: On unexpected API errors.
        """
        active = self.get_active_maintenance()
        return any(m.affects_monitor(monitor_uuid) for m in active)

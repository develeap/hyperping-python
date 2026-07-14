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
from hyperping.exceptions import (
    HyperpingAPIError,
    HyperpingPartialBatchError,
    HyperpingValidationError,
)
from hyperping.models import (
    Maintenance,
    MaintenanceCreate,
    MaintenanceUpdate,
)

# Hyperping's v1 maintenance-windows API silently drops a create when the
# ``statuspages`` array exceeds this many entries: the POST still returns a
# ``{"uuid": ...}`` but the window is never persisted (the follow-up GET 404s
# and it is absent from the list). Empirically the cutoff is 51 (51 persists,
# 52+ vanishes), verified against the live API on 2026-07-14. Guard the create
# so callers get a clear error instead of a phantom window; split larger sets
# across multiple windows.
MAX_STATUSPAGES_PER_MAINTENANCE = 51

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
            "GET",
            Endpoint.MAINTENANCE,
            params=params or None,  # M20
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
        n_statuspages = len(maintenance.statuspages or [])
        if n_statuspages > MAX_STATUSPAGES_PER_MAINTENANCE:
            raise HyperpingValidationError(
                f"A maintenance window can reference at most "
                f"{MAX_STATUSPAGES_PER_MAINTENANCE} status pages, but {n_statuspages} "
                f"were supplied. Above this limit Hyperping's API accepts the create "
                f"(returns a uuid) but silently fails to persist the window. Split the "
                f"status pages across multiple maintenance windows."
            )
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

    def create_maintenance_windows(
        self,
        maintenance: MaintenanceCreate,
        *,
        chunk_size: int = MAX_STATUSPAGES_PER_MAINTENANCE,
    ) -> list[Maintenance]:
        """Create one or more windows, splitting status pages into chunks.

        Hyperping silently fails to persist a window with more than
        :data:`MAX_STATUSPAGES_PER_MAINTENANCE` status pages (see
        :meth:`create_maintenance`). This helper splits a large ``statuspages``
        list into consecutive windows of at most ``chunk_size`` pages so every
        page is covered. Each window carries the full ``monitors`` set (the API
        rejects a window with no monitors); overlapping monitor coverage across
        the windows is harmless.

        Args:
            maintenance: Creation data; ``statuspages`` may exceed the limit.
            chunk_size: Max status pages per window (1..
                :data:`MAX_STATUSPAGES_PER_MAINTENANCE`).

        Returns:
            The created windows in page order (a single window when the pages
            fit in one chunk).

        Raises:
            HyperpingValidationError: If ``chunk_size`` is out of range.
        """
        if not 1 <= chunk_size <= MAX_STATUSPAGES_PER_MAINTENANCE:
            raise HyperpingValidationError(
                f"chunk_size must be between 1 and "
                f"{MAX_STATUSPAGES_PER_MAINTENANCE}, got {chunk_size}."
            )
        pages = list(maintenance.statuspages or [])
        if len(pages) <= chunk_size:
            return [self.create_maintenance(maintenance)]
        chunks = [pages[i : i + chunk_size] for i in range(0, len(pages), chunk_size)]
        windows: list[Maintenance] = []
        for idx, chunk_pages in enumerate(chunks):
            chunk = maintenance.model_copy(update={"statuspages": chunk_pages})
            try:
                windows.append(self.create_maintenance(chunk))
            except HyperpingAPIError as exc:
                # Earlier windows are already live and are NOT rolled back; hand
                # them back so the caller can record or clean them up rather than
                # orphaning them silently.
                raise HyperpingPartialBatchError(
                    f"create_maintenance_windows failed on window {idx + 1} of "
                    f"{len(chunks)}: {exc}. {len(windows)} window(s) were already "
                    f"created and remain live.",
                    created=windows,
                    completed=len(windows),
                    total=len(chunks),
                ) from exc
        return windows

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

        payload: dict[str, object] = current.model_dump(
            mode="json",
            exclude_none=True,
            include={"name", "start_date", "end_date", "monitors"},
        )
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

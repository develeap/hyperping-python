"""Monitor operations mixin for HyperpingClient.

Provides CRUD and reporting methods for Hyperping monitors. Mixed into
:class:`~hyperping.client.HyperpingClient` at class definition time.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from hyperping._protocols import _ClientProtocol
from hyperping._utils import expect_dict, parse_list, unwrap_list, validate_id
from hyperping.endpoints import Endpoint
from hyperping.exceptions import HyperpingNotFoundError
from hyperping.models import (
    Monitor,
    MonitorCreate,
    MonitorReport,
    MonitorUpdate,
)

logger = logging.getLogger(__name__)

# Valid period values for reporting endpoints (M9)
_VALID_PERIODS: frozenset[str] = frozenset({"1h", "24h", "7d", "30d", "90d"})

# Writable fields for the Hyperping monitor PUT endpoint (M19: module-level constant)
_MONITOR_WRITABLE_FIELDS: frozenset[str] = frozenset(
    {
        "name",
        "url",
        "protocol",
        "http_method",
        "check_frequency",
        "regions",
        "request_headers",
        "request_body",
        "follow_redirects",
        "expected_status_code",
        "required_keyword",
        "paused",
        "port",
        "alerts_wait",
        "escalation_policy",
        "dns_record_type",
        "dns_nameserver",
        "dns_expected_answer",
    }
)


class MonitorsMixin(_ClientProtocol):
    """Monitor-related API operations."""

    def list_monitors(self) -> list[Monitor]:
        """List all monitors in the account.

        Returns:
            List of :class:`Monitor` objects. Monitors that fail to parse
            are silently skipped with a warning log.

        Raises:
            HyperpingAuthError: If the API key is invalid.
            HyperpingAPIError: On unexpected API errors.
        """
        response = self._request("GET", Endpoint.MONITORS)
        return parse_list(unwrap_list(response, "monitors"), Monitor, "monitor")

    def get_monitor(self, monitor_id: str) -> Monitor:
        """Get a single monitor by ID.

        Args:
            monitor_id: Monitor UUID

        Returns:
            Monitor object

        Raises:
            HyperpingNotFoundError: If monitor not found
        """
        validate_id(monitor_id, "monitor_id")  # H8
        response = self._request("GET", f"{Endpoint.MONITORS}/{monitor_id}")
        return Monitor.model_validate(expect_dict(response, "get_monitor"))

    def create_monitor(self, monitor: MonitorCreate) -> Monitor:
        """Create a new monitor.

        Args:
            monitor: Monitor creation data.

        Returns:
            Created :class:`Monitor` object.

        Raises:
            HyperpingValidationError: If the payload fails server-side validation.
            HyperpingAPIError: On unexpected API errors.
        """
        payload = monitor.model_dump(exclude_none=True)
        response = self._request("POST", Endpoint.MONITORS, json=payload)
        return Monitor.model_validate(expect_dict(response, "create_monitor"))

    def update_monitor(
        self,
        monitor_id: str,
        update: MonitorUpdate,
        raise_on_conflict: bool = False,
    ) -> Monitor:
        """Update an existing monitor using read-modify-write.

        The Hyperping v1 PUT endpoint requires a full payload. We fetch the
        current state first and apply the update on top to avoid clobbering
        fields not included in the partial update.

        Concurrency note: this method performs a non-atomic read-modify-write
        against the Hyperping API. If two callers update the same monitor
        concurrently, the later write silently wins. The ``raise_on_conflict``
        parameter is reserved for future ETag-based optimistic locking support
        and has no effect today (H6).

        Args:
            monitor_id: Monitor UUID
            update: Fields to update
            raise_on_conflict: Reserved for future ETag support (no-op today).

        Returns:
            Updated Monitor object
        """
        validate_id(monitor_id, "monitor_id")  # H8
        current = self.get_monitor(monitor_id)

        # Build full payload from current writable state
        payload: dict[str, Any] = current.model_dump(
            mode="json",
            exclude_none=True,
            include=set(_MONITOR_WRITABLE_FIELDS),
        )

        # Apply the requested changes on top of current state
        payload.update(update.model_dump(exclude_none=True))

        response = self._request("PUT", f"{Endpoint.MONITORS}/{monitor_id}", json=payload)
        return Monitor.model_validate(expect_dict(response, "update_monitor"))

    def delete_monitor(self, monitor_id: str) -> None:
        """Delete a monitor.

        Args:
            monitor_id: Monitor UUID

        Raises:
            HyperpingNotFoundError: If monitor not found
        """
        validate_id(monitor_id, "monitor_id")  # H8
        self._request("DELETE", f"{Endpoint.MONITORS}/{monitor_id}")

    def pause_monitor(self, monitor_id: str) -> Monitor:
        """Pause a monitor.

        Args:
            monitor_id: Monitor UUID

        Returns:
            Updated Monitor object
        """
        return self.update_monitor(monitor_id, MonitorUpdate(paused=True))

    def resume_monitor(self, monitor_id: str) -> Monitor:
        """Resume a paused monitor.

        Args:
            monitor_id: Monitor UUID

        Returns:
            Updated Monitor object
        """
        return self.update_monitor(monitor_id, MonitorUpdate(paused=False))

    def get_all_reports(
        self,
        period: Literal["1h", "24h", "7d", "30d", "90d"] = "30d",
    ) -> list[MonitorReport]:
        """Get uptime reports for all monitors in a single batch call.

        Uses the v2 batch endpoint — one API call for all monitors.

        Args:
            period: Report period. One of ``1h``, ``24h``, ``7d``, ``30d``, ``90d``.

        Returns:
            List of :class:`MonitorReport` objects. Reports that fail to parse
            are silently skipped with a warning log.

        Raises:
            ValueError: If *period* is not a recognised value (M9).
            HyperpingAuthError: If the API key is invalid.
            HyperpingAPIError: On unexpected API errors.
        """
        if period not in _VALID_PERIODS:
            raise ValueError(
                f"Invalid period {period!r}. Valid values: {sorted(_VALID_PERIODS)}"
            )
        response = expect_dict(
            self._request("GET", Endpoint.REPORTS, params={"period": period}),
            "get_all_reports",
        )
        period_info = response.get("period", {})
        monitors_data = response.get("monitors", [])

        # Inject the shared period block into each monitor dict before parsing
        augmented = [{**m, "period": period_info} for m in monitors_data]
        return parse_list(augmented, MonitorReport, "monitor report")

    def get_monitor_report(
        self,
        monitor_id: str,
        period: Literal["1h", "24h", "7d", "30d", "90d"] = "30d",
    ) -> MonitorReport:
        """Get uptime report for a single monitor.

        Fetches the batch report endpoint and filters by monitor UUID.

        Performance note: this method fetches reports for ALL monitors and
        performs a linear scan to find the requested one (O(n) where n is
        account monitor count). If Hyperping adds a single-monitor report
        endpoint (e.g. ``GET /v2/reporting/monitor-reports?monitor_uuid=``),
        this implementation should be updated to use it directly (H7).

        Args:
            monitor_id: Monitor UUID
            period: Report period (1h, 24h, 7d, 30d, 90d)

        Returns:
            MonitorReport object

        Raises:
            HyperpingNotFoundError: If no report found for the monitor
        """
        validate_id(monitor_id, "monitor_id")  # H8
        for r in self.get_all_reports(period):
            if r.uuid == monitor_id:
                return r
        raise HyperpingNotFoundError(f"No report found for monitor: {monitor_id}")

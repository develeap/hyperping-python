"""Monitor operations mixin for HyperpingClient.

Provides CRUD and reporting methods for Hyperping monitors. Mixed into
:class:`~hyperping.client.HyperpingClient` at class definition time.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from hyperping.endpoints import Endpoint
from hyperping.exceptions import HyperpingNotFoundError
from hyperping.models import (
    Monitor,
    MonitorCreate,
    MonitorReport,
    MonitorUpdate,
)

logger = logging.getLogger(__name__)


class MonitorsMixin:
    """Monitor-related API operations."""

    def _request(  # type: ignore[empty-body]
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...  # provided by HyperpingClient

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

        # Handle different response formats
        if isinstance(response, list):
            monitors_data = response
        elif "monitors" in response:
            monitors_data = response["monitors"]
        else:
            monitors_data = response.get("data", [])

        monitors = []
        skipped = 0
        for data in monitors_data:
            try:
                monitors.append(Monitor.model_validate(data))
            except (ValueError, ValidationError) as e:
                skipped += 1
                logger.warning(f"Failed to parse monitor data: {e}", extra={"data": data})

        if skipped:
            logger.warning(
                f"{skipped} of {len(monitors_data)} monitors could not be parsed and were skipped"
            )

        return monitors

    def get_monitor(self, monitor_id: str) -> Monitor:
        """Get a single monitor by ID.

        Args:
            monitor_id: Monitor UUID

        Returns:
            Monitor object

        Raises:
            HyperpingNotFoundError: If monitor not found
        """
        response = self._request("GET", f"{Endpoint.MONITORS}/{monitor_id}")
        return Monitor.model_validate(response)

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
        return Monitor.model_validate(response)

    # Writable fields for the Hyperping monitor PUT endpoint
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

    def update_monitor(self, monitor_id: str, update: MonitorUpdate) -> Monitor:
        """Update an existing monitor using read-modify-write.

        The Hyperping v1 PUT endpoint requires a full payload. We fetch the
        current state first and apply the update on top to avoid clobbering
        fields not included in the partial update.

        Args:
            monitor_id: Monitor UUID
            update: Fields to update

        Returns:
            Updated Monitor object
        """
        current = self.get_monitor(monitor_id)

        # Build full payload from current writable state
        payload: dict[str, Any] = current.model_dump(
            mode="json",
            exclude_none=True,
            include=set(self._MONITOR_WRITABLE_FIELDS),
        )

        # Apply the requested changes on top of current state
        payload.update(update.model_dump(exclude_none=True))

        response = self._request("PUT", f"{Endpoint.MONITORS}/{monitor_id}", json=payload)
        return Monitor.model_validate(response)

    def delete_monitor(self, monitor_id: str) -> None:
        """Delete a monitor.

        Args:
            monitor_id: Monitor UUID

        Raises:
            HyperpingNotFoundError: If monitor not found
        """
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

    def get_all_reports(self, period: str = "30d") -> list[MonitorReport]:
        """Get uptime reports for all monitors in a single batch call.

        Uses the v2 batch endpoint -- one API call for all monitors.

        Args:
            period: Report period (``1h``, ``24h``, ``7d``, ``30d``, ``90d``).

        Returns:
            List of :class:`MonitorReport` objects. Reports that fail to parse
            are silently skipped with a warning log.

        Raises:
            HyperpingAuthError: If the API key is invalid.
            HyperpingAPIError: On unexpected API errors.
        """
        response = self._request("GET", Endpoint.REPORTS, params={"period": period})
        period_info = response.get("period", {})
        monitors_data = response.get("monitors", [])

        reports = []
        skipped = 0
        for m in monitors_data:
            try:
                reports.append(MonitorReport.model_validate({**m, "period": period_info}))
            except (ValueError, ValidationError) as e:
                skipped += 1
                logger.warning(f"Failed to parse monitor report: {e}", extra={"data": m})

        if skipped:
            logger.warning(
                f"{skipped} of {len(monitors_data)} reports could not be parsed and were skipped"
            )

        return reports

    def get_monitor_report(
        self,
        monitor_id: str,
        period: str = "30d",
    ) -> MonitorReport:
        """Get uptime report for a single monitor.

        Fetches the batch report and filters by monitor UUID.

        Args:
            monitor_id: Monitor UUID
            period: Report period (1h, 24h, 7d, 30d, 90d)

        Returns:
            MonitorReport object

        Raises:
            HyperpingNotFoundError: If no report found for the monitor
        """
        for r in self.get_all_reports(period):
            if r.uuid == monitor_id:
                return r
        raise HyperpingNotFoundError(f"No report found for monitor: {monitor_id}")

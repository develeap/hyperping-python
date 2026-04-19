"""Observability mixin: anomalies, probe logs, alert history."""

from typing import Any

from hyperping._protocols import _ClientProtocol
from hyperping._utils import parse_list, validate_id
from hyperping.endpoints import Endpoint
from hyperping.exceptions import HyperpingAPIError, HyperpingNotFoundError
from hyperping.models._observability_models import (
    AlertNotification,
    MonitorAnomaly,
    ProbeLog,
)


class ObservabilityMixin(_ClientProtocol):
    """Observability API operations: anomalies, logs, alerts."""

    def get_monitor_anomalies(self, monitor_uuid: str) -> list[MonitorAnomaly]:
        """Get detected anomalies for a monitor.

        Args:
            monitor_uuid: Monitor UUID.

        Returns:
            List of :class:`~hyperping.models.MonitorAnomaly` objects.
            Returns empty list on 404.
        """
        validate_id(monitor_uuid, "monitor_uuid")
        try:
            # Path is speculative; derived from MCP tool name.
            result = self._request("GET", f"{Endpoint.MONITORS}/{monitor_uuid}/anomalies")
        except (HyperpingNotFoundError, HyperpingAPIError):
            return []
        items = result if isinstance(result, list) else []
        return parse_list(items, MonitorAnomaly, "anomaly")

    def get_monitor_http_logs(
        self,
        monitor_uuid: str,
        page: int = 0,
        limit: int = 50,
        level: str | None = None,
    ) -> list[ProbeLog]:
        """Get recent HTTP probe logs for a monitor.

        Args:
            monitor_uuid: Monitor UUID.
            page: Page number (0-indexed).
            limit: Results per page (max 200).
            level: Filter by log level (e.g., ``"error"``).

        Returns:
            List of :class:`~hyperping.models.ProbeLog` objects.
            Returns empty list on 404.
        """
        validate_id(monitor_uuid, "monitor_uuid")
        params: dict[str, Any] = {"page": page, "limit": limit}
        if level is not None:
            params["level"] = level
        try:
            # Path is speculative; derived from MCP tool name.
            result = self._request(
                "GET",
                f"{Endpoint.MONITORS}/{monitor_uuid}/http-logs",
                params=params,
            )
        except (HyperpingNotFoundError, HyperpingAPIError):
            return []
        items = result if isinstance(result, list) else []
        return parse_list(items, ProbeLog, "probe_log")

    def list_recent_alerts(
        self,
        from_dt: str | None = None,
        to_dt: str | None = None,
        monitor_uuids: list[str] | None = None,
    ) -> list[AlertNotification]:
        """Get recent alert notification history.

        Args:
            from_dt: Start time filter (ISO 8601).
            to_dt: End time filter (ISO 8601).
            monitor_uuids: Filter to specific monitors.

        Returns:
            List of :class:`~hyperping.models.AlertNotification` objects.
            Returns empty list on 404.
        """
        params: dict[str, Any] = {}
        if from_dt is not None:
            params["from"] = from_dt
        if to_dt is not None:
            params["to"] = to_dt
        if monitor_uuids:
            params["monitor_uuids"] = ",".join(monitor_uuids)
        try:
            result = self._request("GET", Endpoint.ALERTS, params=params)
        except (HyperpingNotFoundError, HyperpingAPIError):
            return []
        items = result if isinstance(result, list) else []
        return parse_list(items, AlertNotification, "alert")

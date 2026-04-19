"""Async observability mixin: anomalies, probe logs, alert history."""

from typing import Any

from hyperping._protocols import _AsyncClientProtocol
from hyperping._utils import parse_list, validate_id
from hyperping.endpoints import Endpoint
from hyperping.models._observability_models import (
    AlertNotification,
    MonitorAnomaly,
    ProbeLog,
)


class AsyncObservabilityMixin(_AsyncClientProtocol):
    """Async observability API operations."""

    async def get_monitor_anomalies(self, monitor_uuid: str) -> list[MonitorAnomaly]:
        """Get detected anomalies for a monitor."""
        validate_id(monitor_uuid, "monitor_uuid")
        try:
            result = await self._request("GET", f"{Endpoint.MONITORS}/{monitor_uuid}/anomalies")
        except Exception:
            return []
        items = result if isinstance(result, list) else []
        return parse_list(items, MonitorAnomaly, "anomaly")

    async def get_monitor_http_logs(
        self, monitor_uuid: str, page: int = 0, limit: int = 50, level: str | None = None
    ) -> list[ProbeLog]:
        """Get recent HTTP probe logs for a monitor."""
        validate_id(monitor_uuid, "monitor_uuid")
        params: dict[str, Any] = {"page": page, "limit": limit}
        if level is not None:
            params["level"] = level
        try:
            result = await self._request(
                "GET", f"{Endpoint.MONITORS}/{monitor_uuid}/http-logs", params=params
            )
        except Exception:
            return []
        items = result if isinstance(result, list) else []
        return parse_list(items, ProbeLog, "probe_log")

    async def list_recent_alerts(
        self,
        from_dt: str | None = None,
        to_dt: str | None = None,
        monitor_uuids: list[str] | None = None,
    ) -> list[AlertNotification]:
        """Get recent alert notification history."""
        params: dict[str, Any] = {}
        if from_dt is not None:
            params["from"] = from_dt
        if to_dt is not None:
            params["to"] = to_dt
        if monitor_uuids:
            params["monitor_uuids"] = ",".join(monitor_uuids)
        try:
            result = await self._request("GET", Endpoint.ALERTS, params=params)
        except Exception:
            return []
        items = result if isinstance(result, list) else []
        return parse_list(items, AlertNotification, "alert")

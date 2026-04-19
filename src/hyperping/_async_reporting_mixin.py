"""Async reporting mixin: status summary, response time, MTTA."""

from typing import Any

from hyperping._protocols import _AsyncClientProtocol
from hyperping._utils import expect_dict, validate_id
from hyperping.endpoints import Endpoint
from hyperping.models._reporting_models import StatusSummary


class AsyncReportingMixin(_AsyncClientProtocol):
    """Async status and reporting API operations."""

    async def get_status_summary(self) -> StatusSummary:
        """Get aggregate status counts for the project."""
        result = await self._request("GET", Endpoint.STATUS_SUMMARY)
        return StatusSummary.model_validate(expect_dict(result, "get_status_summary"))

    async def get_monitor_response_time(
        self, monitor_uuid: str, period: str = "24h"
    ) -> dict[str, Any]:
        """Get latency percentiles for a monitor."""
        validate_id(monitor_uuid, "monitor_uuid")
        result = await self._request(
            "GET",
            f"/v2/reporting/response-time/{monitor_uuid}",
            params={"period": period},
        )
        return expect_dict(result, "get_monitor_response_time")

    async def get_monitor_mtta(self, monitor_uuid: str, period: str = "30d") -> dict[str, Any]:
        """Get Mean Time To Acknowledge for a monitor."""
        validate_id(monitor_uuid, "monitor_uuid")
        result = await self._request(
            "GET",
            f"/v2/reporting/mtta/{monitor_uuid}",
            params={"period": period},
        )
        return expect_dict(result, "get_monitor_mtta")

"""Reporting mixin: status summary, response time, MTTA."""

from typing import Any

from hyperping._protocols import _ClientProtocol
from hyperping._utils import expect_dict, validate_id
from hyperping.endpoints import Endpoint
from hyperping.models._reporting_models import StatusSummary


class ReportingMixin(_ClientProtocol):
    """Status and reporting API operations."""

    def get_status_summary(self) -> StatusSummary:
        """Get aggregate status counts for the project.

        Returns:
            :class:`~hyperping.models.StatusSummary` with up/down/paused counts.
        """
        result = self._request("GET", Endpoint.STATUS_SUMMARY)
        return StatusSummary.model_validate(expect_dict(result, "get_status_summary"))

    def get_monitor_response_time(
        self,
        monitor_uuid: str,
        period: str = "24h",
    ) -> dict[str, Any]:
        """Get latency percentiles for a monitor.

        Args:
            monitor_uuid: Monitor UUID.
            period: Time period (e.g., ``"1h"``, ``"24h"``, ``"7d"``).

        Returns:
            Dict with latency percentile data (shape depends on API).

        Raises:
            HyperpingNotFoundError: If monitor not found.
        """
        validate_id(monitor_uuid, "monitor_uuid")
        # Path is speculative; derived from MCP tool name.
        result = self._request(
            "GET",
            f"/v2/reporting/response-time/{monitor_uuid}",
            params={"period": period},
        )
        return expect_dict(result, "get_monitor_response_time")

    def get_monitor_mtta(
        self,
        monitor_uuid: str,
        period: str = "30d",
    ) -> dict[str, Any]:
        """Get Mean Time To Acknowledge for a monitor.

        Args:
            monitor_uuid: Monitor UUID.
            period: Time period (e.g., ``"7d"``, ``"30d"``).

        Returns:
            Dict with MTTA data (shape depends on API).

        Raises:
            HyperpingNotFoundError: If monitor not found.
        """
        validate_id(monitor_uuid, "monitor_uuid")
        # Path is speculative; derived from MCP tool name.
        result = self._request(
            "GET",
            f"/v2/reporting/mtta/{monitor_uuid}",
            params={"period": period},
        )
        return expect_dict(result, "get_monitor_mtta")

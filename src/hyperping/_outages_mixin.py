"""Outage operations mixin for HyperpingClient.

Provides methods for managing auto-detected outages (v2 API). Mixed into
:class:`~hyperping.client.HyperpingClient` at class definition time.
"""

from __future__ import annotations

import logging
from typing import Any

from hyperping._protocols import _ClientProtocol
from hyperping._utils import collect_all_pages, expect_dict, parse_list, validate_id
from hyperping.endpoints import Endpoint
from hyperping.exceptions import HyperpingNotFoundError
from hyperping.models import Outage, OutageAction

logger = logging.getLogger(__name__)

_VALID_STATUSES: frozenset[str] = frozenset({"all", "ongoing", "resolved"})
_VALID_TYPES: frozenset[str] = frozenset({"all", "manual", "monitor"})


class OutagesMixin(_ClientProtocol):
    """Outage-related API operations."""

    def list_outages(
        self,
        page: int | None = None,
        status: str = "all",
        outage_type: str = "all",
    ) -> list[Outage]:
        """List auto-detected outages.

        The Hyperping outages endpoint is paginated (0-indexed ``page`` param).
        When *page* is ``None`` (default), all pages are fetched automatically.
        Pass an explicit ``page`` index to retrieve a single page.

        Args:
            page: Page index (0-based). ``None`` fetches all pages.
            status: Filter by outage status. One of ``"all"``, ``"ongoing"``,
                ``"resolved"``. Default ``"all"``.
            outage_type: Filter by outage type. One of ``"all"``,
                ``"manual"``, ``"monitor"``. Default ``"all"``.

        Returns:
            List of :class:`~hyperping.models.Outage` objects.
            Empty list if the endpoint is not available (404).

        Raises:
            ValueError: If *status* or *outage_type* is not a recognised value.
        """
        if status not in _VALID_STATUSES:
            raise ValueError(
                f"Invalid status {status!r}. Valid values: {sorted(_VALID_STATUSES)}"
            )
        if outage_type not in _VALID_TYPES:
            raise ValueError(
                f"Invalid outage_type {outage_type!r}. Valid values: {sorted(_VALID_TYPES)}"
            )

        params: dict[str, Any] = {}
        if status != "all":
            params["status"] = status
        if outage_type != "all":
            params["type"] = outage_type

        try:
            if page is not None:
                params["page"] = page
                data = self._request("GET", Endpoint.OUTAGES, params=params)
                raw: list[Any] = (
                    data.get("outages", []) if isinstance(data, dict)
                    else (data if isinstance(data, list) else [])
                )
                return parse_list(raw, Outage, "outage")
            return collect_all_pages(
                self._request, Endpoint.OUTAGES, "outages", params or None, Outage, "outage"
            )
        except HyperpingNotFoundError:
            logger.debug("Outage endpoint not available (404)")
            return []

    def acknowledge_outage(self, outage_id: str, message: str | None = None) -> OutageAction:
        """Acknowledge an outage.

        Args:
            outage_id: Outage UUID.
            message: Optional acknowledgement message.

        Returns:
            :class:`~hyperping.models.OutageAction` with the action result.

        Raises:
            HyperpingNotFoundError: If outage not found.
        """
        validate_id(outage_id, "outage_id")  # H8
        json_body = {"message": message} if message else None
        result = self._request(
            "POST",
            f"{Endpoint.OUTAGES}/{outage_id}/acknowledge",
            json=json_body,
        )
        return OutageAction.from_raw(expect_dict(result, "outage operation"))

    def resolve_outage(self, outage_id: str, message: str | None = None) -> OutageAction:
        """Resolve an outage.

        Args:
            outage_id: Outage UUID.
            message: Optional resolution message.

        Returns:
            :class:`~hyperping.models.OutageAction` with the action result.

        Raises:
            HyperpingNotFoundError: If outage not found.
        """
        validate_id(outage_id, "outage_id")  # H8
        json_body = {"message": message} if message else None
        result = self._request(
            "POST",
            f"{Endpoint.OUTAGES}/{outage_id}/resolve",
            json=json_body,
        )
        return OutageAction.from_raw(expect_dict(result, "outage operation"))

    def escalate_outage(self, outage_id: str) -> OutageAction:
        """Escalate an outage.

        Args:
            outage_id: Outage UUID.

        Returns:
            :class:`~hyperping.models.OutageAction` with the action result.

        Raises:
            HyperpingNotFoundError: If outage not found.
        """
        validate_id(outage_id, "outage_id")  # H8
        result = self._request("POST", f"{Endpoint.OUTAGES}/{outage_id}/escalate")
        return OutageAction.from_raw(expect_dict(result, "outage operation"))

    def unacknowledge_outage(self, outage_id: str) -> OutageAction:
        """Unacknowledge an outage.

        Args:
            outage_id: Outage UUID.

        Returns:
            :class:`~hyperping.models.OutageAction` with the action result.

        Raises:
            HyperpingNotFoundError: If outage not found.
        """
        validate_id(outage_id, "outage_id")  # H8
        result = self._request(
            "POST", f"{Endpoint.OUTAGES}/{outage_id}/unacknowledge"
        )
        return OutageAction.from_raw(expect_dict(result, "outage operation"))

    def delete_outage(self, outage_id: str) -> None:
        """Delete an outage.

        Args:
            outage_id: Outage UUID.

        Raises:
            HyperpingNotFoundError: If outage not found.
        """
        validate_id(outage_id, "outage_id")  # H8
        self._request("DELETE", f"{Endpoint.OUTAGES}/{outage_id}")

    def create_outage(self, monitor_uuid: str) -> Outage:
        """Create a manual outage for a monitor.

        Args:
            monitor_uuid: Monitor UUID to create the outage for.

        Returns:
            Created :class:`~hyperping.models.Outage` object.

        Raises:
            HyperpingValidationError: If the payload fails server-side validation.
            HyperpingAPIError: On unexpected API errors.
        """
        payload = {"monitor_uuid": monitor_uuid}
        result = self._request("POST", Endpoint.OUTAGES, json=payload)
        return Outage.model_validate(expect_dict(result, "create_outage"))

    def get_outage(self, outage_id: str) -> Outage:
        """Get a single outage by ID.

        Args:
            outage_id: Outage UUID.

        Returns:
            :class:`~hyperping.models.Outage` object.

        Raises:
            HyperpingNotFoundError: If outage not found.
        """
        validate_id(outage_id, "outage_id")  # H8
        result = self._request("GET", f"{Endpoint.OUTAGES}/{outage_id}")
        return Outage.model_validate(expect_dict(result, "get_outage"))

"""Async outage operations mixin for AsyncHyperpingClient.

Provides methods for managing auto-detected outages (v2 API). Mixed into
:class:`~hyperping._async_client.AsyncHyperpingClient` at class definition time.
"""

from __future__ import annotations

import logging
from typing import Any

from hyperping._protocols import _AsyncClientProtocol
from hyperping._utils import expect_dict, parse_list, validate_id
from hyperping.endpoints import Endpoint
from hyperping.exceptions import HyperpingNotFoundError
from hyperping.models import Outage, OutageAction

logger = logging.getLogger(__name__)


class AsyncOutagesMixin(_AsyncClientProtocol):
    """Async outage-related API operations."""

    async def list_outages(self) -> list[Outage]:
        """List auto-detected outages.

        Returns:
            List of :class:`~hyperping.models.Outage` objects.
            Empty list if the endpoint is not available (404).
        """
        try:
            data = await self._request("GET", Endpoint.OUTAGES)
            if isinstance(data, list):
                raw: list[Any] = data
            elif isinstance(data, dict) and "outages" in data:
                raw = data["outages"]
            else:
                return []
            return parse_list(raw, Outage, "outage")
        except HyperpingNotFoundError:
            logger.debug("Outage endpoint not available (404)")
            return []

    async def acknowledge_outage(
        self, outage_id: str, message: str | None = None
    ) -> OutageAction:
        """Acknowledge an outage.

        Args:
            outage_id: Outage UUID.
            message: Optional acknowledgement message.

        Returns:
            :class:`~hyperping.models.OutageAction` with the action result.

        Raises:
            HyperpingNotFoundError: If outage not found.
        """
        validate_id(outage_id, "outage_id")
        json_body = {"message": message} if message else None
        result = await self._request(
            "POST",
            f"{Endpoint.OUTAGES}/{outage_id}/acknowledge",
            json=json_body,
        )
        return OutageAction.from_raw(expect_dict(result, "outage operation"))

    async def resolve_outage(
        self, outage_id: str, message: str | None = None
    ) -> OutageAction:
        """Resolve an outage.

        Args:
            outage_id: Outage UUID.
            message: Optional resolution message.

        Returns:
            :class:`~hyperping.models.OutageAction` with the action result.

        Raises:
            HyperpingNotFoundError: If outage not found.
        """
        validate_id(outage_id, "outage_id")
        json_body = {"message": message} if message else None
        result = await self._request(
            "POST",
            f"{Endpoint.OUTAGES}/{outage_id}/resolve",
            json=json_body,
        )
        return OutageAction.from_raw(expect_dict(result, "outage operation"))

    async def escalate_outage(self, outage_id: str) -> OutageAction:
        """Escalate an outage.

        Args:
            outage_id: Outage UUID.

        Returns:
            :class:`~hyperping.models.OutageAction` with the action result.

        Raises:
            HyperpingNotFoundError: If outage not found.
        """
        validate_id(outage_id, "outage_id")
        result = await self._request("POST", f"{Endpoint.OUTAGES}/{outage_id}/escalate")
        return OutageAction.from_raw(expect_dict(result, "outage operation"))

    async def unacknowledge_outage(self, outage_id: str) -> OutageAction:
        """Unacknowledge an outage.

        Args:
            outage_id: Outage UUID.

        Returns:
            :class:`~hyperping.models.OutageAction` with the action result.

        Raises:
            HyperpingNotFoundError: If outage not found.
        """
        validate_id(outage_id, "outage_id")
        result = await self._request(
            "POST", f"{Endpoint.OUTAGES}/{outage_id}/unacknowledge"
        )
        return OutageAction.from_raw(expect_dict(result, "outage operation"))

    async def delete_outage(self, outage_id: str) -> None:
        """Delete an outage.

        Args:
            outage_id: Outage UUID.

        Raises:
            HyperpingNotFoundError: If outage not found.
        """
        validate_id(outage_id, "outage_id")
        await self._request("DELETE", f"{Endpoint.OUTAGES}/{outage_id}")

    async def create_outage(self, monitor_uuid: str) -> Outage:
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
        result = await self._request("POST", Endpoint.OUTAGES, json=payload)
        return Outage.model_validate(expect_dict(result, "create_outage"))

    async def get_outage(self, outage_id: str) -> Outage:
        """Get a single outage by ID.

        Args:
            outage_id: Outage UUID.

        Returns:
            :class:`~hyperping.models.Outage` object.

        Raises:
            HyperpingNotFoundError: If outage not found.
        """
        validate_id(outage_id, "outage_id")
        result = await self._request("GET", f"{Endpoint.OUTAGES}/{outage_id}")
        return Outage.model_validate(expect_dict(result, "get_outage"))

"""Outage operations mixin for HyperpingClient.

Provides methods for managing auto-detected outages (v2 API). Mixed into
:class:`~hyperping.client.HyperpingClient` at class definition time.
"""

from __future__ import annotations

import logging
from typing import Any

from hyperping._protocols import _ClientProtocol
from hyperping._utils import expect_dict, parse_list, validate_id
from hyperping.endpoints import Endpoint
from hyperping.exceptions import HyperpingNotFoundError
from hyperping.models import Outage

logger = logging.getLogger(__name__)


class OutagesMixin(_ClientProtocol):
    """Outage-related API operations."""

    def list_outages(self) -> list[Outage]:
        """List auto-detected outages.

        Returns:
            List of :class:`~hyperping.models.Outage` objects.
            Empty list if the endpoint is not available (404).
        """
        try:
            data = self._request("GET", Endpoint.OUTAGES)
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

    def acknowledge_outage(self, outage_id: str, message: str | None = None) -> dict[str, Any]:
        """Acknowledge an outage.

        Args:
            outage_id: Outage UUID.
            message: Optional acknowledgement message.

        Returns:
            API response dict.

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
        return expect_dict(result, "outage operation")

    def resolve_outage(self, outage_id: str, message: str | None = None) -> dict[str, Any]:
        """Resolve an outage.

        Args:
            outage_id: Outage UUID.
            message: Optional resolution message.

        Returns:
            API response dict.

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
        return expect_dict(result, "outage operation")

    def escalate_outage(self, outage_id: str) -> dict[str, Any]:
        """Escalate an outage.

        Args:
            outage_id: Outage UUID.

        Returns:
            API response dict.

        Raises:
            HyperpingNotFoundError: If outage not found.
        """
        validate_id(outage_id, "outage_id")  # H8
        result = self._request("POST", f"{Endpoint.OUTAGES}/{outage_id}/escalate")
        return expect_dict(result, "outage operation")

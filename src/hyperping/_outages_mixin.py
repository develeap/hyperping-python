"""Outage operations mixin for HyperpingClient.

Provides methods for managing auto-detected outages (v2 API). Mixed into
:class:`~hyperping.client.HyperpingClient` at class definition time.
"""

from __future__ import annotations

import logging
from typing import Any, cast

from hyperping.endpoints import Endpoint
from hyperping.exceptions import HyperpingNotFoundError

logger = logging.getLogger(__name__)


class OutagesMixin:
    """Outage-related API operations."""

    def _request(  # type: ignore[empty-body]
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...  # provided by HyperpingClient

    def list_outages(self) -> list[dict[str, Any]]:
        """List auto-detected outages.

        Returns raw dicts since the exact API response shape is not fully
        documented. The command layer normalizes the response defensively.

        Returns:
            List of outage dicts from the API.
            Empty list if the endpoint is not available (404).
        """
        try:
            data = self._request("GET", Endpoint.OUTAGES)
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "outages" in data:
                return cast(list[dict[str, Any]], data["outages"])
            return []
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
        json_body = {"message": message} if message else None
        return self._request(
            "POST",
            f"{Endpoint.OUTAGES}/{outage_id}/acknowledge",
            json=json_body,
        )

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
        json_body = {"message": message} if message else None
        return self._request(
            "POST",
            f"{Endpoint.OUTAGES}/{outage_id}/resolve",
            json=json_body,
        )

    def escalate_outage(self, outage_id: str) -> dict[str, Any]:
        """Escalate an outage.

        Args:
            outage_id: Outage UUID.

        Returns:
            API response dict.

        Raises:
            HyperpingNotFoundError: If outage not found.
        """
        return self._request("POST", f"{Endpoint.OUTAGES}/{outage_id}/escalate")

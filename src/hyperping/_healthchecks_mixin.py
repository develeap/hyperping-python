"""Healthcheck operations mixin for HyperpingClient.

Provides CRUD and pause/resume methods for Hyperping healthchecks (push-based
cron/heartbeat monitors). Mixed into
:class:`~hyperping.client.HyperpingClient` at class definition time.
"""

from __future__ import annotations

import logging
from typing import Any

from hyperping._protocols import _ClientProtocol
from hyperping._utils import expect_dict, parse_list, validate_id
from hyperping.endpoints import Endpoint
from hyperping.exceptions import HyperpingNotFoundError
from hyperping.models import Healthcheck, HealthcheckCreate, HealthcheckUpdate

logger = logging.getLogger(__name__)


class HealthchecksMixin(_ClientProtocol):
    """Healthcheck-related API operations."""

    def list_healthchecks(self) -> list[Healthcheck]:
        """List all healthchecks in the account.

        Returns:
            List of :class:`~hyperping.models.Healthcheck` objects.
            Empty list if the endpoint returns 404.

        Raises:
            HyperpingAuthError: If the API key is invalid.
            HyperpingAPIError: On unexpected API errors.
        """
        try:
            data = self._request("GET", Endpoint.HEALTHCHECKS)
            raw: list[Any]
            if isinstance(data, list):
                raw = data
            elif isinstance(data, dict) and "healthchecks" in data:
                raw = data["healthchecks"]
            else:
                return []
            return parse_list(raw, Healthcheck, "healthcheck")
        except HyperpingNotFoundError:
            logger.debug("Healthcheck endpoint not available (404)")
            return []

    def get_healthcheck(self, healthcheck_id: str) -> Healthcheck:
        """Get a single healthcheck by ID.

        Args:
            healthcheck_id: Healthcheck UUID.

        Returns:
            :class:`~hyperping.models.Healthcheck` object.

        Raises:
            HyperpingNotFoundError: If the healthcheck is not found.
            HyperpingAuthError: If the API key is invalid.
            HyperpingAPIError: On unexpected API errors.
        """
        validate_id(healthcheck_id, "healthcheck_id")
        response = self._request("GET", f"{Endpoint.HEALTHCHECKS}/{healthcheck_id}")
        return Healthcheck.model_validate(expect_dict(response, "get_healthcheck"))

    def create_healthcheck(self, healthcheck: HealthcheckCreate) -> Healthcheck:
        """Create a new healthcheck.

        Args:
            healthcheck: Healthcheck creation data.

        Returns:
            Created :class:`~hyperping.models.Healthcheck` object.

        Raises:
            HyperpingValidationError: If the payload fails server-side validation.
            HyperpingAPIError: On unexpected API errors.
        """
        payload = healthcheck.model_dump(exclude_none=True)
        response = self._request("POST", Endpoint.HEALTHCHECKS, json=payload)
        return Healthcheck.model_validate(expect_dict(response, "create_healthcheck"))

    def update_healthcheck(
        self,
        healthcheck_id: str,
        update: HealthcheckUpdate,
    ) -> Healthcheck:
        """Update an existing healthcheck.

        Args:
            healthcheck_id: Healthcheck UUID.
            update: Fields to update (all optional).

        Returns:
            Updated :class:`~hyperping.models.Healthcheck` object.

        Raises:
            HyperpingNotFoundError: If the healthcheck is not found.
            HyperpingAPIError: On unexpected API errors.
        """
        validate_id(healthcheck_id, "healthcheck_id")
        payload = update.model_dump(exclude_none=True)
        response = self._request(
            "PUT",
            f"{Endpoint.HEALTHCHECKS}/{healthcheck_id}",
            json=payload,
        )
        return Healthcheck.model_validate(expect_dict(response, "update_healthcheck"))

    def delete_healthcheck(self, healthcheck_id: str) -> None:
        """Delete a healthcheck.

        Args:
            healthcheck_id: Healthcheck UUID.

        Raises:
            HyperpingNotFoundError: If the healthcheck is not found.
            HyperpingAPIError: On unexpected API errors.
        """
        validate_id(healthcheck_id, "healthcheck_id")
        self._request("DELETE", f"{Endpoint.HEALTHCHECKS}/{healthcheck_id}")

    def pause_healthcheck(self, healthcheck_id: str) -> Healthcheck:
        """Pause a healthcheck.

        Args:
            healthcheck_id: Healthcheck UUID.

        Returns:
            Updated :class:`~hyperping.models.Healthcheck` object.

        Raises:
            HyperpingNotFoundError: If the healthcheck is not found.
            HyperpingAPIError: On unexpected API errors.
        """
        validate_id(healthcheck_id, "healthcheck_id")
        response = self._request(
            "POST",
            f"{Endpoint.HEALTHCHECKS}/{healthcheck_id}/pause",
        )
        return Healthcheck.model_validate(expect_dict(response, "pause_healthcheck"))

    def resume_healthcheck(self, healthcheck_id: str) -> Healthcheck:
        """Resume a paused healthcheck.

        Args:
            healthcheck_id: Healthcheck UUID.

        Returns:
            Updated :class:`~hyperping.models.Healthcheck` object.

        Raises:
            HyperpingNotFoundError: If the healthcheck is not found.
            HyperpingAPIError: On unexpected API errors.
        """
        validate_id(healthcheck_id, "healthcheck_id")
        response = self._request(
            "POST",
            f"{Endpoint.HEALTHCHECKS}/{healthcheck_id}/resume",
        )
        return Healthcheck.model_validate(expect_dict(response, "resume_healthcheck"))

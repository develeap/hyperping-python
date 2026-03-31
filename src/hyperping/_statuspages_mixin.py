"""Status page operations mixin for HyperpingClient.

Provides CRUD and subscriber methods for Hyperping status pages (v2 API). Mixed into
:class:`~hyperping.client.HyperpingClient` at class definition time.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from hyperping.endpoints import Endpoint
from hyperping.models import (
    StatusPage,
    StatusPageCreate,
    StatusPageSubscriber,
    StatusPageUpdate,
)

logger = logging.getLogger(__name__)


class StatusPagesMixin:
    """Status page-related API operations."""

    def _request(  # type: ignore[empty-body]
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...  # provided by HyperpingClient

    def list_status_pages(self, search: str | None = None) -> list[StatusPage]:
        """List all status pages.

        Args:
            search: Optional search query to filter by name.

        Returns:
            List of :class:`StatusPage` objects. Pages that fail to parse
            are silently skipped with a warning log.

        Raises:
            HyperpingAuthError: If the API key is invalid.
            HyperpingAPIError: On unexpected API errors.
        """
        query_params: dict[str, Any] = {}
        if search:
            query_params["search"] = search

        response = self._request(
            "GET",
            Endpoint.STATUSPAGES,
            params=query_params if query_params else None,
        )

        if isinstance(response, list):
            pages_data = response
        elif "statuspages" in response:
            pages_data = response["statuspages"]
        else:
            pages_data = response.get("data", [])

        pages = []
        skipped = 0
        for data in pages_data:
            try:
                pages.append(StatusPage.model_validate(data))
            except (ValueError, ValidationError) as e:
                skipped += 1
                logger.warning(f"Failed to parse status page data: {e}", extra={"data": data})

        if skipped:
            logger.warning(
                f"{skipped} of {len(pages_data)} status pages could not be parsed and were skipped"
            )

        return pages

    def get_status_page(self, status_page_id: str) -> StatusPage:
        """Get a single status page by ID.

        Args:
            status_page_id: Status page UUID.

        Returns:
            :class:`StatusPage` object.

        Raises:
            HyperpingNotFoundError: If status page not found.
        """
        response = self._request("GET", f"{Endpoint.STATUSPAGES}/{status_page_id}")
        return StatusPage.model_validate(response)

    def create_status_page(self, status_page: StatusPageCreate) -> StatusPage:
        """Create a new status page.

        Args:
            status_page: Status page creation data.

        Returns:
            Created :class:`StatusPage` object.

        Raises:
            HyperpingValidationError: If the payload fails server-side validation.
            HyperpingAPIError: On unexpected API errors.
        """
        payload = status_page.model_dump(exclude_none=True, by_alias=True)
        response = self._request("POST", Endpoint.STATUSPAGES, json=payload)
        return StatusPage.model_validate(response)

    def update_status_page(
        self,
        status_page_id: str,
        update: StatusPageUpdate,
    ) -> StatusPage:
        """Update an existing status page.

        Args:
            status_page_id: Status page UUID.
            update: Fields to update.

        Returns:
            Updated :class:`StatusPage` object.

        Raises:
            HyperpingNotFoundError: If status page not found.
            HyperpingValidationError: If the payload fails server-side validation.
            HyperpingAPIError: On unexpected API errors.
        """
        payload = update.model_dump(exclude_none=True, by_alias=True)
        response = self._request("PUT", f"{Endpoint.STATUSPAGES}/{status_page_id}", json=payload)
        return StatusPage.model_validate(response)

    def delete_status_page(self, status_page_id: str) -> None:
        """Delete a status page.

        Args:
            status_page_id: Status page UUID.

        Raises:
            HyperpingNotFoundError: If status page not found.
        """
        self._request("DELETE", f"{Endpoint.STATUSPAGES}/{status_page_id}")

    def list_subscribers(self, status_page_id: str) -> list[StatusPageSubscriber]:
        """List subscribers for a status page.

        Args:
            status_page_id: Status page UUID.

        Returns:
            List of :class:`StatusPageSubscriber` objects.

        Raises:
            HyperpingNotFoundError: If status page not found.
            HyperpingAPIError: On unexpected API errors.
        """
        response = self._request(
            "GET", f"{Endpoint.STATUSPAGES}/{status_page_id}/subscribers"
        )

        if isinstance(response, list):
            subscribers_data = response
        elif "subscribers" in response:
            subscribers_data = response["subscribers"]
        else:
            subscribers_data = response.get("data", [])

        subscribers = []
        skipped = 0
        for data in subscribers_data:
            try:
                subscribers.append(StatusPageSubscriber.model_validate(data))
            except (ValueError, ValidationError) as e:
                skipped += 1
                logger.warning(f"Failed to parse subscriber data: {e}", extra={"data": data})

        if skipped:
            logger.warning(
                f"{skipped} of {len(subscribers_data)} subscribers could not be parsed "
                "and were skipped"
            )

        return subscribers

    def add_subscriber(self, status_page_id: str, email: str) -> StatusPageSubscriber:
        """Add a subscriber to a status page.

        Args:
            status_page_id: Status page UUID.
            email: Subscriber email address.

        Returns:
            Created :class:`StatusPageSubscriber` object.

        Raises:
            HyperpingNotFoundError: If status page not found.
            HyperpingValidationError: If the email is invalid.
            HyperpingAPIError: On unexpected API errors.
        """
        payload = {"email": email}
        response = self._request(
            "POST",
            f"{Endpoint.STATUSPAGES}/{status_page_id}/subscribers",
            json=payload,
        )
        return StatusPageSubscriber.model_validate(response)

    def remove_subscriber(self, status_page_id: str, subscriber_id: str) -> None:
        """Remove a subscriber from a status page.

        Args:
            status_page_id: Status page UUID.
            subscriber_id: Subscriber ID.

        Raises:
            HyperpingNotFoundError: If status page or subscriber not found.
        """
        self._request(
            "DELETE",
            f"{Endpoint.STATUSPAGES}/{status_page_id}/subscribers/{subscriber_id}",
        )

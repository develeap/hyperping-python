"""Async status page operations mixin for AsyncHyperpingClient.

Provides CRUD and subscriber methods for Hyperping status pages (v2 API). Mixed into
:class:`~hyperping._async_client.AsyncHyperpingClient` at class definition time.
"""

from __future__ import annotations

import logging
import re

from hyperping._protocols import _AsyncClientProtocol
from hyperping._utils import expect_dict, parse_list, unwrap_list, validate_id
from hyperping.endpoints import Endpoint
from hyperping.models import (
    StatusPage,
    StatusPageCreate,
    StatusPageSubscriber,
    StatusPageUpdate,
)

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AsyncStatusPagesMixin(_AsyncClientProtocol):
    """Async status page-related API operations."""

    async def list_status_pages(self, search: str | None = None) -> list[StatusPage]:
        """List all status pages.

        Args:
            search: Optional search query to filter by name.

        Returns:
            List of :class:`StatusPage` objects.

        Raises:
            HyperpingAuthError: If the API key is invalid.
            HyperpingAPIError: On unexpected API errors.
        """
        query_params: dict[str, str] = {}
        if search:
            query_params["search"] = search

        response = await self._request(
            "GET",
            Endpoint.STATUSPAGES,
            params=query_params or None,
        )
        return parse_list(unwrap_list(response, "statuspages"), StatusPage, "status page")

    async def get_status_page(self, status_page_id: str) -> StatusPage:
        """Get a single status page by ID.

        Args:
            status_page_id: Status page UUID.

        Returns:
            :class:`StatusPage` object.

        Raises:
            HyperpingNotFoundError: If status page not found.
        """
        validate_id(status_page_id, "status_page_id")
        response = await self._request("GET", f"{Endpoint.STATUSPAGES}/{status_page_id}")
        return StatusPage.model_validate(expect_dict(response, "get_status_page"))

    async def create_status_page(self, status_page: StatusPageCreate) -> StatusPage:
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
        response = await self._request("POST", Endpoint.STATUSPAGES, json=payload)
        return StatusPage.model_validate(expect_dict(response, "create_status_page"))

    async def update_status_page(
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
        validate_id(status_page_id, "status_page_id")
        payload = update.model_dump(exclude_none=True, by_alias=True)
        response = expect_dict(
            await self._request(
                "PUT", f"{Endpoint.STATUSPAGES}/{status_page_id}", json=payload
            ),
            "update_status_page",
        )
        return StatusPage.model_validate(response)

    async def delete_status_page(self, status_page_id: str) -> None:
        """Delete a status page.

        Args:
            status_page_id: Status page UUID.

        Raises:
            HyperpingNotFoundError: If status page not found.
        """
        validate_id(status_page_id, "status_page_id")
        await self._request("DELETE", f"{Endpoint.STATUSPAGES}/{status_page_id}")

    async def list_subscribers(
        self, status_page_id: str
    ) -> list[StatusPageSubscriber]:
        """List subscribers for a status page.

        Args:
            status_page_id: Status page UUID.

        Returns:
            List of :class:`StatusPageSubscriber` objects.

        Raises:
            HyperpingNotFoundError: If status page not found.
            HyperpingAPIError: On unexpected API errors.
        """
        validate_id(status_page_id, "status_page_id")
        response = await self._request(
            "GET", f"{Endpoint.STATUSPAGES}/{status_page_id}/subscribers"
        )
        return parse_list(
            unwrap_list(response, "subscribers"), StatusPageSubscriber, "subscriber"
        )

    async def add_subscriber(
        self, status_page_id: str, email: str
    ) -> StatusPageSubscriber:
        """Add a subscriber to a status page.

        Args:
            status_page_id: Status page UUID.
            email: Subscriber email address.

        Returns:
            Created :class:`StatusPageSubscriber` object.

        Raises:
            ValueError: If *email* does not look like a valid email address.
            HyperpingNotFoundError: If status page not found.
            HyperpingValidationError: If the email is rejected by the API.
            HyperpingAPIError: On unexpected API errors.
        """
        validate_id(status_page_id, "status_page_id")
        if not _EMAIL_RE.match(email):
            raise ValueError(f"Invalid email address: {email!r}")
        payload = {"email": email}
        response = expect_dict(
            await self._request(
                "POST",
                f"{Endpoint.STATUSPAGES}/{status_page_id}/subscribers",
                json=payload,
            ),
            "add_subscriber",
        )
        return StatusPageSubscriber.model_validate(response)

    async def remove_subscriber(
        self, status_page_id: str, subscriber_id: str
    ) -> None:
        """Remove a subscriber from a status page.

        Args:
            status_page_id: Status page UUID.
            subscriber_id: Subscriber ID.

        Raises:
            HyperpingNotFoundError: If status page or subscriber not found.
        """
        validate_id(status_page_id, "status_page_id")
        validate_id(subscriber_id, "subscriber_id")
        await self._request(
            "DELETE",
            f"{Endpoint.STATUSPAGES}/{status_page_id}/subscribers/{subscriber_id}",
        )

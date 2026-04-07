"""Internal base classes shared across mixin modules (H4).

Centralises the ``_request`` stub so each mixin can reference a single typed
contract instead of duplicating a 7-line ``# type: ignore[empty-body]`` stub.

Not part of the public API.
"""

from __future__ import annotations

from typing import Any


class _ClientProtocol:
    """Base class providing the ``_request`` method stub for mixin classes.

    All mixin classes inherit from this base so that:
    - There is a single source of truth for the method signature.
    - ``# type: ignore[empty-body]`` comments are eliminated from every mixin.
    - Future signature changes propagate automatically.

    The concrete implementation is provided by
    :class:`~hyperping.client.HyperpingClient`.
    """

    def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Execute an authenticated HTTP request and return the parsed body."""
        raise NotImplementedError("_request must be provided by HyperpingClient")


class _AsyncClientProtocol:
    """Base class providing the async ``_request`` stub for async mixin classes.

    All async mixin classes inherit from this base so that:
    - There is a single source of truth for the async method signature.
    - Future signature changes propagate automatically.

    The concrete implementation is provided by
    :class:`~hyperping._async_client.AsyncHyperpingClient`.
    """

    async def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Execute an async authenticated HTTP request and return the parsed body."""
        raise NotImplementedError("_request must be provided by AsyncHyperpingClient")

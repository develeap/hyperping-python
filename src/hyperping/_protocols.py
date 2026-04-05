"""Internal Protocol definitions shared across mixin modules (H4).

Centralises the ``_request`` stub so each mixin can reference a single typed
contract instead of duplicating a 7-line ``# type: ignore[empty-body]`` stub.

Not part of the public API.
"""

from __future__ import annotations

from typing import Any, Protocol


class _ClientProtocol(Protocol):
    """Structural type for the ``_request`` method provided by HyperpingClient.

    All mixin classes use this protocol instead of an inline stub so that:
    - There is a single source of truth for the method signature.
    - ``# type: ignore[empty-body]`` comments are eliminated from every mixin.
    - Future signature changes propagate automatically.
    """

    def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Execute an authenticated HTTP request and return the parsed body."""
        ...

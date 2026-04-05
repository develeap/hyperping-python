"""Internal utilities shared across mixin modules.

Not part of the public API.
"""

from __future__ import annotations

import logging
import re
from typing import Any, TypeVar

from pydantic import ValidationError

T = TypeVar("T")

# Allowed characters for Hyperping resource IDs (H8)
_RESOURCE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

logger = logging.getLogger(__name__)


def validate_id(value: str, name: str = "id") -> str:
    """Assert that a resource ID contains only safe characters.

    Prevents path-traversal attacks by rejecting IDs that contain ``/``,
    ``..``, or other special characters before they are interpolated into
    URL paths.

    Args:
        value: The resource ID to validate.
        name: Human-readable parameter name for error messages.

    Returns:
        The original value if valid.

    Raises:
        ValueError: If the ID contains unsafe characters.
    """
    if not value or not _RESOURCE_ID_RE.match(value):
        raise ValueError(
            f"Invalid {name} {value!r}: must contain only letters, digits, "
            "hyphens, and underscores"
        )
    return value


def unwrap_list(response: Any, key: str) -> list[Any]:
    """Normalise the three list-response shapes the Hyperping API uses.

    Hyperping endpoints return list data in one of:
    - A bare JSON array: ``[{...}, ...]``
    - A dict with a named key: ``{"monitors": [...]}``
    - A dict with a generic ``"data"`` key: ``{"data": [...]}``

    Args:
        response: Raw value returned by ``_request``.
        key: The dict key to look for when the response is a dict.

    Returns:
        The list of raw item dicts.
    """
    if isinstance(response, list):
        return response  # type: ignore[return-value]
    if isinstance(response, dict):
        if key in response:
            return response[key]  # type: ignore[return-value]
        return response.get("data", [])  # type: ignore[return-value]
    return []


def parse_list(
    raw_items: list[Any],
    model_cls: type[T],
    label: str,
) -> list[T]:
    """Validate a list of raw dicts into typed Pydantic model instances.

    Items that fail validation are silently skipped with a warning log so
    that a single malformed record never breaks a full-list response.

    Args:
        raw_items: List of raw dicts from the API.
        model_cls: Pydantic model class to validate against.
        label: Human-readable resource name for log messages (e.g., "monitor").

    Returns:
        List of successfully validated model instances.
    """
    results: list[T] = []
    skipped = 0
    for item in raw_items:
        try:
            results.append(model_cls.model_validate(item))  # type: ignore[attr-defined]
        except (ValueError, ValidationError) as exc:
            skipped += 1
            logger.warning("Failed to parse %s data: %s", label, exc, extra={"data": item})

    if skipped:
        logger.warning(
            "%d of %d %s records could not be parsed and were skipped",
            skipped,
            len(raw_items),
            label,
        )

    return results

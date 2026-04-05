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


def expect_dict(response: Any, context: str = "API response") -> dict[str, Any]:
    """Assert that a response is a dict, raising a clear SDK error otherwise.

    Used by single-resource endpoints where the Hyperping API is expected to
    return a JSON object (not a list).  Unlike a bare ``assert``, this check
    survives ``python -O`` and produces a meaningful error message.

    Args:
        response: Raw value returned by ``_request``.
        context: Human-readable label for the error message.

    Returns:
        The same dict, now narrowed for the type checker.

    Raises:
        TypeError: If *response* is not a dict.
    """
    if not isinstance(response, dict):
        raise TypeError(
            f"Expected dict from {context}, got {type(response).__name__}"
        )
    return response


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
        return response
    if isinstance(response, dict):
        if key in response:
            return response[key]  # type: ignore[no-any-return]
        return response.get("data", [])  # type: ignore[no-any-return]
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
            # Log only the exception, not the raw item - it may contain
            # sensitive data (subscriber emails, custom auth headers).
            logger.warning("Failed to parse %s data: %s", label, exc)

    if skipped:
        logger.warning(
            "%d of %d %s records could not be parsed and were skipped",
            skipped,
            len(raw_items),
            label,
        )

    return results

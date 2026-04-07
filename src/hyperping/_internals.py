"""Shared internal constants and helpers used by both sync and async clients.

Not part of the public API.
"""

from __future__ import annotations

from typing import Any

from hyperping._version import __version__

# Maximum time to honour a server-requested Retry-After value (5 minutes)
RETRY_AFTER_MAX = 300.0

# Default User-Agent header value
DEFAULT_USER_AGENT = f"hyperping-python/{__version__}"

# Known JSON body keys whose values must not appear in debug logs (M15)
_SENSITIVE_LOG_KEYS = frozenset(
    {"authorization", "x-api-key", "api_key", "request_headers", "request_body"}
)


def sanitize_for_log(data: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return a copy of *data* with sensitive values replaced by ``[REDACTED]``.

    Prevents tokens and header values from leaking into DEBUG-level log output.
    """
    if data is None:
        return None
    return {
        k: "[REDACTED]" if k.lower() in _SENSITIVE_LOG_KEYS else v
        for k, v in data.items()
    }

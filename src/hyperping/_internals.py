"""Shared internal constants and helpers used by both sync and async clients.

Not part of the public API.
"""

from __future__ import annotations

import warnings
from typing import Any
from urllib.parse import urlsplit

from hyperping._version import __version__

# Maximum time to honour a server-requested Retry-After value (5 minutes)
RETRY_AFTER_MAX = 300.0

# Default User-Agent header value
DEFAULT_USER_AGENT = f"hyperping-python/{__version__}"

# Known JSON body keys whose values must not appear in debug logs (M15)
_SENSITIVE_LOG_KEYS = frozenset(
    {"authorization", "x-api-key", "api_key", "request_headers", "request_body"}
)


class InsecureTransportWarning(UserWarning):
    """Warning emitted when the client is configured to use plaintext HTTP.

    Plaintext transport ships the Bearer API key in clear text on every
    request. Allowed only as an explicit opt-in (``allow_insecure=True``)
    for local development and integration testing.
    """


def validate_base_url(
    url: str,
    *,
    allow_insecure: bool = False,
    param_name: str = "base_url",
) -> str:
    """Validate that *url* is a safe, well-formed API base URL.

    Rejects:
    - non-string / empty input
    - URLs that don't parse to ``scheme://host`` form
    - URLs with userinfo (``user:pass@host``); credentials in URLs are a
      common exfiltration vector and are never legitimate for this SDK
    - non-``https`` schemes, unless *allow_insecure* is ``True``

    When *allow_insecure* permits an ``http://`` URL, an
    :class:`InsecureTransportWarning` is emitted so the operator sees the
    downgrade in their logs.

    Returns the URL with any trailing slash stripped. Raises ``ValueError``
    on any rejection.
    """
    if not isinstance(url, str) or not url.strip():
        raise ValueError(f"{param_name} must be a non-empty string")

    try:
        parts = urlsplit(url.strip())
    except ValueError as exc:
        raise ValueError(f"{param_name} is not a parseable URL: {url!r}") from exc

    if parts.scheme not in ("http", "https"):
        raise ValueError(
            f"{param_name} must use the https scheme (got {parts.scheme!r} in {url!r})"
        )

    # ``urlsplit`` accepts strings without ``//`` (e.g. ``not a url``) and
    # produces an empty netloc; reject any URL without a hostname.
    if not parts.hostname:
        raise ValueError(f"{param_name} must include a host (got {url!r})")

    if parts.username or parts.password:
        raise ValueError(
            f"{param_name} must not embed userinfo (credentials) in the URL"
        )

    if parts.scheme == "http":
        if not allow_insecure:
            raise ValueError(
                f"{param_name} uses the insecure http scheme; pass allow_insecure=True "
                f"to opt in to plaintext transport (development only)"
            )
        warnings.warn(
            f"{param_name}={url!r} uses plaintext http; the Bearer API key "
            "will be transmitted in clear text",
            InsecureTransportWarning,
            stacklevel=3,
        )

    return url.rstrip("/")


def sanitize_for_log(data: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return a copy of *data* with sensitive values replaced by ``[REDACTED]``.

    Prevents tokens and header values from leaking into DEBUG-level log output.
    """
    if data is None:
        return None
    return {k: "[REDACTED]" if k.lower() in _SENSITIVE_LOG_KEYS else v for k, v in data.items()}

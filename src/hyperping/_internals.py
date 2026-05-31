"""Shared internal constants and helpers used by both sync and async clients.

Not part of the public API.
"""

from __future__ import annotations

import re
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


# Keys whose values are redacted recursively from any structured payload that
# may end up attached to an exception. Over-redact when uncertain: it is
# always safer to drop a string from a server response than to ship a secret
# into a logging pipeline.
_SENSITIVE_RESPONSE_KEYS = frozenset(
    {
        "authorization",
        "x-api-key",
        "api_key",
        "apikey",
        "token",
        "access_token",
        "refresh_token",
        "secret",
        "password",
        "cookie",
        "set-cookie",
        "session",
        "subscriber_email",
        "subscribers",
        "email",
        "webhook",
        "webhook_url",
        "webhookurl",
        "request_headers",
        "request_body",
        "headers",
    }
)

# Maximum length of an embedded error message in formatted exception output.
_ERROR_MESSAGE_MAX_LEN = 256
# Control-byte stripper: drop C0 controls except TAB and LF. CR is dropped to
# avoid log-injection line splicing.
_CONTROL_BYTES_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

# Token-shaped substrings to scrub from server-supplied string values. Captures
# Bearer-style ("Bearer sk_xxx" / "Bearer eyJ...") and bare sk_-prefixed keys
# (the documented Hyperping API key shape).
_TOKEN_VALUE_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)bearer\s+\S+"),
    re.compile(r"\bsk_[A-Za-z0-9_\-]{4,}"),
)


def _scrub_token_strings(value: str) -> str:
    """Replace Bearer / sk_-prefixed tokens inside a free-form string."""
    for pattern in _TOKEN_VALUE_RES:
        value = pattern.sub("[REDACTED]", value)
    return value


def redact_response_body(value: Any) -> Any:
    """Recursively redact sensitive keys from a parsed JSON response body.

    Mirrors the key list used by :func:`sanitize_for_log` but applied at any
    depth so server payloads that echo request headers or carry subscriber
    PII can be attached to exceptions without leaking secrets through
    ``logging.exception`` / traceback printing.

    Lists and tuples are walked element-wise; primitive values are returned
    unchanged. The structure is copied; the input is not mutated.
    """
    if isinstance(value, dict):
        redacted: dict[Any, Any] = {}
        for k, v in value.items():
            key_str = str(k).lower() if isinstance(k, str) else k
            if isinstance(key_str, str) and key_str in _SENSITIVE_RESPONSE_KEYS:
                redacted[k] = "[REDACTED]"
            else:
                redacted[k] = redact_response_body(v)
        return redacted
    if isinstance(value, list):
        return [redact_response_body(v) for v in value]
    if isinstance(value, tuple):
        return tuple(redact_response_body(v) for v in value)
    if isinstance(value, str):
        return _scrub_token_strings(value)
    return value


def sanitize_error_message(message: str) -> str:
    """Strip control bytes and clamp length on an exception message.

    Server-supplied error strings can carry ANSI escapes (terminal-injection)
    or arbitrarily long payloads; both are unsafe to forward into log lines
    or terminals verbatim. TAB and LF are preserved so multi-line validation
    errors keep their shape.
    """
    if not isinstance(message, str):
        message = str(message)
    cleaned = _CONTROL_BYTES_RE.sub("", message)
    if len(cleaned) > _ERROR_MESSAGE_MAX_LEN:
        cleaned = cleaned[: _ERROR_MESSAGE_MAX_LEN - 3] + "..."
    return cleaned

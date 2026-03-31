"""Hyperping API client exceptions.

All exceptions carry optional ``status_code``, ``response_body``, and
``request_id`` fields for diagnostic context.
"""

from typing import Any


class HyperpingAPIError(Exception):
    """Base exception for Hyperping API errors.

    Args:
        message: Human-readable error description.
        status_code: HTTP status code, if the error originated from an HTTP response.
        response_body: Parsed JSON body of the error response, if available.
        request_id: Server-assigned request identifier (``x-request-id`` header),
            if the server included one.
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_body: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response_body = response_body or {}
        self.request_id = request_id

    def __str__(self) -> str:
        if self.status_code:
            return f"[{self.status_code}] {self.message}"
        return self.message


class HyperpingAuthError(HyperpingAPIError):
    """Raised when authentication fails (HTTP 401 or 403)."""

    pass


class HyperpingNotFoundError(HyperpingAPIError):
    """Raised when a resource is not found (HTTP 404)."""

    pass


class HyperpingRateLimitError(HyperpingAPIError):
    """Raised when the API rate limit is exceeded (HTTP 429).

    Args:
        message: Human-readable error description.
        retry_after: Seconds to wait before retrying, from the ``Retry-After``
            response header. ``None`` if the header was absent.
        **kwargs: Forwarded to :class:`HyperpingAPIError`.
    """

    def __init__(
        self,
        message: str,
        retry_after: int | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class HyperpingValidationError(HyperpingAPIError):
    """Raised when request validation fails (HTTP 400 or 422).

    Args:
        message: Human-readable error description.
        validation_errors: Structured validation error details from the API
            response body (``details`` or ``errors`` key).
        **kwargs: Forwarded to :class:`HyperpingAPIError`.
    """

    def __init__(
        self,
        message: str,
        validation_errors: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.validation_errors = validation_errors or []

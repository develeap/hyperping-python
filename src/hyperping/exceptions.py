"""Hyperping API client exceptions.

All exceptions carry optional ``status_code``, ``response_body``, and
``request_id`` fields for diagnostic context. ``response_body`` is
recursively redacted at assignment time so callers that route exceptions
through ``logging.exception`` cannot accidentally flush server-echoed
secrets (Authorization headers, subscriber emails, webhook URLs) to logs.
"""

from typing import Any

from hyperping._internals import redact_response_body, sanitize_error_message


class HyperpingAPIError(Exception):
    """Base exception for Hyperping API errors.

    Args:
        message: Human-readable error description. Control bytes are stripped
            and the value is length-clamped before being included in ``str()``.
        status_code: HTTP status code, if the error originated from an HTTP response.
        response_body: Parsed JSON body of the error response, if available.
            Sensitive keys (authorization, tokens, emails, webhooks, request
            headers/body) are redacted recursively at assignment time.
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
        safe_message = sanitize_error_message(message)
        super().__init__(safe_message)
        self.message = safe_message
        self.status_code = status_code
        # Redact at assignment time so any caller introspecting the attribute
        # (logging, custom error renderers, traceback frames) sees only the
        # sanitised copy. The redactor produces a fresh structure; the input
        # is left untouched.
        self.response_body = redact_response_body(response_body) if response_body else {}
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
    """Raised when an API rate limit is exceeded.

    The REST API and the MCP server both signal rate-limit using this
    exception. The signal can arrive two ways:

    - HTTP 429 with a standard ``Retry-After`` header (REST and MCP).
    - HTTP 200 with a JSON-RPC ``-32000`` error whose message contains the
      string ``"rate limit exceeded"`` and (optionally) ``"Retry after Ns"``
      (MCP ``initialize``-bucket signal).

    ``status_code`` reflects whichever signal was used (429 or 200). When the
    MCP cool-off latch short-circuits a subsequent ``initialize`` attempt,
    ``status_code`` is the status of the original rate-limit response.

    Args:
        message: Human-readable error description.
        retry_after: Seconds to wait before retrying, parsed from the
            ``Retry-After`` header or the JSON-RPC message body. ``None`` if
            no value was advertised.
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


class HyperpingPartialBatchError(HyperpingAPIError):
    """Raised when a multi-item batch operation fails partway through.

    Used by helpers that split one logical request into several API calls
    (e.g. :meth:`create_maintenance_windows`, :meth:`create_incidents` when the
    status-page list exceeds the per-request cap). If an item fails after
    earlier ones succeeded, the already-created objects are NOT rolled back;
    they are attached here so the caller can record or clean them up.

    Args:
        message: Human-readable error description.
        created: The objects successfully created before the failure.
        completed: How many items succeeded.
        total: How many items were attempted in the batch.
        **kwargs: Forwarded to :class:`HyperpingAPIError`.
    """

    def __init__(
        self,
        message: str,
        created: list[Any] | None = None,
        completed: int | None = None,
        total: int | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.created = created or []
        self.completed = completed if completed is not None else len(self.created)
        self.total = total

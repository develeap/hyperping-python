"""Hyperping API client with retry logic and error handling.

This module provides the main :class:`HyperpingClient` class along with
configuration dataclasses for retry behavior.

Circuit-breaker types (``CircuitBreaker``, ``CircuitBreakerConfig``,
``CircuitState``, ``DEFAULT_CIRCUIT_BREAKER_CONFIG``) are defined in
:mod:`hyperping._circuit_breaker` and re-exported here for backward compat.
"""

import logging
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx
from pydantic import SecretStr

from hyperping._circuit_breaker import (
    DEFAULT_CIRCUIT_BREAKER_CONFIG,
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
)
from hyperping._healthchecks_mixin import HealthchecksMixin
from hyperping._incidents_mixin import IncidentsMixin
from hyperping._internals import (
    DEFAULT_USER_AGENT,
    RETRY_AFTER_MAX,
    sanitize_for_log,
    validate_base_url,
)
from hyperping._maintenance_mixin import MaintenanceMixin
from hyperping._monitors_mixin import MonitorsMixin
from hyperping._outages_mixin import OutagesMixin
from hyperping._statuspages_mixin import StatusPagesMixin
from hyperping.endpoints import API_BASE, Endpoint
from hyperping.exceptions import (
    HyperpingAPIError,
    HyperpingAuthError,
    HyperpingNotFoundError,
    HyperpingRateLimitError,
    HyperpingValidationError,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetryConfig:
    """Configuration for retry behavior."""

    max_retries: int = 3
    initial_delay: float = 1.0
    max_delay: float = 30.0
    backoff_factor: float = 2.0
    retry_on_status: tuple[int, ...] = (429, 500, 502, 503, 504)


DEFAULT_RETRY_CONFIG = RetryConfig()
# intentionally internal — not in __all__; exported from _circuit_breaker counterpart
# DEFAULT_CIRCUIT_BREAKER_CONFIG is exported from _circuit_breaker (M7)


class HyperpingClient(
    MonitorsMixin,
    IncidentsMixin,
    MaintenanceMixin,
    OutagesMixin,
    StatusPagesMixin,
    HealthchecksMixin,
):
    """Client for interacting with Hyperping API.

    Handles authentication, retry logic, and error mapping.

    Example:
        >>> client = HyperpingClient(api_key="sk_xxx")
        >>> monitors = client.list_monitors()
        >>> for m in monitors:
        ...     print(f"{m.name}: {'down' if m.down else 'up'}")
    """

    DEFAULT_BASE_URL = API_BASE  # https://api.hyperping.io
    DEFAULT_TIMEOUT = 30.0

    def __init__(
        self,
        api_key: str | SecretStr,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        retry_config: RetryConfig | None = None,
        circuit_breaker_config: CircuitBreakerConfig | None = None,
        user_agent: str | None = None,
        per_endpoint_circuit_breaker: bool = False,
        breaker_key_fn: Callable[[str], str] | None = None,
        allow_insecure: bool = False,
    ) -> None:
        """Initialize the Hyperping API client.

        Args:
            api_key: Hyperping API key (starts with ``sk_``). Accepts a plain
                string or a :class:`pydantic.SecretStr`.
            base_url: Override the default API base URL
                (``https://api.hyperping.io``).
            timeout: HTTP request timeout in seconds.
            retry_config: Retry behaviour configuration. Pass ``None`` for
                defaults (3 retries, exponential backoff).
            circuit_breaker_config: Circuit breaker configuration. Pass ``None``
                for defaults (5-failure threshold, 60 s recovery). When
                ``per_endpoint_circuit_breaker`` is ``True`` this same config
                is applied to every per-path breaker.
            user_agent: Custom ``User-Agent`` header value. Defaults to
                ``hyperping-python/0.1.0``.
            per_endpoint_circuit_breaker: When ``True``, maintain an independent
                breaker per *endpoint* so a single flaky endpoint does not
                block traffic to healthy ones. By default the breaker key is
                the matching :class:`~hyperping.endpoints.Endpoint` prefix:
                ``/v1/monitors``, ``/v1/monitors/{uuid}`` and
                ``/v1/monitors/{uuid}/anything`` all share one breaker keyed
                on ``/v1/monitors``. This keeps the breaker set bounded
                (one per Endpoint) instead of growing per resource UUID.
                Default ``False`` preserves the original single-shared-breaker
                behaviour.
            breaker_key_fn: Override the default endpoint-prefix bucketing.
                Receives the request path (with query/fragment intact) and
                must return the breaker key. Use this if you want different
                granularity (e.g. one breaker per resource UUID, or a single
                breaker for all monitor sub-paths). Ignored unless
                ``per_endpoint_circuit_breaker`` is ``True``. *Caller is
                responsible for keeping the key set bounded.*
        """
        raw_key = api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
        if not raw_key or not raw_key.strip():
            raise ValueError("api_key must be a non-empty string")
        self._api_key = SecretStr(raw_key) if isinstance(api_key, str) else api_key
        self.base_url = validate_base_url(
            base_url or self.DEFAULT_BASE_URL,
            allow_insecure=allow_insecure,
        )
        self.timeout = timeout
        self.retry_config = retry_config or DEFAULT_RETRY_CONFIG
        self._circuit_breaker_config = circuit_breaker_config
        self._circuit_breaker = CircuitBreaker(circuit_breaker_config)
        self._per_endpoint_circuit_breaker = per_endpoint_circuit_breaker
        self._breaker_key_fn = breaker_key_fn
        self._endpoint_breakers: dict[str, CircuitBreaker] = {}
        self._endpoint_breakers_lock = threading.Lock()

        self._client = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self._api_key.get_secret_value()}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": user_agent or DEFAULT_USER_AGENT,
            },
            timeout=self.timeout,
        )

    def __repr__(self) -> str:
        return f"HyperpingClient(base_url={self.base_url!r})"

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self) -> "HyperpingClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        """Access the (shared) circuit breaker state (for monitoring).

        In per-endpoint mode this returns the original shared breaker, kept
        for backward compatibility; the per-path breakers are exposed via
        :meth:`circuit_breaker_state_for`.
        """
        return self._circuit_breaker

    def _resolve_breaker_key(self, path: str) -> str:
        """Map a request path to its circuit-breaker key.

        Default bucketing strips query/fragment and collapses the path under
        the longest matching :class:`Endpoint` prefix, so every sub-resource
        under an endpoint shares the parent's breaker. When the caller passes
        a custom ``breaker_key_fn`` it wins outright.
        """
        if self._breaker_key_fn is not None:
            return self._breaker_key_fn(path)
        pure = urlsplit(path).path
        for ep in Endpoint:
            ep_value = ep.value
            if pure == ep_value or pure.startswith(ep_value + "/"):
                return ep_value
        return pure

    def _breaker_for(self, path: str) -> CircuitBreaker:
        """Return the breaker that governs ``path``.

        In default mode this is always the shared breaker; in per-endpoint
        mode each canonical key gets its own :class:`CircuitBreaker` lazily.
        """
        if not self._per_endpoint_circuit_breaker:
            return self._circuit_breaker
        key = self._resolve_breaker_key(path)
        # threading.Lock here (not asyncio.Lock) is intentional: it lets the
        # same per-endpoint logic serve both the sync and async clients
        # without forcing an `async` accessor, and it correctly serialises
        # access if the async client is driven from multiple OS threads
        # (e.g. via run_in_executor).
        with self._endpoint_breakers_lock:
            breaker = self._endpoint_breakers.get(key)
            if breaker is None:
                breaker = CircuitBreaker(self._circuit_breaker_config)
                self._endpoint_breakers[key] = breaker
            return breaker

    def circuit_breaker_state_for(self, path: str) -> CircuitState:
        """Return the circuit state of the breaker governing ``path``.

        In per-endpoint mode the path is canonicalised the same way as during
        a request (default endpoint-prefix bucketing, or ``breaker_key_fn``
        if set); untouched buckets report :attr:`CircuitState.CLOSED` without
        allocating a breaker. In the default single-breaker mode the shared
        breaker's state is returned for any path, so this method is always
        safe to call regardless of the flag.
        """
        if not self._per_endpoint_circuit_breaker:
            return self._circuit_breaker.state
        key = self._resolve_breaker_key(path)
        with self._endpoint_breakers_lock:
            breaker = self._endpoint_breakers.get(key)
        return breaker.state if breaker is not None else CircuitState.CLOSED

    def _circuit_open_message(self, breaker: CircuitBreaker, path: str) -> str:
        """Build the error message raised when a request is rejected by an OPEN breaker."""
        if self._per_endpoint_circuit_breaker:
            key = self._resolve_breaker_key(path)
            return (
                f"Circuit breaker OPEN for {key!r} - API calls to this endpoint suspended. "
                f"Consecutive failures: {breaker.failure_count}. "
                f"Will recover after {breaker.recovery_timeout}s."
            )
        return (
            f"Circuit breaker OPEN - API calls suspended. "
            f"Consecutive failures: {breaker.failure_count}. "
            f"Will recover after {breaker.recovery_timeout}s."
        )

    # ==================== Error Handling ====================

    def _parse_error_body(self, response: httpx.Response) -> dict[str, Any]:
        """Parse the JSON body from an error response.

        Falls back to a plain-text envelope when the body is not valid JSON.
        Note: the returned dict may be attached to exception objects and
        forwarded to caller observability stacks. For :class:`HyperpingAuthError`
        specifically, ``response_body`` is omitted to prevent credential leakage
        through tracing/logging pipelines (H10).
        """
        try:
            return response.json()  # type: ignore[no-any-return]
        except (ValueError, httpx.DecodingError):  # H9: narrow bare except
            return {"error": response.text or "Unknown error"}

    def _parse_retry_after(self, response: httpx.Response) -> int | None:
        """Extract and parse the ``Retry-After`` header value.

        Returns:
            Integer seconds, or ``None`` if the header is absent or non-numeric.
        """
        retry_after = response.headers.get("Retry-After")
        if not retry_after:
            return None
        try:
            return int(retry_after)
        except ValueError:
            return None

    def _handle_response_error(self, response: httpx.Response) -> None:
        """Map HTTP errors to typed exceptions.

        Extracts ``x-request-id`` from response headers when present and
        attaches it to the raised exception for diagnostic context.

        Args:
            response: The HTTP response with a 4xx or 5xx status code.

        Raises:
            HyperpingAuthError: On 401 or 403.
            HyperpingNotFoundError: On 404.
            HyperpingRateLimitError: On 429.
            HyperpingValidationError: On 400 or 422.
            HyperpingAPIError: On all other error status codes.
        """
        status = response.status_code
        request_id = response.headers.get("x-request-id")
        body = self._parse_error_body(response)
        error_msg = body.get("error") or body.get("message") or f"HTTP {status}"

        if status in (401, 403):
            # H10: omit response_body for auth errors to prevent credential leakage
            raise HyperpingAuthError(
                message=f"Authentication failed: {error_msg}",
                status_code=status,
                response_body=None,
                request_id=request_id,
            )
        if status == 404:
            raise HyperpingNotFoundError(
                message=f"Resource not found: {error_msg}",
                status_code=status,
                response_body=body,
                request_id=request_id,
            )
        if status == 429:
            raise HyperpingRateLimitError(
                message=f"Rate limit exceeded: {error_msg}",
                status_code=status,
                response_body=body,
                retry_after=self._parse_retry_after(response),
                request_id=request_id,
            )
        if status in (400, 422):
            raise HyperpingValidationError(
                message=f"Validation error: {error_msg}",
                status_code=status,
                response_body=body,
                validation_errors=body.get("details") or body.get("errors"),
                request_id=request_id,
            )
        raise HyperpingAPIError(
            message=f"API error: {error_msg}",
            status_code=status,
            response_body=body,
            request_id=request_id,
        )

    # ==================== Request Helpers ====================

    def _compute_sleep_time(
        self,
        response: httpx.Response,
        delay: float,
    ) -> float:
        """Compute how long to sleep before retrying a failed request (C2).

        For 429 responses the server-provided ``Retry-After`` value is used
        (capped at :data:`RETRY_AFTER_MAX`). For all other retryable statuses,
        exponential backoff with ±25% jitter is applied.

        Args:
            response: The HTTP response that triggered the retry.
            delay: Current base delay from the exponential backoff ladder.

        Returns:
            Seconds to sleep before the next attempt.
        """
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    return min(float(retry_after), RETRY_AFTER_MAX)
                except (ValueError, OverflowError):
                    # RFC 7231 allows HTTP-date strings in Retry-After;
                    # fall through to exponential backoff if unparseable.
                    pass
        return delay + random.uniform(0, delay * 0.25)

    def _should_retry(self, status_code: int, attempt: int) -> bool:
        """Return True if this status/attempt combination warrants a retry (C2).

        Args:
            status_code: HTTP status code of the current response.
            attempt: Zero-based attempt index (0 = first attempt).

        Returns:
            ``True`` when the status is retryable and retries remain.
        """
        return (
            status_code in self.retry_config.retry_on_status
            and attempt < self.retry_config.max_retries
        )

    def _execute_single_attempt(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]] | httpx.Response:
        """Execute a single HTTP request attempt.

        Returns the parsed response on success, or the raw Response object when
        the status code indicates a retryable or non-retryable error (caller
        decides whether to retry).

        Raises:
            httpx.TimeoutException: On request timeout.
            httpx.RequestError: On connection/transport errors.
        """
        logger.debug(
            "API request: %s %s (attempt)",
            method,
            path,
            extra={
                "json": sanitize_for_log(json),  # M15: redact sensitive fields
                "params": sanitize_for_log(params),
            },
        )

        response = self._client.request(method=method, url=path, json=json, params=params)

        if response.status_code >= 400:
            return response

        # Success
        self._breaker_for(path).record_success()
        if response.status_code == 204:
            return {}
        return response.json()  # type: ignore[no-any-return]

    def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]]:  # H1: accurate return type
        """Make an HTTP request with retry logic.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            path: API path (e.g., Endpoint.MONITORS)
            json: Request body as dict
            params: Query parameters

        Returns:
            Response body as dict or list (list endpoints return arrays)

        Raises:
            HyperpingAPIError: On API errors after retries exhausted
        """
        breaker = self._breaker_for(path)
        if not breaker.call_allowed():
            raise HyperpingAPIError(self._circuit_open_message(breaker, path))

        last_exception: Exception | None = None
        delay = self.retry_config.initial_delay
        max_attempts = self.retry_config.max_retries + 1

        for attempt in range(max_attempts):
            try:
                result = self._execute_single_attempt(method, path, json, params)

                if not isinstance(result, httpx.Response):
                    return result

                response = result
                if self._should_retry(response.status_code, attempt):
                    sleep_time = self._compute_sleep_time(response, delay)
                    logger.warning(
                        "Retrying after %.2fs due to %d (attempt %d/%d)",
                        sleep_time,
                        response.status_code,
                        attempt + 1,
                        max_attempts,
                    )
                    time.sleep(sleep_time)
                    delay = min(
                        delay * self.retry_config.backoff_factor,
                        self.retry_config.max_delay,
                    )
                    continue

                # Only trip circuit breaker on server errors, not client errors
                if response.status_code >= 500:
                    breaker.record_failure()
                self._handle_response_error(response)

            except (httpx.TimeoutException, httpx.RequestError) as e:
                last_exception = e
                if attempt < self.retry_config.max_retries:
                    label = "timeout" if isinstance(e, httpx.TimeoutException) else str(e)
                    sleep_time = delay + random.uniform(0, delay * 0.25)
                    logger.warning(
                        "Request %s, retrying after %.2fs (attempt %d/%d)",
                        label,
                        sleep_time,
                        attempt + 1,
                        max_attempts,
                    )
                    time.sleep(sleep_time)
                    delay = min(
                        delay * self.retry_config.backoff_factor,
                        self.retry_config.max_delay,
                    )
                    continue
                breaker.record_failure()
                if isinstance(e, httpx.TimeoutException):
                    raise HyperpingAPIError(f"Request timeout after {max_attempts} attempts") from e
                raise HyperpingAPIError(f"Request failed: {e}") from e

        # Should not reach here, but just in case
        raise HyperpingAPIError(  # pragma: no cover
            "Request failed after all retries"
        ) from last_exception

    # ==================== Health Check ====================

    def ping(self) -> bool:
        """Test API connectivity and authentication.

        Makes a lightweight call to the monitors list endpoint to verify
        that the API key is valid and the Hyperping API is reachable.

        Note: This fetches the full monitor list and discards the result.
        If a dedicated ``/health`` endpoint becomes available in the Hyperping
        API it should be preferred here to reduce unnecessary data transfer (M8).

        Returns:
            True if connection successful

        Raises:
            HyperpingAuthError: If authentication fails
            HyperpingAPIError: If connection fails
        """
        try:
            self.list_monitors()
            return True
        except HyperpingAuthError:
            raise
        except (HyperpingAPIError, httpx.RequestError, httpx.TimeoutException) as e:
            raise HyperpingAPIError(f"API connectivity test failed: {e}") from e


# Re-export circuit-breaker types for backward compatibility (M16)
__all__ = [
    "RetryConfig",
    "DEFAULT_RETRY_CONFIG",
    "CircuitState",
    "CircuitBreakerConfig",
    "DEFAULT_CIRCUIT_BREAKER_CONFIG",
    "CircuitBreaker",
    "HyperpingClient",
]

"""Hyperping API client with retry logic and error handling.

This module provides the main :class:`HyperpingClient` class along with
configuration dataclasses for retry and circuit-breaker behavior.
"""

import logging
import random
import threading
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import httpx
from pydantic import SecretStr

from hyperping._incidents_mixin import IncidentsMixin
from hyperping._maintenance_mixin import MaintenanceMixin
from hyperping._monitors_mixin import MonitorsMixin
from hyperping._outages_mixin import OutagesMixin
from hyperping._statuspages_mixin import StatusPagesMixin
from hyperping._version import __version__
from hyperping.endpoints import (
    API_BASE,
)
from hyperping.exceptions import (
    HyperpingAPIError,
    HyperpingAuthError,
    HyperpingNotFoundError,
    HyperpingRateLimitError,
    HyperpingValidationError,
)

logger = logging.getLogger(__name__)

_DEFAULT_USER_AGENT = f"hyperping-python/{__version__}"


@dataclass(frozen=True)
class RetryConfig:
    """Configuration for retry behavior."""

    max_retries: int = 3
    initial_delay: float = 1.0
    max_delay: float = 30.0
    backoff_factor: float = 2.0
    retry_on_status: tuple[int, ...] = (429, 500, 502, 503, 504)


DEFAULT_RETRY_CONFIG = RetryConfig()

# Maximum time to honor a server-requested Retry-After value (5 minutes)
_RETRY_AFTER_MAX = 300.0


class CircuitState(StrEnum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal: requests flow through
    OPEN = "open"  # Failing: requests fail fast
    HALF_OPEN = "half_open"  # Testing: one request allowed through


@dataclass(frozen=True)
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""

    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    half_open_max_calls: int = 1


DEFAULT_CIRCUIT_BREAKER_CONFIG = CircuitBreakerConfig()


class CircuitBreaker:
    """Circuit breaker pattern for API calls.

    States:
        CLOSED → normal operation
        OPEN → fail fast, no API calls made
        HALF_OPEN → allow one trial call; success → CLOSED, failure → OPEN
    """

    def __init__(self, config: CircuitBreakerConfig | None = None) -> None:
        """Initialize the circuit breaker.

        Args:
            config: Circuit breaker configuration. Uses defaults if ``None``.
        """
        self._config = config or DEFAULT_CIRCUIT_BREAKER_CONFIG
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._half_open_calls: int = 0
        self._last_failure_time: float | None = None
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        """Return the current circuit state."""
        return self._state

    @property
    def failure_count(self) -> int:
        """Return the current consecutive failure count."""
        return self._failure_count

    def call_allowed(self) -> bool:
        """Check whether a new call is permitted under current state.

        Returns:
            ``True`` if a request may proceed, ``False`` if the circuit is open.
        """
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return True
            if self._state == CircuitState.OPEN:
                if self._last_failure_time is not None:
                    elapsed = time.time() - self._last_failure_time
                    if elapsed >= self._config.recovery_timeout:
                        self._state = CircuitState.HALF_OPEN
                        logger.info("Circuit breaker: OPEN → HALF_OPEN (trial call allowed)")
                        return True
                return False
            # HALF_OPEN: allow only up to half_open_max_calls trial requests
            if self._half_open_calls < self._config.half_open_max_calls:
                self._half_open_calls += 1
                return True
            return False

    def record_success(self) -> None:
        """Record a successful call — reset to CLOSED."""
        with self._lock:
            self._half_open_calls = 0
            if self._state != CircuitState.CLOSED:
                logger.info(
                    f"Circuit breaker: {self._state} → CLOSED (recovered after "
                    f"{self._failure_count} failures)"
                )
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_failure_time = None

    def record_failure(self) -> None:
        """Record a failed call — may open the circuit."""
        with self._lock:
            self._half_open_calls = 0
            self._failure_count += 1
            self._last_failure_time = time.time()
            if self._failure_count >= self._config.failure_threshold:
                if self._state != CircuitState.OPEN:
                    logger.warning(
                        f"Circuit breaker: {self._state} → OPEN "
                        f"(threshold {self._config.failure_threshold} reached)"
                    )
                self._state = CircuitState.OPEN


class HyperpingClient(
    MonitorsMixin, IncidentsMixin, MaintenanceMixin, OutagesMixin, StatusPagesMixin
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
    ) -> None:
        """Initialize the Hyperping API client.

        Args:
            api_key: Hyperping API key (starts with ``sk_``). Accepts a plain
                string or a :class:`pydantic.SecretStr`.
            base_url: Override the default API base URL
                (``https://api.hyperping.io``).
            timeout: HTTP request timeout in seconds.
            retry_config: Retry behavior configuration. Pass ``None`` for defaults
                (3 retries, exponential backoff).
            circuit_breaker_config: Circuit breaker configuration. Pass ``None``
                for defaults (5-failure threshold, 60 s recovery).
            user_agent: Custom ``User-Agent`` header value. Defaults to
                ``hyperping-python/0.1.0``.
        """
        self._api_key = SecretStr(api_key) if isinstance(api_key, str) else api_key
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.retry_config = retry_config or DEFAULT_RETRY_CONFIG
        self._circuit_breaker = CircuitBreaker(circuit_breaker_config)

        self._client = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self._api_key.get_secret_value()}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": user_agent or _DEFAULT_USER_AGENT,
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
        """Access the circuit breaker state (for monitoring)."""
        return self._circuit_breaker

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

        try:
            body = response.json()
        except Exception:
            body = {"error": response.text or "Unknown error"}

        error_msg = body.get("error") or body.get("message") or f"HTTP {status}"

        if status == 401 or status == 403:
            raise HyperpingAuthError(
                message=f"Authentication failed: {error_msg}",
                status_code=status,
                response_body=body,
                request_id=request_id,
            )
        elif status == 404:
            raise HyperpingNotFoundError(
                message=f"Resource not found: {error_msg}",
                status_code=status,
                response_body=body,
                request_id=request_id,
            )
        elif status == 429:
            retry_after = response.headers.get("Retry-After")
            retry_after_seconds: int | None = None
            if retry_after:
                try:
                    retry_after_seconds = int(retry_after)
                except ValueError:
                    retry_after_seconds = None
            raise HyperpingRateLimitError(
                message=f"Rate limit exceeded: {error_msg}",
                status_code=status,
                response_body=body,
                retry_after=retry_after_seconds,
                request_id=request_id,
            )
        elif status == 400 or status == 422:
            raise HyperpingValidationError(
                message=f"Validation error: {error_msg}",
                status_code=status,
                response_body=body,
                validation_errors=body.get("details") or body.get("errors"),
                request_id=request_id,
            )
        else:
            raise HyperpingAPIError(
                message=f"API error: {error_msg}",
                status_code=status,
                response_body=body,
                request_id=request_id,
            )

    def _execute_single_attempt(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | httpx.Response:
        """Execute a single HTTP request attempt.

        Returns the parsed response dict on success, or the raw Response
        object when the status code indicates a retryable/non-retryable error
        (caller decides whether to retry).

        Raises:
            httpx.TimeoutException: On request timeout
            httpx.RequestError: On connection/transport errors
        """
        logger.debug(
            f"API request: {method} {path} (attempt)",
            extra={"json": json, "params": params},
        )

        response = self._client.request(method=method, url=path, json=json, params=params)

        if response.status_code >= 400:
            return response

        # Success
        self._circuit_breaker.record_success()
        if response.status_code == 204:
            return {}
        return response.json()  # type: ignore[no-any-return]  # list endpoints return arrays; callers use isinstance checks

    def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP request with retry logic.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            path: API path (e.g., Endpoint.MONITORS)
            json: Request body as dict
            params: Query parameters

        Returns:
            Response body as dict

        Raises:
            HyperpingAPIError: On API errors after retries exhausted
        """
        if not self._circuit_breaker.call_allowed():
            raise HyperpingAPIError(
                f"Circuit breaker OPEN — API calls suspended. "
                f"Consecutive failures: {self._circuit_breaker.failure_count}. "
                f"Will retry after {self.retry_config.initial_delay}s."
            )

        last_exception: Exception | None = None
        delay = self.retry_config.initial_delay
        max_attempts = self.retry_config.max_retries + 1

        for attempt in range(max_attempts):
            try:
                result = self._execute_single_attempt(method, path, json, params)

                if not isinstance(result, httpx.Response):
                    return result

                response = result
                if (
                    response.status_code in self.retry_config.retry_on_status
                    and attempt < self.retry_config.max_retries
                ):
                    if response.status_code == 429:
                        retry_after = response.headers.get("Retry-After")
                        if retry_after:
                            delay = min(float(retry_after), _RETRY_AFTER_MAX)
                    sleep_time = delay
                    if response.status_code != 429:
                        sleep_time = delay + random.uniform(0, delay * 0.25)
                    logger.warning(
                        f"Retrying after {sleep_time:.2f}s due to {response.status_code} "
                        f"(attempt {attempt + 1}/{max_attempts})"
                    )
                    time.sleep(sleep_time)
                    delay = min(
                        delay * self.retry_config.backoff_factor,
                        self.retry_config.max_delay,
                    )
                    continue

                # Only trip circuit breaker on server errors, not client errors
                if response.status_code >= 500:
                    self._circuit_breaker.record_failure()
                self._handle_response_error(response)

            except (httpx.TimeoutException, httpx.RequestError) as e:
                last_exception = e
                if attempt < self.retry_config.max_retries:
                    label = "timeout" if isinstance(e, httpx.TimeoutException) else str(e)
                    sleep_time = delay + random.uniform(0, delay * 0.25)
                    logger.warning(
                        f"Request {label}, retrying after {sleep_time:.2f}s "
                        f"(attempt {attempt + 1}/{max_attempts})"
                    )
                    time.sleep(sleep_time)
                    delay = min(
                        delay * self.retry_config.backoff_factor,
                        self.retry_config.max_delay,
                    )
                    continue
                self._circuit_breaker.record_failure()
                if isinstance(e, httpx.TimeoutException):
                    raise HyperpingAPIError(
                        f"Request timeout after {max_attempts} attempts"
                    ) from e
                raise HyperpingAPIError(f"Request failed: {e}") from e

        # Should not reach here, but just in case
        raise HyperpingAPIError(  # pragma: no cover
            "Request failed after all retries"
        ) from last_exception

    # ==================== Health Check ====================

    def ping(self) -> bool:
        """Test API connectivity and authentication.

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

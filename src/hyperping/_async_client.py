"""Async Hyperping API client with retry logic and error handling.

This module provides the :class:`AsyncHyperpingClient` class, a fully async
counterpart to :class:`~hyperping.client.HyperpingClient`.

Example::

    async with AsyncHyperpingClient(api_key="sk_...") as client:
        monitors = await client.list_monitors()
        for m in monitors:
            print(f"{m.name}: {'down' if m.down else 'up'}")
"""

import asyncio
import logging
import random
import threading
from collections import OrderedDict
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

import httpx2 as httpx
from pydantic import SecretStr

from hyperping._async_healthchecks_mixin import AsyncHealthchecksMixin
from hyperping._async_incidents_mixin import AsyncIncidentsMixin
from hyperping._async_maintenance_mixin import AsyncMaintenanceMixin
from hyperping._async_monitors_mixin import AsyncMonitorsMixin
from hyperping._async_outages_mixin import AsyncOutagesMixin
from hyperping._async_statuspages_mixin import AsyncStatusPagesMixin
from hyperping._async_streaming_mixin import AsyncStreamingMixin
from hyperping._circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
)
from hyperping._internals import (
    DEFAULT_USER_AGENT,
    RETRY_AFTER_MAX,
    sanitize_for_log,
    validate_base_url,
)
from hyperping._otel import get_tracer, record_error, start_request_span
from hyperping.client import _ENDPOINT_BREAKERS_MAX, DEFAULT_RETRY_CONFIG, RetryConfig
from hyperping.endpoints import API_BASE, Endpoint
from hyperping.exceptions import (
    HyperpingAPIError,
    HyperpingAuthError,
    HyperpingRateLimitError,
)

logger = logging.getLogger(__name__)


class AsyncHyperpingClient(
    AsyncMonitorsMixin,
    AsyncIncidentsMixin,
    AsyncMaintenanceMixin,
    AsyncOutagesMixin,
    AsyncStatusPagesMixin,
    AsyncHealthchecksMixin,
    AsyncStreamingMixin,
):
    """Async client for interacting with the Hyperping API.

    Handles authentication, retry logic, and error mapping using
    ``httpx.AsyncClient`` for non-blocking I/O.

    Example::

        async with AsyncHyperpingClient(api_key="sk_xxx") as client:
            monitors = await client.list_monitors()
            for m in monitors:
                print(f"{m.name}: {'down' if m.down else 'up'}")
    """

    DEFAULT_BASE_URL = API_BASE
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
        """Initialize the async Hyperping API client.

        Args:
            api_key: Hyperping API key (starts with ``sk_``). Accepts a plain
                string or a :class:`pydantic.SecretStr`.
            base_url: Override the default API base URL.
            timeout: HTTP request timeout in seconds.
            retry_config: Retry behaviour configuration.
            circuit_breaker_config: Circuit breaker configuration. When
                ``per_endpoint_circuit_breaker`` is ``True`` the same config is
                applied to each per-endpoint breaker.
            user_agent: Custom ``User-Agent`` header value.
            per_endpoint_circuit_breaker: When ``True``, maintain an
                independent breaker per :class:`~hyperping.endpoints.Endpoint`
                prefix (sub-resources inherit the parent endpoint's breaker,
                so the breaker set stays bounded). Default ``False``
                preserves the original single-shared-breaker behaviour.
            breaker_key_fn: Override the default endpoint-prefix bucketing.
                Receives the request path and must return the breaker key.
                Ignored unless ``per_endpoint_circuit_breaker`` is ``True``.
                Caller is responsible for keeping the key set bounded.
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
        self._endpoint_breakers: OrderedDict[str, CircuitBreaker] = OrderedDict()
        self._endpoint_breakers_lock = threading.Lock()

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self._api_key.get_secret_value()}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": user_agent or DEFAULT_USER_AGENT,
            },
            timeout=self.timeout,
        )
        self._tracer = get_tracer()

    def __repr__(self) -> str:
        return f"AsyncHyperpingClient(base_url={self.base_url!r})"

    async def close(self) -> None:
        """Close the async HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "AsyncHyperpingClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

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
        the longest matching :class:`Endpoint` prefix; a custom
        ``breaker_key_fn`` wins outright.
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
        """Return the breaker that governs ``path`` (shared, or per-endpoint).

        The critical section under ``_endpoint_breakers_lock`` is purely
        CPU-bound (a single ``OrderedDict.get`` / ``__setitem__`` /
        ``move_to_end`` / ``popitem``) and never awaits, so wrapping it in a
        ``threading.Lock`` does not block the event loop in practice; the
        loop only "stalls" for the duration of one dict operation, which is
        well below the resolution of any asyncio scheduling decision.

        We keep ``threading.Lock`` (rather than ``asyncio.Lock``) so the same
        breaker map remains safe if a caller drives the async client from
        multiple OS threads (e.g. via ``loop.run_in_executor`` or a thread
        pool that re-enters the SDK). Switching to ``asyncio.Lock`` would
        make the per-endpoint path correct only on the loop that owns the
        lock; ``threading.Lock`` is correct in both cases. Regression
        coverage:
        ``tests/unit/test_security_breaker_cap.py
        ::test_async_breaker_lock_does_not_deadlock_under_gather``.
        """
        if not self._per_endpoint_circuit_breaker:
            return self._circuit_breaker
        key = self._resolve_breaker_key(path)
        with self._endpoint_breakers_lock:
            breaker = self._endpoint_breakers.get(key)
            if breaker is None:
                breaker = CircuitBreaker(self._circuit_breaker_config)
                self._endpoint_breakers[key] = breaker
                # Evict LRU once the cap is hit to bound memory under a
                # pathological breaker_key_fn (see HyperpingClient).
                while len(self._endpoint_breakers) > _ENDPOINT_BREAKERS_MAX:
                    self._endpoint_breakers.popitem(last=False)
            else:
                self._endpoint_breakers.move_to_end(key)
            return breaker

    def circuit_breaker_state_for(self, path: str) -> CircuitState:
        """Return the circuit state of the breaker governing ``path``.

        In per-endpoint mode the path is canonicalised the same way as during
        a request; untouched buckets report :attr:`CircuitState.CLOSED`
        without allocating a breaker. In default mode the shared breaker's
        state is returned for any path.
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
        """Parse the JSON body from an error response."""
        try:
            return response.json()  # type: ignore[no-any-return]
        except (ValueError, httpx.DecodingError):
            return {"error": response.text or "Unknown error"}

    def _parse_retry_after(self, response: httpx.Response) -> int | None:
        """Extract and parse the ``Retry-After`` header value.

        Only the delta-seconds form (RFC 7231 7.1.3) is parsed; HTTP-date
        is intentionally not supported (see
        :meth:`HyperpingClient._parse_retry_after` for rationale).
        """
        retry_after = response.headers.get("Retry-After")
        if not retry_after:
            return None
        try:
            return int(retry_after)
        except ValueError:
            return None

    def _handle_response_error(self, response: httpx.Response) -> None:
        """Map HTTP errors to typed exceptions."""
        from hyperping.exceptions import (
            HyperpingNotFoundError,
            HyperpingValidationError,
        )

        status = response.status_code
        request_id = response.headers.get("x-request-id")
        body = self._parse_error_body(response)
        error_msg = body.get("error") or body.get("message") or f"HTTP {status}"

        if status in (401, 403):
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
            from hyperping.exceptions import HyperpingValidationError

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

    def _compute_sleep_time(self, response: httpx.Response, delay: float) -> float:
        """Compute how long to sleep before retrying a failed request."""
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    return min(float(retry_after), RETRY_AFTER_MAX)
                except (ValueError, OverflowError):
                    pass
        return delay + random.uniform(0, delay * 0.25)

    def _should_retry(self, status_code: int, attempt: int) -> bool:
        """Return True if this status/attempt combination warrants a retry."""
        return (
            status_code in self.retry_config.retry_on_status
            and attempt < self.retry_config.max_retries
        )

    async def _execute_single_attempt(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]] | httpx.Response:
        """Execute a single async HTTP request attempt."""
        logger.debug(
            "API request: %s %s (attempt)",
            method,
            path,
            extra={
                "json": sanitize_for_log(json),
                "params": sanitize_for_log(params),
            },
        )

        response = await self._client.request(method=method, url=path, json=json, params=params)

        if response.status_code >= 400:
            return response

        self._breaker_for(path).record_success()
        if response.status_code == 204:
            return {}
        return response.json()  # type: ignore[no-any-return]

    async def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Make an async HTTP request with retry logic.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            path: API path (e.g., Endpoint.MONITORS)
            json: Request body as dict
            params: Query parameters

        Returns:
            Response body as dict or list

        Raises:
            HyperpingAPIError: On API errors after retries exhausted
        """
        with start_request_span(self._tracer, method, path, self.base_url) as span:
            breaker = self._breaker_for(path)
            if not breaker.call_allowed():
                raise HyperpingAPIError(self._circuit_open_message(breaker, path))

            last_exception: Exception | None = None
            delay = self.retry_config.initial_delay
            max_attempts = self.retry_config.max_retries + 1

            for attempt in range(max_attempts):
                try:
                    result = await self._execute_single_attempt(method, path, json, params)

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
                        await asyncio.sleep(sleep_time)
                        delay = min(
                            delay * self.retry_config.backoff_factor,
                            self.retry_config.max_delay,
                        )
                        continue

                    if response.status_code >= 500:
                        breaker.record_failure()
                    try:
                        self._handle_response_error(response)
                    except HyperpingAPIError as exc:
                        record_error(span, exc)
                        raise

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
                        await asyncio.sleep(sleep_time)
                        delay = min(
                            delay * self.retry_config.backoff_factor,
                            self.retry_config.max_delay,
                        )
                        continue
                    breaker.record_failure()
                    if isinstance(e, httpx.TimeoutException):
                        api_exc = HyperpingAPIError(
                            f"Request timeout after {max_attempts} attempts"
                        )
                        record_error(span, api_exc)
                        raise api_exc from e
                    api_exc = HyperpingAPIError(f"Request failed: {e}")
                    record_error(span, api_exc)
                    raise api_exc from e

            raise HyperpingAPIError(  # pragma: no cover
                "Request failed after all retries"
            ) from last_exception

    # ==================== Health Check ====================

    async def ping(self) -> bool:
        """Test API connectivity and authentication.

        Returns:
            True if connection successful

        Raises:
            HyperpingAuthError: If authentication fails
            HyperpingAPIError: If connection fails
        """
        try:
            await self.list_monitors()
            return True
        except HyperpingAuthError:
            raise
        except (HyperpingAPIError, httpx.RequestError, httpx.TimeoutException) as e:
            raise HyperpingAPIError(f"API connectivity test failed: {e}") from e

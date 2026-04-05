"""Circuit breaker implementation for the Hyperping API client (M16).

Extracted from ``client.py`` to keep file sizes within the 800-line limit and
separate the circuit-breaker concern from the HTTP request logic.

Not part of the public API; re-exported from ``hyperping.client`` for
backward compatibility.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from enum import StrEnum

logger = logging.getLogger(__name__)


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
# intentionally not exported in __all__ — same as DEFAULT_RETRY_CONFIG


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
    def state(self) -> CircuitState:
        """Return the current circuit state (M13: typed return)."""
        with self._lock:  # M14: reads must hold the lock
            return self._state

    @property
    def failure_count(self) -> int:
        """Return the current consecutive failure count."""
        with self._lock:  # M14: reads must hold the lock
            return self._failure_count

    @property
    def recovery_timeout(self) -> float:
        """Seconds before the circuit attempts recovery from OPEN state."""
        return self._config.recovery_timeout

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
                        logger.info("Circuit breaker: OPEN -> HALF_OPEN (trial call allowed)")
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
                    "Circuit breaker: %s -> CLOSED (recovered after %d failures)",
                    self._state,
                    self._failure_count,
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
                        "Circuit breaker: %s -> OPEN (threshold %d reached)",
                        self._state,
                        self._config.failure_threshold,
                    )
                self._state = CircuitState.OPEN

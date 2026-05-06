"""Tests for the per-endpoint circuit breaker option (PY-03).

The default behaviour (single shared breaker) is exercised by the existing
breaker tests in ``test_sdk_surface.py``, ``test_monitors.py``, and
``test_async_client.py``. These tests cover the new opt-in path:

    HyperpingClient(..., per_endpoint_circuit_breaker=True)

with isolation between paths, a per-path state accessor, async parity, and
thread safety on the per-path breaker dict.
"""

from __future__ import annotations

import threading

import httpx
import pytest
import pytest_asyncio
import respx

from hyperping._async_client import AsyncHyperpingClient
from hyperping._circuit_breaker import CircuitBreakerConfig, CircuitState
from hyperping.client import HyperpingClient, RetryConfig
from hyperping.endpoints import API_BASE, Endpoint
from hyperping.exceptions import HyperpingAPIError


def _cb_config(threshold: int = 2) -> CircuitBreakerConfig:
    """Tight threshold so tests trip the breaker quickly without long timeouts."""
    return CircuitBreakerConfig(failure_threshold=threshold, recovery_timeout=60.0)


# ==================== sync ====================


class TestPerEndpointCircuitBreakerSync:
    """Per-endpoint isolation on HyperpingClient."""

    @respx.mock
    def test_per_endpoint_isolation(self) -> None:
        """A failing endpoint trips its own breaker; a healthy endpoint is unaffected."""
        client = HyperpingClient(
            api_key="sk_test",
            retry_config=RetryConfig(max_retries=0),
            circuit_breaker_config=_cb_config(threshold=2),
            per_endpoint_circuit_breaker=True,
        )

        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(
            return_value=httpx.Response(500, json={"error": "boom"}),
        )
        respx.get(f"{API_BASE}{Endpoint.INCIDENTS}").mock(
            return_value=httpx.Response(200, json={"incidents": []}),
        )

        # Trip /v1/monitors
        for _ in range(2):
            with pytest.raises(HyperpingAPIError):
                client.list_monitors()

        # /v1/monitors breaker is now OPEN; further calls fail-fast.
        with pytest.raises(HyperpingAPIError, match="Circuit breaker OPEN"):
            client.list_monitors()

        # /v3/incidents breaker is untouched and the call succeeds.
        assert client.list_incidents() == []

        assert client.circuit_breaker_state_for(str(Endpoint.MONITORS)) == CircuitState.OPEN
        assert client.circuit_breaker_state_for(str(Endpoint.INCIDENTS)) == CircuitState.CLOSED

        client.close()

    @respx.mock
    def test_per_endpoint_state_query_strips_query_string(self) -> None:
        """``circuit_breaker_state_for`` keys on path only, ignoring query/fragment."""
        client = HyperpingClient(
            api_key="sk_test",
            retry_config=RetryConfig(max_retries=0),
            circuit_breaker_config=_cb_config(threshold=1),
            per_endpoint_circuit_breaker=True,
        )

        respx.get(f"{API_BASE}{Endpoint.INCIDENTS}").mock(
            return_value=httpx.Response(500, json={"error": "boom"}),
        )

        with pytest.raises(HyperpingAPIError):
            client.list_incidents(status="investigating")

        # The request used a path with a query string, but the breaker key strips it.
        assert client.circuit_breaker_state_for(str(Endpoint.INCIDENTS)) == CircuitState.OPEN
        assert (
            client.circuit_breaker_state_for(f"{Endpoint.INCIDENTS}?status=investigating")
            == CircuitState.OPEN
        )

        client.close()

    @respx.mock
    def test_default_behaviour_unchanged(self) -> None:
        """With the flag off (default), a 5xx on one path trips the shared breaker for all paths."""
        client = HyperpingClient(
            api_key="sk_test",
            retry_config=RetryConfig(max_retries=0),
            circuit_breaker_config=_cb_config(threshold=1),
        )

        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(
            return_value=httpx.Response(500, json={"error": "boom"}),
        )

        with pytest.raises(HyperpingAPIError):
            client.list_monitors()

        # Shared breaker is OPEN; even an unrelated path (which has no mock route)
        # is rejected without an HTTP call.
        with pytest.raises(HyperpingAPIError, match="Circuit breaker OPEN"):
            client.list_incidents()

        assert client.circuit_breaker.state == CircuitState.OPEN
        client.close()

    def test_state_for_unknown_path_is_closed(self) -> None:
        """Querying a path that has not been touched returns CLOSED (no breaker created)."""
        client = HyperpingClient(
            api_key="sk_test",
            per_endpoint_circuit_breaker=True,
        )
        assert client.circuit_breaker_state_for("/v1/unused") == CircuitState.CLOSED
        client.close()

    def test_state_for_requires_per_endpoint_mode(self) -> None:
        """Calling the per-path accessor without the flag is a misuse — surface it."""
        client = HyperpingClient(api_key="sk_test")
        with pytest.raises(RuntimeError, match="per_endpoint_circuit_breaker"):
            client.circuit_breaker_state_for("/v1/monitors")
        client.close()

    @respx.mock
    def test_per_endpoint_threadsafe(self) -> None:
        """50 concurrent calls across two paths: failing path opens, healthy path stays closed."""
        client = HyperpingClient(
            api_key="sk_test",
            retry_config=RetryConfig(max_retries=0),
            circuit_breaker_config=_cb_config(threshold=3),
            per_endpoint_circuit_breaker=True,
        )

        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(
            return_value=httpx.Response(500, json={"error": "boom"}),
        )
        respx.get(f"{API_BASE}{Endpoint.INCIDENTS}").mock(
            return_value=httpx.Response(200, json={"incidents": []}),
        )

        def hit_monitors() -> None:
            try:
                client.list_monitors()
            except HyperpingAPIError:
                pass

        def hit_incidents() -> None:
            client.list_incidents()

        threads: list[threading.Thread] = []
        for i in range(50):
            target = hit_monitors if i % 2 == 0 else hit_incidents
            threads.append(threading.Thread(target=target))
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert client.circuit_breaker_state_for(str(Endpoint.MONITORS)) == CircuitState.OPEN
        assert client.circuit_breaker_state_for(str(Endpoint.INCIDENTS)) == CircuitState.CLOSED

        client.close()


# ==================== async ====================


@pytest_asyncio.fixture
async def per_endpoint_async_client():
    client = AsyncHyperpingClient(
        api_key="sk_test",
        retry_config=RetryConfig(max_retries=0),
        circuit_breaker_config=_cb_config(threshold=2),
        per_endpoint_circuit_breaker=True,
    )
    yield client
    await client.close()


class TestPerEndpointCircuitBreakerAsync:
    """Per-endpoint isolation on AsyncHyperpingClient."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_per_endpoint_async(
        self, per_endpoint_async_client: AsyncHyperpingClient
    ) -> None:
        client = per_endpoint_async_client

        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(
            return_value=httpx.Response(500, json={"error": "boom"}),
        )
        respx.get(f"{API_BASE}{Endpoint.INCIDENTS}").mock(
            return_value=httpx.Response(200, json={"incidents": []}),
        )

        for _ in range(2):
            with pytest.raises(HyperpingAPIError):
                await client.list_monitors()

        with pytest.raises(HyperpingAPIError, match="Circuit breaker OPEN"):
            await client.list_monitors()

        assert await client.list_incidents() == []

        assert client.circuit_breaker_state_for(str(Endpoint.MONITORS)) == CircuitState.OPEN
        assert client.circuit_breaker_state_for(str(Endpoint.INCIDENTS)) == CircuitState.CLOSED

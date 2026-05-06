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


def _monitor_payload(uuid: str) -> dict:
    """Minimal monitor payload that satisfies Monitor.model_validate()."""
    return {
        "monitorUuid": uuid,
        "name": uuid,
        "url": "https://example.com",
        "method": "GET",
        "frequency": 60,
        "timeout": 10,
        "regions": ["london"],
        "headers": {},
        "expectedStatus": 200,
        "down": False,
        "paused": False,
    }


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

    @respx.mock
    def test_state_for_default_mode_returns_shared_state(self) -> None:
        """In default mode, state_for(any_path) reflects the single shared breaker."""
        client = HyperpingClient(
            api_key="sk_test",
            retry_config=RetryConfig(max_retries=0),
            circuit_breaker_config=_cb_config(threshold=1),
        )
        # Untripped: any path reports CLOSED, identical to the shared breaker.
        assert client.circuit_breaker_state_for("/v1/monitors") == CircuitState.CLOSED
        assert client.circuit_breaker_state_for("/anything") == CircuitState.CLOSED

        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(
            return_value=httpx.Response(500, json={"error": "boom"}),
        )
        with pytest.raises(HyperpingAPIError):
            client.list_monitors()

        # Shared breaker is now OPEN; state_for reports OPEN regardless of path.
        assert client.circuit_breaker.state == CircuitState.OPEN
        assert client.circuit_breaker_state_for("/v1/monitors") == CircuitState.OPEN
        assert client.circuit_breaker_state_for("/v3/incidents") == CircuitState.OPEN
        client.close()

    @respx.mock
    def test_default_canonicalization_buckets_by_endpoint(self) -> None:
        """`/v1/monitors/{uuid}` and `/v1/monitors` share one breaker; other endpoints don't."""
        client = HyperpingClient(
            api_key="sk_test",
            retry_config=RetryConfig(max_retries=0),
            circuit_breaker_config=_cb_config(threshold=2),
            per_endpoint_circuit_breaker=True,
        )

        # Two different monitor UUIDs both fail with 5xx.
        respx.get(f"{API_BASE}{Endpoint.MONITORS}/mon_A").mock(
            return_value=httpx.Response(500, json={"error": "boom"}),
        )
        respx.get(f"{API_BASE}{Endpoint.MONITORS}/mon_B").mock(
            return_value=httpx.Response(500, json={"error": "boom"}),
        )
        respx.get(f"{API_BASE}{Endpoint.INCIDENTS}").mock(
            return_value=httpx.Response(200, json={"incidents": []}),
        )

        # Two failures on mon_A trip the shared `/v1/monitors` breaker.
        with pytest.raises(HyperpingAPIError):
            client.get_monitor("mon_A")
        with pytest.raises(HyperpingAPIError):
            client.get_monitor("mon_A")

        # mon_B is now blocked too — it shares the `/v1/monitors` bucket. No HTTP
        # request is made (no mock interaction needed beyond the route).
        with pytest.raises(HyperpingAPIError, match="Circuit breaker OPEN"):
            client.get_monitor("mon_B")

        # The list endpoint also falls under `/v1/monitors` and is blocked.
        with pytest.raises(HyperpingAPIError, match="Circuit breaker OPEN"):
            client.list_monitors()

        # A different endpoint (`/v3/incidents`) is unaffected.
        assert client.list_incidents() == []

        # State queries: any monitor sub-path resolves to the same key.
        assert client.circuit_breaker_state_for(f"{Endpoint.MONITORS}/mon_A") == CircuitState.OPEN
        assert client.circuit_breaker_state_for(f"{Endpoint.MONITORS}/mon_B") == CircuitState.OPEN
        assert client.circuit_breaker_state_for(str(Endpoint.MONITORS)) == CircuitState.OPEN
        assert client.circuit_breaker_state_for(str(Endpoint.INCIDENTS)) == CircuitState.CLOSED

        client.close()

    @respx.mock
    def test_custom_breaker_key_fn(self) -> None:
        """A caller-supplied key fn overrides the default endpoint bucketing."""
        seen: list[str] = []

        def per_uuid(path: str) -> str:
            seen.append(path)
            # Force one breaker per literal path (the pre-canonicalisation behaviour).
            return path

        client = HyperpingClient(
            api_key="sk_test",
            retry_config=RetryConfig(max_retries=0),
            circuit_breaker_config=_cb_config(threshold=2),
            per_endpoint_circuit_breaker=True,
            breaker_key_fn=per_uuid,
        )

        respx.get(f"{API_BASE}{Endpoint.MONITORS}/mon_A").mock(
            return_value=httpx.Response(500, json={"error": "boom"}),
        )
        respx.get(f"{API_BASE}{Endpoint.MONITORS}/mon_B").mock(
            return_value=httpx.Response(200, json=_monitor_payload("mon_B")),
        )

        with pytest.raises(HyperpingAPIError):
            client.get_monitor("mon_A")
        with pytest.raises(HyperpingAPIError):
            client.get_monitor("mon_A")

        # With a per-UUID key fn, mon_B has its own breaker and the call goes through.
        result = client.get_monitor("mon_B")
        assert result.uuid == "mon_B"

        assert seen, "custom key fn was not invoked"
        assert client.circuit_breaker_state_for(f"{Endpoint.MONITORS}/mon_A") == CircuitState.OPEN
        assert client.circuit_breaker_state_for(f"{Endpoint.MONITORS}/mon_B") == CircuitState.CLOSED

        client.close()

    @respx.mock
    def test_open_error_message_includes_endpoint_key(self) -> None:
        """OPEN error message identifies which endpoint was tripped."""
        client = HyperpingClient(
            api_key="sk_test",
            retry_config=RetryConfig(max_retries=0),
            circuit_breaker_config=_cb_config(threshold=1),
            per_endpoint_circuit_breaker=True,
        )
        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(
            return_value=httpx.Response(500, json={"error": "boom"}),
        )

        with pytest.raises(HyperpingAPIError):
            client.list_monitors()

        with pytest.raises(HyperpingAPIError, match=r"Circuit breaker OPEN for '/v1/monitors'"):
            client.list_monitors()

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

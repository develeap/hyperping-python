"""Security tests for bounded ``_endpoint_breakers`` growth.

Audit finding: a custom ``breaker_key_fn`` returning unbounded unique strings
(buggy callers, UUIDs, query strings) lets ``_endpoint_breakers`` grow without
bound and leaks memory in long-running processes.

The fix caps the dict at a constant (1024 entries) using LRU eviction. These
tests assert the cap holds for both the sync and async per-endpoint paths.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
import respx

from hyperping._async_client import AsyncHyperpingClient
from hyperping.client import HyperpingClient, RetryConfig
from hyperping.endpoints import API_BASE

_ENDPOINT_BREAKERS_CAP = 1024


def _monitor_payload(monitor_uuid: str) -> dict:
    return {
        "monitorUuid": monitor_uuid,
        "name": monitor_uuid,
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


@respx.mock
def test_sync_endpoint_breakers_capped_under_unbounded_key_fn() -> None:
    """A breaker_key_fn that returns fresh keys must not grow the dict beyond the cap."""
    client = HyperpingClient(
        api_key="sk_test",
        base_url=API_BASE,
        retry_config=RetryConfig(max_retries=0),
        per_endpoint_circuit_breaker=True,
        breaker_key_fn=lambda _path: str(uuid.uuid4()),
    )

    respx.get(f"{API_BASE}/v1/monitors").mock(
        return_value=httpx.Response(200, json=[_monitor_payload("mon_1")])
    )

    for _ in range(5000):
        client.list_monitors()

    assert len(client._endpoint_breakers) <= _ENDPOINT_BREAKERS_CAP
    client.close()


@pytest.mark.asyncio
async def test_async_endpoint_breakers_capped_under_unbounded_key_fn() -> None:
    """Async path: same cap enforcement."""
    with respx.mock(base_url=API_BASE, assert_all_called=False) as mock:
        mock.get("/v1/monitors").mock(
            return_value=httpx.Response(200, json=[_monitor_payload("mon_1")])
        )
        client = AsyncHyperpingClient(
            api_key="sk_test",
            base_url=API_BASE,
            retry_config=RetryConfig(max_retries=0),
            per_endpoint_circuit_breaker=True,
            breaker_key_fn=lambda _path: str(uuid.uuid4()),
        )
        for _ in range(5000):
            await client.list_monitors()

        assert len(client._endpoint_breakers) <= _ENDPOINT_BREAKERS_CAP
        await client.close()

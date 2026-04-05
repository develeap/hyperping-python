"""Unit test configuration and shared fixtures."""

from collections.abc import Generator

import pytest

from hyperping.client import HyperpingClient, RetryConfig
from hyperping.endpoints import API_BASE


@pytest.fixture
def client() -> Generator[HyperpingClient, None, None]:
    """Client with retries disabled for deterministic tests (M24: yield-based)."""
    c = HyperpingClient(
        api_key="sk_test_key",
        base_url=API_BASE,
        retry_config=RetryConfig(max_retries=0),
    )
    yield c
    c.close()

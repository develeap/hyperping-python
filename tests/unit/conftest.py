"""Unit test configuration and shared fixtures."""

import pytest

from hyperping.client import HyperpingClient, RetryConfig
from hyperping.endpoints import API_BASE


@pytest.fixture
def client() -> HyperpingClient:
    """Client with retries disabled for deterministic tests."""
    return HyperpingClient(
        api_key="sk_test_key",
        base_url=API_BASE,
        retry_config=RetryConfig(max_retries=0),
    )

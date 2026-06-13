"""Unit test configuration and shared fixtures."""

from collections.abc import Generator

import pytest
from respx.mocks import HTTPCoreMocker

from hyperping.client import HyperpingClient, RetryConfig
from hyperping.endpoints import API_BASE

# httpx2 uses httpcore2 instead of httpcore; extend respx's default mocker so
# that @respx.mock intercepts requests made through httpx2 clients.
HTTPCoreMocker.add_targets(
    "httpcore2._sync.connection.HTTPConnection",
    "httpcore2._sync.connection_pool.ConnectionPool",
    "httpcore2._sync.http_proxy.HTTPProxy",
    "httpcore2._async.connection.AsyncHTTPConnection",
    "httpcore2._async.connection_pool.AsyncConnectionPool",
    "httpcore2._async.http_proxy.AsyncHTTPProxy",
)


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

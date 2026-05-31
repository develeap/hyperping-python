"""Security tests for ``base_url`` (and ``mcp_url``) validation.

Regression coverage for the audit finding "base_url scheme/host not validated"
which allowed bearer-token exfiltration when configuration was attacker-
controlled. Constructors must reject HTTP, userinfo, and unparseable URLs by
default; ``http://`` must be opt-in via ``allow_insecure=True`` and emit a
warning.
"""

from __future__ import annotations

import warnings

import pytest

from hyperping._async_client import AsyncHyperpingClient
from hyperping._async_mcp_transport import AsyncMcpTransport
from hyperping._mcp_transport import McpTransport
from hyperping.client import HyperpingClient
from hyperping.mcp_client import HyperpingMcpClient

# ---------------------------------------------------------------------------
# Parametrisation: every constructor that accepts a URL-bearing kwarg, paired
# with the kwarg name. Each entry takes (api_key, **kwargs).
# ---------------------------------------------------------------------------


def _build_sync(url: str, **extra: object) -> HyperpingClient:
    return HyperpingClient(api_key="sk_test", base_url=url, **extra)  # type: ignore[arg-type]


def _build_async(url: str, **extra: object) -> AsyncHyperpingClient:
    return AsyncHyperpingClient(api_key="sk_test", base_url=url, **extra)  # type: ignore[arg-type]


def _build_mcp_transport(url: str, **extra: object) -> McpTransport:
    return McpTransport(api_key="sk_test", base_url=url, **extra)  # type: ignore[arg-type]


def _build_async_mcp_transport(url: str, **extra: object) -> AsyncMcpTransport:
    return AsyncMcpTransport(api_key="sk_test", base_url=url, **extra)  # type: ignore[arg-type]


def _build_mcp_client(url: str, **extra: object) -> HyperpingMcpClient:
    return HyperpingMcpClient(api_key="sk_test", base_url=url, **extra)  # type: ignore[arg-type]


_CONSTRUCTORS = [
    pytest.param(_build_sync, id="HyperpingClient"),
    pytest.param(_build_async, id="AsyncHyperpingClient"),
    pytest.param(_build_mcp_transport, id="McpTransport"),
    pytest.param(_build_async_mcp_transport, id="AsyncMcpTransport"),
    pytest.param(_build_mcp_client, id="HyperpingMcpClient"),
]


@pytest.mark.parametrize("ctor", _CONSTRUCTORS)
def test_http_scheme_rejected_by_default(ctor):
    """``http://`` URLs must be rejected unless ``allow_insecure=True``."""
    with pytest.raises(ValueError, match="(?i)https|insecure|scheme"):
        ctor("http://evil.example")


@pytest.mark.parametrize("ctor", _CONSTRUCTORS)
def test_http_allowed_with_explicit_opt_in_emits_warning(ctor):
    """``allow_insecure=True`` lets HTTP through but emits a security warning."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        client = ctor("http://localhost:8080", allow_insecure=True)
    assert any("insecure" in str(w.message).lower() or "http" in str(w.message).lower()
               for w in caught), "expected a security warning when allow_insecure=True"
    # Clean up where applicable.
    closer = getattr(client, "close", None)
    if closer is not None and not callable(getattr(closer, "__await__", None)):
        try:
            closer()
        except TypeError:
            pass


@pytest.mark.parametrize("ctor", _CONSTRUCTORS)
def test_userinfo_in_url_rejected(ctor):
    """URLs carrying ``user:pass@host`` must be rejected outright."""
    with pytest.raises(ValueError, match="(?i)userinfo|credentials|user"):
        ctor("https://user:pass@api.hyperping.io")


@pytest.mark.parametrize("ctor", _CONSTRUCTORS)
def test_unparseable_url_rejected(ctor):
    """A non-URL string must be rejected by the constructor."""
    with pytest.raises(ValueError):
        ctor("not a url")


@pytest.mark.parametrize("ctor", _CONSTRUCTORS)
def test_missing_host_rejected(ctor):
    """A URL with a scheme but no host must be rejected."""
    with pytest.raises(ValueError):
        ctor("https://")


@pytest.mark.parametrize("ctor", _CONSTRUCTORS)
def test_https_url_accepted(ctor):
    """A well-formed https URL must be accepted without warning."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        client = ctor("https://api.hyperping.io")
    assert not [w for w in caught if "insecure" in str(w.message).lower()]
    closer = getattr(client, "close", None)
    if closer is not None and not callable(getattr(closer, "__await__", None)):
        try:
            closer()
        except TypeError:
            pass

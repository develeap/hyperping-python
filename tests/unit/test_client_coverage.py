"""Additional coverage tests for HyperpingClient (client.py)."""

from unittest.mock import patch

import httpcore2
import httpx
import pytest
import respx

from hyperping.client import HyperpingClient, RetryConfig
from hyperping.endpoints import API_BASE, Endpoint
from hyperping.exceptions import (
    HyperpingAPIError,
    HyperpingAuthError,
)


class TestClientRepr:
    """Tests for __repr__ method."""

    def test_repr_contains_class_name(self) -> None:
        """__repr__ returns a string containing HyperpingClient."""
        c = HyperpingClient(api_key="sk_test")
        r = repr(c)
        assert "HyperpingClient" in r
        assert API_BASE in r
        c.close()


class TestValidateConnection:
    """Tests for ping / validate_connection behavior."""

    @respx.mock
    def test_ping_success(self) -> None:
        """ping() returns True when list_monitors succeeds."""
        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(return_value=httpx.Response(200, json=[]))
        c = HyperpingClient(api_key="sk_test")
        assert c.ping() is True
        c.close()

    @respx.mock
    def test_ping_auth_failure_reraises(self) -> None:
        """ping() re-raises HyperpingAuthError directly."""
        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(
            return_value=httpx.Response(401, json={"error": "Unauthorized"})
        )
        c = HyperpingClient(
            api_key="sk_test",
            retry_config=RetryConfig(max_retries=0),
        )
        with pytest.raises(HyperpingAuthError):
            c.ping()
        c.close()

    @respx.mock
    def test_ping_api_error_wraps(self) -> None:
        """ping() wraps HyperpingAPIError with connectivity message."""
        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(
            return_value=httpx.Response(500, json={"error": "Server error"})
        )
        c = HyperpingClient(
            api_key="sk_test",
            retry_config=RetryConfig(max_retries=0),
        )
        with pytest.raises(HyperpingAPIError, match="connectivity test failed"):
            c.ping()
        c.close()

    @respx.mock
    def test_ping_timeout_wraps(self) -> None:
        """ping() wraps httpx.TimeoutException."""
        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(
            side_effect=httpcore2.ConnectTimeout("timed out")
        )
        c = HyperpingClient(
            api_key="sk_test",
            retry_config=RetryConfig(max_retries=0),
        )
        with pytest.raises(HyperpingAPIError, match="connectivity test failed"):
            c.ping()
        c.close()

    @respx.mock
    def test_ping_request_error_wraps(self) -> None:
        """ping() wraps httpx.RequestError."""
        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(
            side_effect=httpcore2.ConnectError("connection refused")
        )
        c = HyperpingClient(
            api_key="sk_test",
            retry_config=RetryConfig(max_retries=0),
        )
        with pytest.raises(HyperpingAPIError, match="connectivity test failed"):
            c.ping()
        c.close()


class TestCircuitBreakerDisabled:
    """Tests for circuit breaker disabled path."""

    def test_empty_api_key_raises(self) -> None:
        """Empty api_key raises ValueError (line 109)."""
        with pytest.raises(ValueError, match="non-empty"):
            HyperpingClient(api_key="")

    def test_whitespace_api_key_raises(self) -> None:
        """Whitespace-only api_key raises ValueError (line 109)."""
        with pytest.raises(ValueError, match="non-empty"):
            HyperpingClient(api_key="   ")


class TestRetryAfterParsing:
    """Tests for _parse_retry_after with non-integer values."""

    def test_parse_retry_after_non_integer(self) -> None:
        """Non-integer Retry-After returns None (lines 158-159/172-173)."""
        c = HyperpingClient(api_key="sk_test")
        response = httpx.Response(
            429,
            headers={"Retry-After": "Thu, 01 Dec 2025 16:00:00 GMT"},
        )
        result = c._parse_retry_after(response)
        assert result is None
        c.close()

    def test_parse_retry_after_integer(self) -> None:
        """Integer Retry-After is parsed correctly."""
        c = HyperpingClient(api_key="sk_test")
        response = httpx.Response(429, headers={"Retry-After": "60"})
        result = c._parse_retry_after(response)
        assert result == 60
        c.close()

    def test_parse_retry_after_absent(self) -> None:
        """Missing Retry-After returns None."""
        c = HyperpingClient(api_key="sk_test")
        response = httpx.Response(429)
        result = c._parse_retry_after(response)
        assert result is None
        c.close()


class TestNonJsonErrorBody:
    """Tests for _parse_error_body with non-JSON responses."""

    def test_parse_error_body_non_json(self) -> None:
        """Non-JSON body returns plain-text envelope (lines 172-173)."""
        c = HyperpingClient(api_key="sk_test")
        response = httpx.Response(
            500,
            text="Internal Server Error",
            headers={"content-type": "text/plain"},
        )
        result = c._parse_error_body(response)
        assert result == {"error": "Internal Server Error"}
        c.close()

    def test_parse_error_body_json(self) -> None:
        """JSON body is returned as-is."""
        c = HyperpingClient(api_key="sk_test")
        response = httpx.Response(
            400,
            json={"error": "Bad request", "details": []},
        )
        result = c._parse_error_body(response)
        assert result["error"] == "Bad request"
        c.close()


class TestRetrySleepBackoff:
    """Tests for _compute_sleep_time with backoff (lines 259-262)."""

    def test_compute_sleep_time_429_with_retry_after(self) -> None:
        """429 with valid Retry-After uses server value."""
        c = HyperpingClient(api_key="sk_test")
        response = httpx.Response(429, headers={"Retry-After": "45"})
        sleep_time = c._compute_sleep_time(response, delay=1.0)
        assert sleep_time == 45.0
        c.close()

    def test_compute_sleep_time_429_non_numeric_retry_after(self) -> None:
        """429 with non-numeric Retry-After falls back to backoff."""
        c = HyperpingClient(api_key="sk_test")
        response = httpx.Response(
            429,
            headers={"Retry-After": "Thu, 01 Dec 2025 16:00:00 GMT"},
        )
        sleep_time = c._compute_sleep_time(response, delay=2.0)
        # Should fall through to backoff: delay + jitter in [0, delay*0.25]
        assert 2.0 <= sleep_time <= 2.5
        c.close()

    def test_compute_sleep_time_429_capped_at_max(self) -> None:
        """429 Retry-After is capped at RETRY_AFTER_MAX (300)."""
        c = HyperpingClient(api_key="sk_test")
        response = httpx.Response(429, headers={"Retry-After": "600"})
        sleep_time = c._compute_sleep_time(response, delay=1.0)
        assert sleep_time == 300.0
        c.close()

    def test_compute_sleep_time_500_uses_backoff(self) -> None:
        """Non-429 retryable errors use exponential backoff with jitter."""
        c = HyperpingClient(api_key="sk_test")
        response = httpx.Response(500, text="Server Error")
        sleep_time = c._compute_sleep_time(response, delay=4.0)
        assert 4.0 <= sleep_time <= 5.0
        c.close()


class TestRetryWithSleep:
    """Tests for actual retry loop with sleep (lines 259-262)."""

    @respx.mock
    def test_retry_sleeps_with_backoff(self) -> None:
        """Verify retry loop sleeps with increasing delay."""
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return httpx.Response(500, json={"error": "Server error"})
            return httpx.Response(200, json=[])

        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(side_effect=handler)

        with patch("hyperping.client.time.sleep") as mock_sleep:
            c = HyperpingClient(
                api_key="sk_test",
                retry_config=RetryConfig(
                    max_retries=3,
                    initial_delay=1.0,
                    backoff_factor=2.0,
                ),
            )
            c.list_monitors()

        assert mock_sleep.call_count == 2
        first_sleep = mock_sleep.call_args_list[0][0][0]
        second_sleep = mock_sleep.call_args_list[1][0][0]
        # First delay ~1.0-1.25, second ~2.0-2.5
        assert 1.0 <= first_sleep <= 1.25
        assert 2.0 <= second_sleep <= 2.5
        c.close()


class TestTimeoutRetry:
    """Tests for timeout/request error retry paths (lines 381-401)."""

    @respx.mock
    def test_timeout_retries_then_raises(self) -> None:
        """Timeout after all retries raises HyperpingAPIError."""
        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(
            side_effect=httpcore2.ConnectTimeout("timed out")
        )
        with patch("hyperping.client.time.sleep"):
            c = HyperpingClient(
                api_key="sk_test",
                retry_config=RetryConfig(max_retries=2, initial_delay=0.01),
            )
            with pytest.raises(HyperpingAPIError, match="Request timeout"):
                c.list_monitors()
        c.close()

    @respx.mock
    def test_request_error_retries_then_raises(self) -> None:
        """Connection error after all retries raises HyperpingAPIError."""
        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(
            side_effect=httpcore2.ConnectError("connection refused")
        )
        with patch("hyperping.client.time.sleep"):
            c = HyperpingClient(
                api_key="sk_test",
                retry_config=RetryConfig(max_retries=1, initial_delay=0.01),
            )
            with pytest.raises(HyperpingAPIError, match="Request failed"):
                c.list_monitors()
        c.close()

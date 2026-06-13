"""Tests for Hyperping API client monitor operations."""

from unittest.mock import patch

import httpx
import pytest
import respx
from pydantic import SecretStr

from hyperping.client import HyperpingClient, RetryConfig
from hyperping.endpoints import API_BASE, Endpoint
from hyperping.exceptions import (
    HyperpingAPIError,
    HyperpingAuthError,
    HyperpingNotFoundError,
    HyperpingRateLimitError,
    HyperpingValidationError,
)
from hyperping.models import MonitorCreate, MonitorUpdate


class TestHyperpingClientMonitors:
    """Tests for HyperpingClient monitor methods."""

    @respx.mock
    def test_list_monitors_success(self, client: HyperpingClient) -> None:
        """Test successful list monitors (M17: Endpoint enum)."""
        mock_response = [
            {
                "monitorUuid": "mon_123",
                "name": "Test Monitor",
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
        ]
        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        monitors = client.list_monitors()

        assert len(monitors) == 1
        assert monitors[0].uuid == "mon_123"
        assert monitors[0].name == "Test Monitor"

    @respx.mock
    def test_list_monitors_empty(self, client: HyperpingClient) -> None:
        """Test list monitors with empty result."""
        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(return_value=httpx.Response(200, json=[]))

        monitors = client.list_monitors()
        assert monitors == []

    @respx.mock
    def test_get_monitor_success(self, client: HyperpingClient) -> None:
        """Test get single monitor."""
        mock_response = {
            "monitorUuid": "mon_456",
            "name": "Single Monitor",
            "url": "https://api.example.com",
            "method": "GET",
            "frequency": 30,
            "timeout": 10,
            "regions": ["london", "frankfurt"],
            "headers": {},
            "expectedStatus": 200,
            "down": False,
            "paused": True,
        }
        respx.get(f"{API_BASE}{Endpoint.MONITORS}/mon_456").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        monitor = client.get_monitor("mon_456")

        assert monitor.uuid == "mon_456"
        assert monitor.paused is True

    @respx.mock
    def test_get_monitor_not_found(self, client: HyperpingClient) -> None:
        """Test get monitor that doesn't exist."""
        respx.get(f"{API_BASE}{Endpoint.MONITORS}/mon_notfound").mock(
            return_value=httpx.Response(404, json={"error": "Monitor not found"})
        )

        with pytest.raises(HyperpingNotFoundError):
            client.get_monitor("mon_notfound")

    @respx.mock
    def test_create_monitor_success(self, client: HyperpingClient) -> None:
        """Test create monitor."""
        mock_response = {
            "monitorUuid": "mon_new123",
            "name": "New Monitor",
            "url": "https://new.example.com",
            "method": "GET",
            "frequency": 60,
            "timeout": 10,
            "regions": ["london"],
            "headers": {},
            "expectedStatus": 200,
            "down": False,
            "paused": False,
        }
        respx.post(f"{API_BASE}{Endpoint.MONITORS}").mock(
            return_value=httpx.Response(201, json=mock_response)
        )

        monitor_create = MonitorCreate(
            name="New Monitor",
            url="https://new.example.com",
        )
        created = client.create_monitor(monitor_create)

        assert created.uuid == "mon_new123"
        assert created.name == "New Monitor"

    @respx.mock
    def test_create_monitor_validation_error(self, client: HyperpingClient) -> None:
        """Test create monitor with validation error."""
        respx.post(f"{API_BASE}{Endpoint.MONITORS}").mock(
            return_value=httpx.Response(
                400,
                json={
                    "error": "Invalid URL",
                    "details": [{"field": "url", "message": "Invalid URL format"}],
                },
            )
        )

        with pytest.raises(HyperpingValidationError) as exc_info:
            client.create_monitor(MonitorCreate(name="Bad", url="not-a-url"))

        assert exc_info.value.status_code == 400

    @respx.mock
    def test_delete_monitor_success(self, client: HyperpingClient) -> None:
        """Test delete monitor."""
        respx.delete(f"{API_BASE}{Endpoint.MONITORS}/mon_del").mock(
            return_value=httpx.Response(204)
        )

        # Should not raise
        client.delete_monitor("mon_del")

    @respx.mock
    def test_auth_error(self, client: HyperpingClient) -> None:
        """Test authentication error."""
        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(
            return_value=httpx.Response(401, json={"error": "Invalid API key"})
        )

        with pytest.raises(HyperpingAuthError) as exc_info:
            client.list_monitors()

        assert exc_info.value.status_code == 401

    @respx.mock
    def test_rate_limit_error(self, client: HyperpingClient) -> None:
        """Test rate limit error."""
        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(
            return_value=httpx.Response(
                429,
                json={"error": "Rate limit exceeded"},
                headers={"Retry-After": "60"},
            )
        )

        with pytest.raises(HyperpingRateLimitError) as exc_info:
            client.list_monitors()

        assert exc_info.value.retry_after == 60

    @respx.mock
    def test_ping_success(self, client: HyperpingClient) -> None:
        """Test ping connectivity check."""
        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(return_value=httpx.Response(200, json=[]))

        assert client.ping() is True

    @respx.mock
    def test_ping_auth_failure(self, client: HyperpingClient) -> None:
        """Test ping with auth failure."""
        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(
            return_value=httpx.Response(401, json={"error": "Unauthorized"})
        )

        with pytest.raises(HyperpingAuthError):
            client.ping()

    # ==================== M22: update_monitor / pause / resume ====================

    @respx.mock
    def test_update_monitor_changes_name(self, client: HyperpingClient) -> None:
        """Test that update_monitor sends read-modify-write and returns updated monitor (M22)."""
        current = {
            "monitorUuid": "mon_upd",
            "name": "Old Name",
            "url": "https://example.com",
            "method": "GET",
            "frequency": 60,
            "regions": ["london"],
            "headers": {},
            "expectedStatus": 200,
            "down": False,
            "paused": False,
        }
        updated = {**current, "name": "New Name"}
        respx.get(f"{API_BASE}{Endpoint.MONITORS}/mon_upd").mock(
            return_value=httpx.Response(200, json=current)
        )
        respx.put(f"{API_BASE}{Endpoint.MONITORS}/mon_upd").mock(
            return_value=httpx.Response(200, json=updated)
        )

        result = client.update_monitor("mon_upd", MonitorUpdate(name="New Name"))
        assert result.name == "New Name"

    @respx.mock
    def test_pause_monitor(self, client: HyperpingClient) -> None:
        """Test that pause_monitor sets paused=True on the monitor (M22)."""
        current = {
            "monitorUuid": "mon_pause",
            "name": "Active Monitor",
            "url": "https://example.com",
            "method": "GET",
            "frequency": 60,
            "regions": ["london"],
            "headers": {},
            "expectedStatus": 200,
            "down": False,
            "paused": False,
        }
        paused_response = {**current, "paused": True}
        respx.get(f"{API_BASE}{Endpoint.MONITORS}/mon_pause").mock(
            return_value=httpx.Response(200, json=current)
        )
        respx.put(f"{API_BASE}{Endpoint.MONITORS}/mon_pause").mock(
            return_value=httpx.Response(200, json=paused_response)
        )

        result = client.pause_monitor("mon_pause")
        assert result.paused is True

    @respx.mock
    def test_resume_monitor(self, client: HyperpingClient) -> None:
        """Test that resume_monitor sets paused=False on the monitor (M22)."""
        current = {
            "monitorUuid": "mon_resume",
            "name": "Paused Monitor",
            "url": "https://example.com",
            "method": "GET",
            "frequency": 60,
            "regions": ["london"],
            "headers": {},
            "expectedStatus": 200,
            "down": False,
            "paused": True,
        }
        resumed_response = {**current, "paused": False}
        respx.get(f"{API_BASE}{Endpoint.MONITORS}/mon_resume").mock(
            return_value=httpx.Response(200, json=current)
        )
        respx.put(f"{API_BASE}{Endpoint.MONITORS}/mon_resume").mock(
            return_value=httpx.Response(200, json=resumed_response)
        )

        result = client.resume_monitor("mon_resume")
        assert result.paused is False

    # ==================== M23: report tests ====================

    @respx.mock
    def test_get_all_reports(self, client: HyperpingClient) -> None:
        """Test that get_all_reports returns MonitorReport objects (M23)."""
        mock_response = {
            "period": {"from": "2024-01-01T00:00:00Z", "to": "2024-01-31T23:59:59Z"},
            "monitors": [
                {
                    "uuid": "mon_r1",
                    "name": "Report Monitor",
                    "protocol": "http",
                    "sla": 99.9,
                    "mttr": 120,
                    "mttrFormatted": "2m",
                    "outages": {
                        "count": 1,
                        "totalDowntime": 120,
                        "totalDowntimeFormatted": "2m",
                        "longestOutage": 120,
                        "longestOutageFormatted": "2m",
                        "details": [
                            {
                                "startDate": "2024-01-15T10:00:00Z",
                                "endDate": "2024-01-15T10:02:00Z",
                            }
                        ],
                    },
                }
            ],
        }
        respx.get(f"{API_BASE}{Endpoint.REPORTS}").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        reports = client.get_all_reports(period="30d")

        assert len(reports) == 1
        assert reports[0].uuid == "mon_r1"
        assert reports[0].sla == 99.9
        # Verify nested outages.details is parsed correctly
        assert len(reports[0].outages.details) == 1
        assert reports[0].outages.details[0].start_date == "2024-01-15T10:00:00Z"

    @respx.mock
    def test_get_monitor_report(self, client: HyperpingClient) -> None:
        """Test get_monitor_report returns the matching report (M23)."""
        mock_response = {
            "period": {"from": "2024-01-01T00:00:00Z", "to": "2024-01-31T23:59:59Z"},
            "monitors": [
                {
                    "uuid": "mon_target",
                    "name": "Target Monitor",
                    "protocol": "http",
                    "sla": 98.5,
                    "mttr": 0,
                    "mttrFormatted": "0s",
                    "outages": {
                        "count": 0,
                        "totalDowntime": 0,
                        "totalDowntimeFormatted": "0s",
                        "longestOutage": 0,
                        "longestOutageFormatted": "0s",
                        "details": [],
                    },
                },
                {
                    "uuid": "mon_other",
                    "name": "Other Monitor",
                    "protocol": "http",
                    "sla": 100.0,
                    "mttr": 0,
                    "mttrFormatted": "0s",
                    "outages": {
                        "count": 0,
                        "totalDowntime": 0,
                        "totalDowntimeFormatted": "0s",
                        "longestOutage": 0,
                        "longestOutageFormatted": "0s",
                        "details": [],
                    },
                },
            ],
        }
        respx.get(f"{API_BASE}{Endpoint.REPORTS}").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        report = client.get_monitor_report("mon_target")
        assert report.uuid == "mon_target"
        assert report.sla == 98.5

    @respx.mock
    def test_get_monitor_report_not_found(self, client: HyperpingClient) -> None:
        """Test get_monitor_report raises NotFoundError when UUID not in batch (M23)."""
        respx.get(f"{API_BASE}{Endpoint.REPORTS}").mock(
            return_value=httpx.Response(
                200,
                json={
                    "period": {"from": "2024-01-01", "to": "2024-01-31"},
                    "monitors": [],
                },
            )
        )

        with pytest.raises(HyperpingNotFoundError):
            client.get_monitor_report("mon_missing")

    def test_get_all_reports_invalid_period(self, client: HyperpingClient) -> None:
        """Test that an invalid period raises ValueError (M9)."""
        with pytest.raises(ValueError, match="Invalid period"):
            client.get_all_reports(period="15d")  # type: ignore[arg-type]


class TestRetryBehavior:
    """Tests for retry behavior."""

    @respx.mock
    def test_retry_on_500(self) -> None:
        """Test retry on 500 error."""
        c = HyperpingClient(
            api_key="sk_test",
            retry_config=RetryConfig(max_retries=2, initial_delay=0.01),
        )

        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return httpx.Response(500, json={"error": "Server error"})
            return httpx.Response(200, json=[])

        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(side_effect=handler)

        monitors = c.list_monitors()

        assert call_count == 3
        assert monitors == []
        c.close()

    @respx.mock
    def test_no_retry_on_400(self) -> None:
        """Test no retry on 400 error (client error)."""
        c = HyperpingClient(
            api_key="sk_test",
            retry_config=RetryConfig(max_retries=2),
        )

        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(400, json={"error": "Bad request"})

        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(side_effect=handler)

        with pytest.raises(HyperpingValidationError):
            c.list_monitors()

        # Should only be called once (no retry)
        assert call_count == 1
        c.close()


class TestContextManager:
    """Tests for context manager usage."""

    @respx.mock
    def test_context_manager(self) -> None:
        """Test client works as context manager."""
        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(return_value=httpx.Response(200, json=[]))

        with HyperpingClient(api_key="sk_test") as c:
            monitors = c.list_monitors()

        assert monitors == []


class TestSecretStrApiKey:
    """Tests for API key masking."""

    def test_api_key_not_in_repr(self) -> None:
        """repr(client) does NOT contain the API key value."""
        c = HyperpingClient(api_key="sk_super_secret_key")
        assert "sk_super_secret_key" not in repr(c)
        c.close()

    @respx.mock
    def test_api_key_used_in_auth_header(self) -> None:
        """Authorization header contains the actual key."""
        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(return_value=httpx.Response(200, json=[]))
        c = HyperpingClient(api_key="sk_test_auth")
        c.list_monitors()
        assert c._client.headers["Authorization"] == "Bearer sk_test_auth"
        c.close()

    def test_api_key_accepts_str_and_secretstr(self) -> None:
        """Constructor works with both str and SecretStr input."""
        client_str = HyperpingClient(api_key="sk_from_str")
        client_secret = HyperpingClient(api_key=SecretStr("sk_from_secret"))

        assert client_str._api_key.get_secret_value() == "sk_from_str"
        assert client_secret._api_key.get_secret_value() == "sk_from_secret"

        client_str.close()
        client_secret.close()


class TestCircuitBreakerFiltering:
    """Tests for circuit breaker only tripping on 5xx."""

    @respx.mock
    def test_4xx_error_does_not_trip_circuit_breaker(self) -> None:
        """400/404/422 responses do NOT call record_failure()."""
        c = HyperpingClient(
            api_key="sk_test",
            retry_config=RetryConfig(max_retries=0),
        )

        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(
            return_value=httpx.Response(400, json={"error": "bad request"})
        )

        with pytest.raises(HyperpingValidationError):
            c.list_monitors()

        assert c.circuit_breaker.failure_count == 0
        c.close()

    @respx.mock
    def test_5xx_error_trips_circuit_breaker(self) -> None:
        """500/502/503 responses DO call record_failure()."""
        c = HyperpingClient(
            api_key="sk_test",
            retry_config=RetryConfig(max_retries=0),
        )

        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(
            return_value=httpx.Response(500, json={"error": "server error"})
        )

        with pytest.raises(HyperpingAPIError):
            c.list_monitors()

        assert c.circuit_breaker.failure_count == 1
        c.close()

    @respx.mock
    def test_429_does_not_trip_circuit_breaker(self) -> None:
        """429 (rate limit) does NOT trip the breaker."""
        c = HyperpingClient(
            api_key="sk_test",
            retry_config=RetryConfig(max_retries=0),
        )

        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(
            return_value=httpx.Response(429, json={"error": "rate limited"})
        )

        with pytest.raises(HyperpingRateLimitError):
            c.list_monitors()

        assert c.circuit_breaker.failure_count == 0
        c.close()


class TestRetryAfterCap:
    """Tests for Retry-After honoring."""

    @respx.mock
    def test_retry_after_honored_above_max_delay(self) -> None:
        """Retry-After of 120s is honored (not capped at 30s max_delay)."""
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(
                    429,
                    json={"error": "rate limited"},
                    headers={"Retry-After": "120"},
                )
            return httpx.Response(200, json=[])

        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(side_effect=handler)

        with patch("hyperping.client.time.sleep") as mock_sleep:
            c = HyperpingClient(
                api_key="sk_test",
                retry_config=RetryConfig(max_retries=1, initial_delay=1.0, max_delay=30.0),
            )
            c.list_monitors()

            # Should have slept for 120s (not capped at 30s)
            assert mock_sleep.call_count == 1
            slept = mock_sleep.call_args[0][0]
            assert slept == 120.0
            c.close()

    @respx.mock
    def test_retry_after_capped_at_300s(self) -> None:
        """Retry-After of 600s is capped at 300s."""
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(
                    429,
                    json={"error": "rate limited"},
                    headers={"Retry-After": "600"},
                )
            return httpx.Response(200, json=[])

        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(side_effect=handler)

        with patch("hyperping.client.time.sleep") as mock_sleep:
            c = HyperpingClient(
                api_key="sk_test",
                retry_config=RetryConfig(max_retries=1, initial_delay=1.0),
            )
            c.list_monitors()

            slept = mock_sleep.call_args[0][0]
            assert slept == 300.0
            c.close()


class TestRetryJitter:
    """Tests for jitter on exponential backoff delays."""

    @respx.mock
    def test_retry_delay_has_jitter(self) -> None:
        """Verify exponential backoff delays have jitter (not exact powers of 2)."""
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return httpx.Response(500, json={"error": "server error"})
            return httpx.Response(200, json=[])

        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(side_effect=handler)

        sleep_values: list[float] = []

        def capture_sleep(duration: float) -> None:
            sleep_values.append(duration)

        with patch("hyperping.client.time.sleep", side_effect=capture_sleep):
            with patch("hyperping.client.random.uniform", wraps=__import__("random").uniform):
                c = HyperpingClient(
                    api_key="sk_test",
                    retry_config=RetryConfig(max_retries=2, initial_delay=1.0, backoff_factor=2.0),
                )
                c.list_monitors()

        assert len(sleep_values) >= 1
        if len(sleep_values) >= 2:
            assert sleep_values[1] != 4.0, "Expected jitter to make delay non-exact"

    @respx.mock
    def test_429_retry_after_no_jitter(self) -> None:
        """Verify server-provided Retry-After values are NOT jittered."""
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(
                    429,
                    json={"error": "rate limited"},
                    headers={"Retry-After": "45"},
                )
            return httpx.Response(200, json=[])

        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(side_effect=handler)

        with patch("hyperping.client.time.sleep") as mock_sleep:
            c = HyperpingClient(
                api_key="sk_test",
                retry_config=RetryConfig(max_retries=1, initial_delay=1.0),
            )
            c.list_monitors()

            # Should have slept exactly 45s (the Retry-After value), no jitter
            assert mock_sleep.call_count == 1
            slept = mock_sleep.call_args[0][0]
            assert slept == 45.0
            c.close()


class TestMonitorCreateProjectUuid:
    def test_included_in_serialized_output(self) -> None:
        m = MonitorCreate(name="t", url="https://x.com", project_uuid="proj_x")
        payload = m.model_dump(by_alias=True, exclude_none=True)
        assert payload["projectUuid"] == "proj_x"

    def test_excluded_when_none(self) -> None:
        m = MonitorCreate(name="t", url="https://x.com")
        payload = m.model_dump(by_alias=True, exclude_none=True)
        assert "projectUuid" not in payload


class TestMonitorUpdateProjectUuid:
    def test_included_in_serialized_output(self) -> None:
        m = MonitorUpdate(project_uuid="proj_x")
        payload = m.model_dump(by_alias=True, exclude_none=True)
        assert payload["projectUuid"] == "proj_x"

    def test_excluded_when_none(self) -> None:
        m = MonitorUpdate()
        payload = m.model_dump(by_alias=True, exclude_none=True)
        assert "projectUuid" not in payload

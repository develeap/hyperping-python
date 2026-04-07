"""Tests for AsyncHyperpingClient."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio

from hyperping._async_client import AsyncHyperpingClient
from hyperping.client import RetryConfig
from hyperping.endpoints import API_BASE
from hyperping.exceptions import (
    HyperpingAPIError,
    HyperpingAuthError,
    HyperpingNotFoundError,
    HyperpingRateLimitError,
    HyperpingValidationError,
)
from hyperping.models import Monitor, MonitorCreate, MonitorUpdate, OutageAction

# ==================== Fixtures ====================


@pytest_asyncio.fixture
async def async_client() -> AsyncHyperpingClient:
    """Async client with retries disabled for deterministic tests."""
    client = AsyncHyperpingClient(
        api_key="sk_test_key",
        base_url=API_BASE,
        retry_config=RetryConfig(max_retries=0),
    )
    yield client
    await client.close()


def _make_monitor_payload(uuid: str = "mon_123", name: str = "Test Monitor") -> dict:
    return {
        "monitorUuid": uuid,
        "name": name,
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


# ==================== Construction ====================


class TestAsyncClientConstruction:
    """Tests for AsyncHyperpingClient construction."""

    def test_rejects_empty_api_key(self) -> None:
        """AsyncHyperpingClient raises ValueError for empty api_key."""
        with pytest.raises(ValueError, match="api_key must be a non-empty string"):
            AsyncHyperpingClient(api_key="")

    def test_rejects_whitespace_api_key(self) -> None:
        """AsyncHyperpingClient raises ValueError for whitespace-only api_key."""
        with pytest.raises(ValueError, match="api_key must be a non-empty string"):
            AsyncHyperpingClient(api_key="   ")

    def test_repr_does_not_expose_key(self) -> None:
        """repr(client) should not contain the API key value."""
        client = AsyncHyperpingClient(api_key="sk_super_secret")
        assert "sk_super_secret" not in repr(client)

    def test_accepts_valid_api_key(self) -> None:
        """AsyncHyperpingClient accepts a valid API key string."""
        client = AsyncHyperpingClient(api_key="sk_valid_key")
        assert client._api_key.get_secret_value() == "sk_valid_key"


# ==================== Context Manager ====================


class TestAsyncContextManager:
    """Tests for async context manager support."""

    @pytest.mark.asyncio
    async def test_aenter_returns_client(self) -> None:
        """__aenter__ returns the client instance."""
        client = AsyncHyperpingClient(api_key="sk_test")
        async with client as c:
            assert c is client

    @pytest.mark.asyncio
    async def test_aexit_closes_client(self) -> None:
        """__aexit__ calls close() which calls aclose on the inner httpx client."""
        client = AsyncHyperpingClient(api_key="sk_test")
        close_mock = AsyncMock()
        client._client.aclose = close_mock

        async with client:
            pass

        close_mock.assert_awaited_once()

    def test_no_sync_context_manager(self) -> None:
        """AsyncHyperpingClient does not support sync with statement."""
        client = AsyncHyperpingClient(api_key="sk_test")
        assert not hasattr(client, "__enter__")
        assert not hasattr(client, "__exit__")


# ==================== list_monitors (mocked httpx) ====================


class TestAsyncListMonitors:
    """Tests for async list_monitors."""

    @pytest.mark.asyncio
    async def test_list_monitors_returns_monitor_list(self) -> None:
        """list_monitors returns list[Monitor] on success."""
        payload = [_make_monitor_payload()]
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = payload
        mock_response.headers = {}

        async with AsyncHyperpingClient(
            api_key="sk_test",
            retry_config=RetryConfig(max_retries=0),
        ) as client:
            client._client.request = AsyncMock(return_value=mock_response)
            monitors = await client.list_monitors()

        assert isinstance(monitors, list)
        assert len(monitors) == 1
        assert isinstance(monitors[0], Monitor)
        assert monitors[0].uuid == "mon_123"
        assert monitors[0].name == "Test Monitor"

    @pytest.mark.asyncio
    async def test_list_monitors_empty(self) -> None:
        """list_monitors returns empty list when API returns empty array."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.headers = {}

        async with AsyncHyperpingClient(
            api_key="sk_test",
            retry_config=RetryConfig(max_retries=0),
        ) as client:
            client._client.request = AsyncMock(return_value=mock_response)
            monitors = await client.list_monitors()

        assert monitors == []


# ==================== ping ====================


class TestAsyncPing:
    """Tests for async ping method."""

    @pytest.mark.asyncio
    async def test_ping_returns_true_on_success(self) -> None:
        """ping() returns True when monitors endpoint responds 200."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.headers = {}

        async with AsyncHyperpingClient(
            api_key="sk_test",
            retry_config=RetryConfig(max_retries=0),
        ) as client:
            client._client.request = AsyncMock(return_value=mock_response)
            result = await client.ping()

        assert result is True

    @pytest.mark.asyncio
    async def test_ping_raises_auth_error_on_401(self) -> None:
        """ping() re-raises HyperpingAuthError when API returns 401."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 401
        mock_response.json.return_value = {"error": "Unauthorized"}
        mock_response.headers = {}
        mock_response.text = "Unauthorized"

        async with AsyncHyperpingClient(
            api_key="sk_test",
            retry_config=RetryConfig(max_retries=0),
        ) as client:
            client._client.request = AsyncMock(return_value=mock_response)
            with pytest.raises(HyperpingAuthError):
                await client.ping()

    @pytest.mark.asyncio
    async def test_ping_wraps_api_error(self) -> None:
        """ping() wraps connection errors in HyperpingAPIError."""
        async with AsyncHyperpingClient(
            api_key="sk_test",
            retry_config=RetryConfig(max_retries=0),
        ) as client:
            client._client.request = AsyncMock(
                side_effect=httpx.ConnectError("connection refused")
            )
            with pytest.raises(HyperpingAPIError, match="API connectivity test failed"):
                await client.ping()


# ==================== Retry behavior ====================


class TestAsyncRetryBehavior:
    """Tests for async retry behavior with asyncio.sleep."""

    @pytest.mark.asyncio
    async def test_retry_on_500_uses_asyncio_sleep(self) -> None:
        """Retry logic calls asyncio.sleep (not time.sleep) between attempts."""
        call_count = 0

        async def side_effect(**kwargs):  # type: ignore[no-untyped-def]
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock(spec=httpx.Response)
            if call_count < 3:
                mock_resp.status_code = 500
                mock_resp.json.return_value = {"error": "Server error"}
                mock_resp.headers = {}
                mock_resp.text = "Server error"
            else:
                mock_resp.status_code = 200
                mock_resp.json.return_value = []
                mock_resp.headers = {}
            return mock_resp

        client = AsyncHyperpingClient(
            api_key="sk_test",
            retry_config=RetryConfig(max_retries=2, initial_delay=0.01),
        )

        with patch("hyperping._async_client.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            client._client.request = AsyncMock(side_effect=side_effect)
            monitors = await client.list_monitors()

        assert call_count == 3
        assert monitors == []
        assert mock_sleep.await_count >= 1
        await client.close()

    @pytest.mark.asyncio
    async def test_no_retry_on_400(self) -> None:
        """Retry logic does not retry on 400 client errors."""
        call_count = 0

        async def side_effect(**kwargs):  # type: ignore[no-untyped-def]
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock(spec=httpx.Response)
            mock_resp.status_code = 400
            mock_resp.json.return_value = {"error": "Bad request"}
            mock_resp.headers = {}
            mock_resp.text = "Bad request"
            return mock_resp

        from hyperping.exceptions import HyperpingValidationError

        client = AsyncHyperpingClient(
            api_key="sk_test",
            retry_config=RetryConfig(max_retries=2),
        )
        client._client.request = AsyncMock(side_effect=side_effect)

        with pytest.raises(HyperpingValidationError):
            await client.list_monitors()

        assert call_count == 1
        await client.close()


# ==================== Circuit Breaker ====================


class TestAsyncCircuitBreaker:
    """Tests for circuit breaker behavior in AsyncHyperpingClient."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_on_repeated_failures(self) -> None:
        """Circuit breaker opens after consecutive 500 errors."""
        from hyperping._circuit_breaker import CircuitBreakerConfig

        cb_config = CircuitBreakerConfig(failure_threshold=2, recovery_timeout=60)
        client = AsyncHyperpingClient(
            api_key="sk_test",
            retry_config=RetryConfig(max_retries=0),
            circuit_breaker_config=cb_config,
        )

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 500
        mock_resp.json.return_value = {"error": "Server error"}
        mock_resp.headers = {}
        mock_resp.text = "Server error"
        client._client.request = AsyncMock(return_value=mock_resp)

        with pytest.raises(HyperpingAPIError):
            await client.list_monitors()
        with pytest.raises(HyperpingAPIError):
            await client.list_monitors()

        assert client.circuit_breaker.failure_count >= 2
        await client.close()

    @pytest.mark.asyncio
    async def test_4xx_does_not_trip_circuit_breaker(self) -> None:
        """400/404/422 responses do not record circuit breaker failures."""
        client = AsyncHyperpingClient(
            api_key="sk_test",
            retry_config=RetryConfig(max_retries=0),
        )

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 400
        mock_resp.json.return_value = {"error": "bad request"}
        mock_resp.headers = {}
        mock_resp.text = "bad request"
        client._client.request = AsyncMock(return_value=mock_resp)

        from hyperping.exceptions import HyperpingValidationError

        with pytest.raises(HyperpingValidationError):
            await client.list_monitors()

        assert client.circuit_breaker.failure_count == 0
        await client.close()


def _mock_ok(json_body: object, status: int = 200) -> MagicMock:
    """Build a mock httpx.Response for a successful request."""
    r = MagicMock(spec=httpx.Response)
    r.status_code = status
    r.json.return_value = json_body
    r.headers = {}
    return r


def _mock_err(status: int, body: dict) -> MagicMock:
    """Build a mock httpx.Response for an error response."""
    r = MagicMock(spec=httpx.Response)
    r.status_code = status
    r.json.return_value = body
    r.headers = {}
    r.text = body.get("error", "error")
    return r


# ==================== Monitors mixin ====================


class TestAsyncMonitorsMixin:
    """Tests for AsyncMonitorsMixin methods."""

    @pytest.mark.asyncio
    async def test_get_monitor(self) -> None:
        """get_monitor returns a Monitor for valid ID."""
        async with AsyncHyperpingClient(
            api_key="sk_test", retry_config=RetryConfig(max_retries=0)
        ) as client:
            client._client.request = AsyncMock(
                return_value=_mock_ok(_make_monitor_payload("mon_abc"))
            )
            monitor = await client.get_monitor("mon_abc")
        assert monitor.uuid == "mon_abc"

    @pytest.mark.asyncio
    async def test_create_monitor(self) -> None:
        """create_monitor returns the created Monitor."""
        async with AsyncHyperpingClient(
            api_key="sk_test", retry_config=RetryConfig(max_retries=0)
        ) as client:
            client._client.request = AsyncMock(
                return_value=_mock_ok(_make_monitor_payload("mon_new"), status=201)
            )
            result = await client.create_monitor(
                MonitorCreate(name="New Monitor", url="https://example.com")
            )
        assert result.uuid == "mon_new"

    @pytest.mark.asyncio
    async def test_update_monitor(self) -> None:
        """update_monitor performs read-modify-write and returns updated Monitor."""
        current = _make_monitor_payload("mon_upd")
        updated = {**current, "name": "New Name"}
        responses = [_mock_ok(current), _mock_ok(updated)]
        async with AsyncHyperpingClient(
            api_key="sk_test", retry_config=RetryConfig(max_retries=0)
        ) as client:
            client._client.request = AsyncMock(side_effect=responses)
            result = await client.update_monitor("mon_upd", MonitorUpdate(name="New Name"))
        assert result.name == "New Name"

    @pytest.mark.asyncio
    async def test_delete_monitor(self) -> None:
        """delete_monitor completes without error on 204."""
        r = MagicMock(spec=httpx.Response)
        r.status_code = 204
        r.headers = {}
        async with AsyncHyperpingClient(
            api_key="sk_test", retry_config=RetryConfig(max_retries=0)
        ) as client:
            client._client.request = AsyncMock(return_value=r)
            await client.delete_monitor("mon_del")

    @pytest.mark.asyncio
    async def test_pause_monitor(self) -> None:
        """pause_monitor sets paused=True."""
        current = _make_monitor_payload("mon_pause")
        paused = {**current, "paused": True}
        responses = [_mock_ok(current), _mock_ok(paused)]
        async with AsyncHyperpingClient(
            api_key="sk_test", retry_config=RetryConfig(max_retries=0)
        ) as client:
            client._client.request = AsyncMock(side_effect=responses)
            result = await client.pause_monitor("mon_pause")
        assert result.paused is True

    @pytest.mark.asyncio
    async def test_resume_monitor(self) -> None:
        """resume_monitor sets paused=False."""
        current = {**_make_monitor_payload("mon_resume"), "paused": True}
        resumed = {**current, "paused": False}
        responses = [_mock_ok(current), _mock_ok(resumed)]
        async with AsyncHyperpingClient(
            api_key="sk_test", retry_config=RetryConfig(max_retries=0)
        ) as client:
            client._client.request = AsyncMock(side_effect=responses)
            result = await client.resume_monitor("mon_resume")
        assert result.paused is False

    @pytest.mark.asyncio
    async def test_get_monitor_not_found(self) -> None:
        """get_monitor raises HyperpingNotFoundError on 404."""
        async with AsyncHyperpingClient(
            api_key="sk_test", retry_config=RetryConfig(max_retries=0)
        ) as client:
            client._client.request = AsyncMock(
                return_value=_mock_err(404, {"error": "Not found"})
            )
            with pytest.raises(HyperpingNotFoundError):
                await client.get_monitor("mon_missing")

    @pytest.mark.asyncio
    async def test_get_all_reports(self) -> None:
        """get_all_reports returns MonitorReport objects."""
        report_payload = {
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
                        "count": 0,
                        "totalDowntime": 0,
                        "totalDowntimeFormatted": "0s",
                        "longestOutage": 0,
                        "longestOutageFormatted": "0s",
                        "details": [],
                    },
                }
            ],
        }
        async with AsyncHyperpingClient(
            api_key="sk_test", retry_config=RetryConfig(max_retries=0)
        ) as client:
            client._client.request = AsyncMock(return_value=_mock_ok(report_payload))
            reports = await client.get_all_reports(period="30d")
        assert len(reports) == 1
        assert reports[0].sla == 99.9

    @pytest.mark.asyncio
    async def test_get_all_reports_invalid_period(self) -> None:
        """get_all_reports raises ValueError for unknown period."""
        async with AsyncHyperpingClient(
            api_key="sk_test", retry_config=RetryConfig(max_retries=0)
        ) as client:
            with pytest.raises(ValueError, match="Invalid period"):
                await client.get_all_reports(period="15d")  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_get_monitor_report_not_found(self) -> None:
        """get_monitor_report raises HyperpingNotFoundError if UUID not in batch."""
        report_payload = {
            "period": {"from": "2024-01-01", "to": "2024-01-31"},
            "monitors": [],
        }
        async with AsyncHyperpingClient(
            api_key="sk_test", retry_config=RetryConfig(max_retries=0)
        ) as client:
            client._client.request = AsyncMock(return_value=_mock_ok(report_payload))
            with pytest.raises(HyperpingNotFoundError):
                await client.get_monitor_report("mon_missing")


# ==================== Outages mixin ====================


class TestAsyncOutagesMixin:
    """Tests for AsyncOutagesMixin methods."""

    @pytest.mark.asyncio
    async def test_list_outages_success(self) -> None:
        """list_outages returns Outage objects from dict response."""
        payload = {
            "outages": [{"uuid": "out_1", "monitor_uuid": "mon_1", "status": "active"}]
        }
        async with AsyncHyperpingClient(
            api_key="sk_test", retry_config=RetryConfig(max_retries=0)
        ) as client:
            client._client.request = AsyncMock(return_value=_mock_ok(payload))
            outages = await client.list_outages()
        assert len(outages) == 1
        assert outages[0].uuid == "out_1"

    @pytest.mark.asyncio
    async def test_list_outages_as_list(self) -> None:
        """list_outages handles raw list response."""
        payload = [{"uuid": "out_2", "monitor_uuid": "mon_2", "status": "active"}]
        async with AsyncHyperpingClient(
            api_key="sk_test", retry_config=RetryConfig(max_retries=0)
        ) as client:
            client._client.request = AsyncMock(return_value=_mock_ok(payload))
            outages = await client.list_outages()
        assert len(outages) == 1

    @pytest.mark.asyncio
    async def test_list_outages_empty_on_404(self) -> None:
        """list_outages returns empty list on 404."""
        async with AsyncHyperpingClient(
            api_key="sk_test", retry_config=RetryConfig(max_retries=0)
        ) as client:
            client._client.request = AsyncMock(
                return_value=_mock_err(404, {"error": "Not found"})
            )
            outages = await client.list_outages()
        assert outages == []

    @pytest.mark.asyncio
    async def test_acknowledge_outage(self) -> None:
        """acknowledge_outage returns OutageAction."""
        async with AsyncHyperpingClient(
            api_key="sk_test", retry_config=RetryConfig(max_retries=0)
        ) as client:
            client._client.request = AsyncMock(
                return_value=_mock_ok({"status": "acknowledged"})
            )
            result = await client.acknowledge_outage("out_1")
        assert isinstance(result, OutageAction)
        assert result.status == "acknowledged"

    @pytest.mark.asyncio
    async def test_resolve_outage(self) -> None:
        """resolve_outage returns OutageAction."""
        async with AsyncHyperpingClient(
            api_key="sk_test", retry_config=RetryConfig(max_retries=0)
        ) as client:
            client._client.request = AsyncMock(
                return_value=_mock_ok({"status": "resolved"})
            )
            result = await client.resolve_outage("out_1")
        assert result.status == "resolved"

    @pytest.mark.asyncio
    async def test_escalate_outage(self) -> None:
        """escalate_outage returns OutageAction."""
        async with AsyncHyperpingClient(
            api_key="sk_test", retry_config=RetryConfig(max_retries=0)
        ) as client:
            client._client.request = AsyncMock(
                return_value=_mock_ok({"status": "escalated"})
            )
            result = await client.escalate_outage("out_1")
        assert result.status == "escalated"


# ==================== Error mapping ====================


class TestAsyncErrorMapping:
    """Tests for HTTP error code to exception mapping."""

    @pytest.mark.asyncio
    async def test_401_raises_auth_error(self) -> None:
        """HTTP 401 maps to HyperpingAuthError."""
        async with AsyncHyperpingClient(
            api_key="sk_test", retry_config=RetryConfig(max_retries=0)
        ) as client:
            client._client.request = AsyncMock(
                return_value=_mock_err(401, {"error": "Unauthorized"})
            )
            with pytest.raises(HyperpingAuthError):
                await client.list_monitors()

    @pytest.mark.asyncio
    async def test_404_raises_not_found(self) -> None:
        """HTTP 404 maps to HyperpingNotFoundError."""
        async with AsyncHyperpingClient(
            api_key="sk_test", retry_config=RetryConfig(max_retries=0)
        ) as client:
            client._client.request = AsyncMock(
                return_value=_mock_err(404, {"error": "Not found"})
            )
            with pytest.raises(HyperpingNotFoundError):
                await client.get_monitor("mon_nope")

    @pytest.mark.asyncio
    async def test_429_raises_rate_limit(self) -> None:
        """HTTP 429 maps to HyperpingRateLimitError."""
        r = _mock_err(429, {"error": "Rate limited"})
        r.headers = {"Retry-After": "60"}
        async with AsyncHyperpingClient(
            api_key="sk_test", retry_config=RetryConfig(max_retries=0)
        ) as client:
            client._client.request = AsyncMock(return_value=r)
            with pytest.raises(HyperpingRateLimitError) as exc_info:
                await client.list_monitors()
        assert exc_info.value.retry_after == 60

    @pytest.mark.asyncio
    async def test_422_raises_validation_error(self) -> None:
        """HTTP 422 maps to HyperpingValidationError."""
        async with AsyncHyperpingClient(
            api_key="sk_test", retry_config=RetryConfig(max_retries=0)
        ) as client:
            client._client.request = AsyncMock(
                return_value=_mock_err(422, {"error": "Validation failed"})
            )
            with pytest.raises(HyperpingValidationError):
                await client.list_monitors()

    @pytest.mark.asyncio
    async def test_500_raises_api_error(self) -> None:
        """HTTP 500 maps to HyperpingAPIError."""
        async with AsyncHyperpingClient(
            api_key="sk_test", retry_config=RetryConfig(max_retries=0)
        ) as client:
            client._client.request = AsyncMock(
                return_value=_mock_err(500, {"error": "Server error"})
            )
            with pytest.raises(HyperpingAPIError):
                await client.list_monitors()

    @pytest.mark.asyncio
    async def test_timeout_exception_raises_api_error(self) -> None:
        """httpx.TimeoutException is wrapped in HyperpingAPIError after retries."""
        async with AsyncHyperpingClient(
            api_key="sk_test", retry_config=RetryConfig(max_retries=0)
        ) as client:
            client._client.request = AsyncMock(
                side_effect=httpx.TimeoutException("timed out")
            )
            with pytest.raises(HyperpingAPIError, match="timeout"):
                await client.list_monitors()

    @pytest.mark.asyncio
    async def test_request_error_raises_api_error(self) -> None:
        """httpx.ConnectError is wrapped in HyperpingAPIError after retries."""
        async with AsyncHyperpingClient(
            api_key="sk_test", retry_config=RetryConfig(max_retries=0)
        ) as client:
            client._client.request = AsyncMock(
                side_effect=httpx.ConnectError("connection refused")
            )
            with pytest.raises(HyperpingAPIError, match="Request failed"):
                await client.list_monitors()


# ==================== Retry with Retry-After ====================


class TestAsyncRetryAfter:
    """Tests for Retry-After header handling in async client."""

    @pytest.mark.asyncio
    async def test_retry_after_honored(self) -> None:
        """Retry-After of 5s is passed to asyncio.sleep on 429."""
        call_count = 0

        async def side_effect(**kwargs):  # type: ignore[no-untyped-def]
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                r = _mock_err(429, {"error": "rate limited"})
                r.headers = {"Retry-After": "5"}
                return r
            return _mock_ok([])

        client = AsyncHyperpingClient(
            api_key="sk_test",
            retry_config=RetryConfig(max_retries=1, initial_delay=1.0),
        )
        with patch("hyperping._async_client.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            client._client.request = AsyncMock(side_effect=side_effect)
            await client.list_monitors()

        assert mock_sleep.await_count == 1
        slept = mock_sleep.await_args[0][0]
        assert slept == 5.0
        await client.close()


# ==================== Outages mixin (pagination) ====================


class TestAsyncOutagesPagination:
    """Tests for pagination paths in AsyncOutagesMixin."""

    @pytest.mark.asyncio
    async def test_list_outages_invalid_status(self) -> None:
        """list_outages raises ValueError for unknown status."""
        async with AsyncHyperpingClient(
            api_key="sk_test", retry_config=RetryConfig(max_retries=0)
        ) as client:
            with pytest.raises(ValueError, match="Invalid status"):
                await client.list_outages(status="unknown")

    @pytest.mark.asyncio
    async def test_list_outages_invalid_type(self) -> None:
        """list_outages raises ValueError for unknown outage_type."""
        async with AsyncHyperpingClient(
            api_key="sk_test", retry_config=RetryConfig(max_retries=0)
        ) as client:
            with pytest.raises(ValueError, match="Invalid outage_type"):
                await client.list_outages(outage_type="bad")

    @pytest.mark.asyncio
    async def test_list_outages_explicit_page(self) -> None:
        """list_outages with explicit page returns single-page results."""
        payload = {
            "outages": [{"uuid": "out_p1", "monitor_uuid": "mon_1", "status": "active"}]
        }
        async with AsyncHyperpingClient(
            api_key="sk_test", retry_config=RetryConfig(max_retries=0)
        ) as client:
            client._client.request = AsyncMock(return_value=_mock_ok(payload))
            outages = await client.list_outages(page=0)
        assert len(outages) == 1
        assert outages[0].uuid == "out_p1"

    @pytest.mark.asyncio
    async def test_list_outages_with_status_filter(self) -> None:
        """list_outages with status filter passes param and auto-paginates."""
        payload = {
            "outages": [{"uuid": "out_ongoing", "monitor_uuid": "mon_1", "status": "active"}],
            "hasNextPage": False,
        }
        async with AsyncHyperpingClient(
            api_key="sk_test", retry_config=RetryConfig(max_retries=0)
        ) as client:
            client._client.request = AsyncMock(return_value=_mock_ok(payload))
            outages = await client.list_outages(status="ongoing")
        assert len(outages) == 1

    @pytest.mark.asyncio
    async def test_list_outages_multipage(self) -> None:
        """list_outages auto-paginates when hasNextPage is True."""
        page1 = {
            "outages": [{"uuid": "out_1", "monitor_uuid": "mon_1", "status": "active"}],
            "hasNextPage": True,
        }
        page2 = {
            "outages": [{"uuid": "out_2", "monitor_uuid": "mon_2", "status": "active"}],
            "hasNextPage": False,
        }
        async with AsyncHyperpingClient(
            api_key="sk_test", retry_config=RetryConfig(max_retries=0)
        ) as client:
            client._client.request = AsyncMock(
                side_effect=[_mock_ok(page1), _mock_ok(page2)]
            )
            outages = await client.list_outages()
        assert len(outages) == 2


# ==================== StatusPages mixin ====================


class TestAsyncStatusPagesMixin:
    """Tests for AsyncStatusPagesMixin methods."""

    @pytest.mark.asyncio
    async def test_list_status_pages(self) -> None:
        """list_status_pages returns StatusPage objects."""
        from hyperping.models import StatusPage

        payload = {
            "statuspages": [
                {
                    "uuid": "sp_1",
                    "name": "My Status Page",
                    "subdomain": "mystatus",
                    "monitors": [],
                }
            ],
            "hasNextPage": False,
        }
        async with AsyncHyperpingClient(
            api_key="sk_test", retry_config=RetryConfig(max_retries=0)
        ) as client:
            client._client.request = AsyncMock(return_value=_mock_ok(payload))
            pages = await client.list_status_pages()
        assert len(pages) == 1
        assert isinstance(pages[0], StatusPage)

    @pytest.mark.asyncio
    async def test_list_status_pages_explicit_page(self) -> None:
        """list_status_pages with explicit page returns single-page results."""
        payload = {
            "statuspages": [
                {
                    "uuid": "sp_2",
                    "name": "Page 2",
                    "subdomain": "page2",
                    "monitors": [],
                }
            ]
        }
        async with AsyncHyperpingClient(
            api_key="sk_test", retry_config=RetryConfig(max_retries=0)
        ) as client:
            client._client.request = AsyncMock(return_value=_mock_ok(payload))
            pages = await client.list_status_pages(page=0)
        assert len(pages) == 1

    @pytest.mark.asyncio
    async def test_list_status_pages_404_returns_empty(self) -> None:
        """list_status_pages returns empty list on 404."""
        async with AsyncHyperpingClient(
            api_key="sk_test", retry_config=RetryConfig(max_retries=0)
        ) as client:
            client._client.request = AsyncMock(
                return_value=_mock_err(404, {"error": "Not found"})
            )
            pages = await client.list_status_pages()
        assert pages == []

    @pytest.mark.asyncio
    async def test_get_status_page(self) -> None:
        """get_status_page returns a StatusPage for valid ID."""
        payload = {"uuid": "sp_3", "name": "Test Page", "subdomain": "test", "monitors": []}
        async with AsyncHyperpingClient(
            api_key="sk_test", retry_config=RetryConfig(max_retries=0)
        ) as client:
            client._client.request = AsyncMock(return_value=_mock_ok(payload))
            page = await client.get_status_page("sp_3")
        assert page.uuid == "sp_3"

    @pytest.mark.asyncio
    async def test_create_status_page(self) -> None:
        """create_status_page returns created StatusPage."""
        from hyperping.models import StatusPageCreate

        payload = {
            "uuid": "sp_new",
            "name": "New Page",
            "subdomain": "newpage",
            "monitors": [],
        }
        async with AsyncHyperpingClient(
            api_key="sk_test", retry_config=RetryConfig(max_retries=0)
        ) as client:
            client._client.request = AsyncMock(return_value=_mock_ok(payload))
            result = await client.create_status_page(
                StatusPageCreate(name="New Page", subdomain="newpage")
            )
        assert result.uuid == "sp_new"

    @pytest.mark.asyncio
    async def test_update_status_page(self) -> None:
        """update_status_page returns updated StatusPage."""
        from hyperping.models import StatusPageUpdate

        payload = {"uuid": "sp_u", "name": "Updated", "subdomain": "updated", "monitors": []}
        async with AsyncHyperpingClient(
            api_key="sk_test", retry_config=RetryConfig(max_retries=0)
        ) as client:
            client._client.request = AsyncMock(return_value=_mock_ok(payload))
            result = await client.update_status_page("sp_u", StatusPageUpdate(name="Updated"))
        assert result.name == "Updated"

    @pytest.mark.asyncio
    async def test_delete_status_page(self) -> None:
        """delete_status_page completes without error on 204."""
        r = MagicMock(spec=httpx.Response)
        r.status_code = 204
        r.headers = {}
        async with AsyncHyperpingClient(
            api_key="sk_test", retry_config=RetryConfig(max_retries=0)
        ) as client:
            client._client.request = AsyncMock(return_value=r)
            await client.delete_status_page("sp_del")

    @pytest.mark.asyncio
    async def test_list_subscribers(self) -> None:
        """list_subscribers returns StatusPageSubscriber objects."""
        from hyperping.models import StatusPageSubscriber

        payload = {
            "subscribers": [{"id": "sub_1", "email": "test@example.com", "type": "email"}],
            "hasNextPage": False,
        }
        async with AsyncHyperpingClient(
            api_key="sk_test", retry_config=RetryConfig(max_retries=0)
        ) as client:
            client._client.request = AsyncMock(return_value=_mock_ok(payload))
            subs = await client.list_subscribers("sp_1")
        assert len(subs) == 1
        assert isinstance(subs[0], StatusPageSubscriber)

    @pytest.mark.asyncio
    async def test_list_subscribers_explicit_page(self) -> None:
        """list_subscribers with explicit page returns single-page results."""
        payload = {
            "subscribers": [{"id": "sub_2", "email": "a@b.com", "type": "email"}]
        }
        async with AsyncHyperpingClient(
            api_key="sk_test", retry_config=RetryConfig(max_retries=0)
        ) as client:
            client._client.request = AsyncMock(return_value=_mock_ok(payload))
            subs = await client.list_subscribers("sp_1", page=0)
        assert len(subs) == 1

    @pytest.mark.asyncio
    async def test_add_subscriber(self) -> None:
        """add_subscriber returns created StatusPageSubscriber."""
        payload = {"id": "sub_new", "email": "new@example.com", "type": "email"}
        async with AsyncHyperpingClient(
            api_key="sk_test", retry_config=RetryConfig(max_retries=0)
        ) as client:
            client._client.request = AsyncMock(return_value=_mock_ok(payload))
            result = await client.add_subscriber("sp_1", "new@example.com")
        assert result.email == "new@example.com"

    @pytest.mark.asyncio
    async def test_add_subscriber_invalid_email(self) -> None:
        """add_subscriber raises ValueError for malformed email."""
        async with AsyncHyperpingClient(
            api_key="sk_test", retry_config=RetryConfig(max_retries=0)
        ) as client:
            with pytest.raises(ValueError, match="Invalid email"):
                await client.add_subscriber("sp_1", "not-an-email")

    @pytest.mark.asyncio
    async def test_remove_subscriber(self) -> None:
        """remove_subscriber completes without error on 204."""
        r = MagicMock(spec=httpx.Response)
        r.status_code = 204
        r.headers = {}
        async with AsyncHyperpingClient(
            api_key="sk_test", retry_config=RetryConfig(max_retries=0)
        ) as client:
            client._client.request = AsyncMock(return_value=r)
            await client.remove_subscriber("sp_1", "sub_1")

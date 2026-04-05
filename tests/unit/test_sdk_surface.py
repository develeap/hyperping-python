"""SDK public surface tests.

Tests the Hyperping client package as an external SDK consumer would use it.
Existing test_*.py files are regression anchors -- this file covers
the public API contract for SDK extraction.
"""

import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx
from pydantic import ValidationError as PydanticValidationError

import hyperping as client_pkg
from hyperping import (
    API_BASE,
    HyperpingAPIError,
    HyperpingAuthError,
    HyperpingClient,
    HyperpingNotFoundError,
    HyperpingRateLimitError,
    HyperpingValidationError,
    __version__,
)
from hyperping.client import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    RetryConfig,
)
from hyperping.endpoints import Endpoint
from hyperping.models import (
    APIErrorResponse,
    DnsRecordType,
    HttpMethod,
    Incident,
    IncidentCreate,
    IncidentUpdate,
    LocalizedText,
    Maintenance,
    MaintenanceCreate,
    Monitor,
    MonitorCreate,
    MonitorFrequency,
    MonitorListResponse,
    MonitorProtocol,
    MonitorReport,
    MonitorTimeout,
    NotificationOption,
    OutageDetail,
    OutageStats,
    Region,
    ReportPeriod,
)

# ==================== Task 1: Exception Hierarchy ====================


class TestExceptionHierarchy:
    """Verify exception classes carry request_id and status_code."""

    def test_base_error_has_request_id(self) -> None:
        err = HyperpingAPIError("fail", status_code=500, request_id="req_abc123")
        assert err.request_id == "req_abc123"
        assert err.status_code == 500

    def test_base_error_request_id_defaults_to_none(self) -> None:
        err = HyperpingAPIError("fail", status_code=500)
        assert err.request_id is None

    def test_auth_error_inherits_request_id(self) -> None:
        err = HyperpingAuthError("denied", status_code=401, request_id="req_xyz")
        assert err.request_id == "req_xyz"
        assert isinstance(err, HyperpingAPIError)

    def test_rate_limit_error_has_retry_after_and_request_id(self) -> None:
        err = HyperpingRateLimitError(
            "slow down", status_code=429, retry_after=60, request_id="req_rl"
        )
        assert err.retry_after == 60
        assert err.request_id == "req_rl"

    def test_validation_error_has_errors_and_request_id(self) -> None:
        errs = [{"field": "name", "message": "required"}]
        err = HyperpingValidationError(
            "bad input", status_code=422, validation_errors=errs, request_id="req_ve"
        )
        assert err.validation_errors == errs
        assert err.request_id == "req_ve"

    def test_not_found_error_inherits_request_id(self) -> None:
        err = HyperpingNotFoundError("gone", status_code=404, request_id="req_nf")
        assert err.request_id == "req_nf"

    def test_str_includes_status_code(self) -> None:
        err = HyperpingAPIError("something broke", status_code=503)
        assert "[503]" in str(err)

    def test_str_without_status_code(self) -> None:
        err = HyperpingAPIError("network error")
        assert str(err) == "network error"


# ==================== Task 2: Request ID Propagation ====================


class TestRequestIdPropagation:
    """Verify request_id flows from response headers to exceptions."""

    @respx.mock
    def test_error_includes_request_id_from_header(self, client: HyperpingClient) -> None:
        respx.get(f"{API_BASE}/v1/monitors").mock(
            return_value=httpx.Response(
                500,
                json={"error": "Internal Server Error"},
                headers={"x-request-id": "req_abc123"},
            )
        )
        with pytest.raises(HyperpingAPIError) as exc_info:
            client.list_monitors()
        assert exc_info.value.request_id == "req_abc123"

    @respx.mock
    def test_error_request_id_none_when_header_missing(self, client: HyperpingClient) -> None:
        respx.get(f"{API_BASE}/v1/monitors").mock(
            return_value=httpx.Response(500, json={"error": "fail"})
        )
        with pytest.raises(HyperpingAPIError) as exc_info:
            client.list_monitors()
        assert exc_info.value.request_id is None

    @respx.mock
    def test_auth_error_includes_request_id(self, client: HyperpingClient) -> None:
        respx.get(f"{API_BASE}/v1/monitors").mock(
            return_value=httpx.Response(
                401,
                json={"error": "Unauthorized"},
                headers={"x-request-id": "req_auth"},
            )
        )
        with pytest.raises(HyperpingAuthError) as exc_info:
            client.list_monitors()
        assert exc_info.value.request_id == "req_auth"

    @respx.mock
    def test_rate_limit_error_includes_request_id(self, client: HyperpingClient) -> None:
        respx.get(f"{API_BASE}/v1/monitors").mock(
            return_value=httpx.Response(
                429,
                json={"error": "Rate limited"},
                headers={"x-request-id": "req_rl", "Retry-After": "30"},
            )
        )
        with pytest.raises(HyperpingRateLimitError) as exc_info:
            client.list_monitors()
        assert exc_info.value.request_id == "req_rl"
        assert exc_info.value.retry_after == 30


# ==================== Task 3: User-Agent Header ====================


class TestUserAgent:
    """Verify User-Agent header is sent and configurable."""

    @respx.mock
    def test_default_user_agent_sent(self) -> None:
        route = respx.get(f"{API_BASE}/v1/monitors").mock(return_value=httpx.Response(200, json=[]))
        c = HyperpingClient(api_key="sk_test", retry_config=RetryConfig(max_retries=0))
        c.list_monitors()
        c.close()

        sent_headers = route.calls[0].request.headers
        assert sent_headers["user-agent"] == f"hyperping-python/{__version__}"

    @respx.mock
    def test_custom_user_agent(self) -> None:
        route = respx.get(f"{API_BASE}/v1/monitors").mock(return_value=httpx.Response(200, json=[]))
        c = HyperpingClient(
            api_key="sk_test",
            user_agent="my-app/2.0",
            retry_config=RetryConfig(max_retries=0),
        )
        c.list_monitors()
        c.close()

        sent_headers = route.calls[0].request.headers
        assert sent_headers["user-agent"] == "my-app/2.0"


# ==================== Task 4: Frozen Response Models ====================


class TestFrozenResponseModels:
    """Response models should be immutable (frozen=True)."""

    def test_monitor_is_frozen(self) -> None:
        m = Monitor(
            uuid="mon_1",
            name="Test",
            url="https://example.com",
            protocol="http",
            down=False,
            paused=False,
        )
        with pytest.raises(Exception):
            m.name = "Changed"  # type: ignore[misc]

    def test_incident_is_frozen(self) -> None:
        i = Incident(
            uuid="inci_1",
            title=LocalizedText(en="Test"),
            type="incident",
            statuspages=["sp_1"],
        )
        with pytest.raises(Exception):
            i.type = "outage"  # type: ignore[misc]

    def test_maintenance_is_frozen(self) -> None:
        m = Maintenance(uuid="mw_1", name="Test Maint")
        with pytest.raises(Exception):
            m.name = "Changed"  # type: ignore[misc]

    def test_monitor_report_is_frozen(self) -> None:
        r = MonitorReport(
            uuid="mon_1",
            name="Test",
            protocol="http",
            period=ReportPeriod(**{"from": "2026-01-01", "to": "2026-01-31"}),
            sla=99.9,
            outages=OutageStats(),
        )
        with pytest.raises(Exception):
            r.sla = 100.0  # type: ignore[misc]

    def test_incident_update_is_frozen(self) -> None:
        u = IncidentUpdate(
            uuid="upd_1",
            date="2026-01-01T00:00:00Z",
            text=LocalizedText(en="update"),
            type="investigating",
        )
        with pytest.raises(Exception):
            u.type = "resolved"  # type: ignore[misc]

    def test_outage_stats_is_frozen(self) -> None:
        o = OutageStats()
        with pytest.raises(Exception):
            o.count = 99  # type: ignore[misc]

    def test_outage_detail_is_frozen(self) -> None:
        d = OutageDetail(
            startDate="2026-01-01T00:00:00Z",
            endDate="2026-01-01T01:00:00Z",
        )
        with pytest.raises(Exception):
            d.start_date = "2026-02-01T00:00:00Z"  # type: ignore[misc]

    def test_report_period_is_frozen(self) -> None:
        rp = ReportPeriod(**{"from": "2026-01-01", "to": "2026-01-31"})
        with pytest.raises(Exception):
            rp.to_date = "2026-02-01"  # type: ignore[misc]

    def test_monitor_list_response_is_frozen(self) -> None:
        r = MonitorListResponse(monitors=[], total=0)
        with pytest.raises(Exception):
            r.total = 5  # type: ignore[misc]

    def test_api_error_response_is_frozen(self) -> None:
        e = APIErrorResponse(error="bad")
        with pytest.raises(Exception):
            e.error = "worse"  # type: ignore[misc]

    def test_localized_text_is_frozen(self) -> None:
        lt = LocalizedText(en="hello")
        with pytest.raises(Exception):
            lt.en = "bye"  # type: ignore[misc]


# ==================== Task 5: py.typed Marker ====================


class TestPackageMetadata:
    """Verify package-level metadata for SDK consumers."""

    def test_py_typed_marker_exists(self) -> None:
        """PEP 561: py.typed marker enables type checking for consumers."""
        marker = Path(__file__).resolve().parents[2] / "src" / "hyperping" / "py.typed"
        assert marker.exists(), f"Missing py.typed at {marker}"


# ==================== Task 6: __all__ Completeness ====================


class TestAllExports:
    """Verify __all__ is complete -- every public name is exported."""

    EXPECTED_EXPORTS = {
        # Client
        "HyperpingClient",
        # Configuration
        "RetryConfig",
        "CircuitBreakerConfig",
        "CircuitBreaker",
        "CircuitState",
        # Exceptions
        "HyperpingAPIError",
        "HyperpingAuthError",
        "HyperpingNotFoundError",
        "HyperpingRateLimitError",
        "HyperpingValidationError",
        # Endpoints — public types only (H5: internal helpers removed from __all__)
        "API_BASE",
        "Endpoint",
        "APIVersion",
        # Monitor models
        "Monitor",
        "MonitorCreate",
        "MonitorUpdate",
        "MonitorReport",
        "MonitorListResponse",
        "MonitorBase",
        # Monitor enums
        "HttpMethod",
        "MonitorFrequency",
        "MonitorTimeout",
        "Region",
        "MonitorProtocol",
        "DnsRecordType",
        "DEFAULT_REGIONS",
        # Monitor helpers
        "RequestHeader",
        # Incident models
        "Incident",
        "IncidentCreate",
        "IncidentUpdate",
        "IncidentUpdateRequest",
        "IncidentType",
        "IncidentUpdateType",
        "AddIncidentUpdateRequest",
        "LocalizedText",
        # Legacy aliases (H5/L3: accessible via __getattr__ + DeprecationWarning)
        "IncidentStatus",
        "IncidentUpdateCreate",
        # Maintenance models
        "Maintenance",
        "MaintenanceCreate",
        "MaintenanceUpdate",
        "NotificationOption",
        # Report models
        "ReportPeriod",
        "OutageDetail",
        "OutageStats",
        # M6: APIErrorResponse is intentionally internal — not in __all__
        # Status Page models
        "StatusPage",
        "StatusPageCreate",
        "StatusPageUpdate",
        "StatusPageSubscriber",
        # Outage models (C5)
        "Outage",
    }

    def test_all_contains_expected_exports(self) -> None:
        actual = set(client_pkg.__all__)
        missing = self.EXPECTED_EXPORTS - actual
        assert not missing, f"Missing from __all__: {missing}"

    def test_all_entries_are_importable(self) -> None:
        for name in client_pkg.__all__:
            assert hasattr(client_pkg, name), f"{name} in __all__ but not importable"

    def test_deprecated_symbols_still_accessible(self) -> None:
        """H5/L3: removed from __all__ but still accessible with DeprecationWarning."""
        import warnings

        deprecated = ["HYPERPING_API_BASE", "API_PATHS", "IncidentStatus", "IncidentUpdateCreate"]
        for name in deprecated:
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                val = getattr(client_pkg, name)
                assert val is not None, f"{name} should be accessible"
                assert any(issubclass(x.category, DeprecationWarning) for x in w), (
                    f"{name} should emit DeprecationWarning"
                )


# ==================== Task 8: Client Lifecycle ====================


class TestClientLifecycle:
    """Client instantiation, context manager, and cleanup."""

    def test_create_with_string_key(self) -> None:
        c = HyperpingClient(api_key="sk_test_123")
        assert repr(c) == f"HyperpingClient(base_url='{API_BASE}')"
        c.close()

    def test_create_with_custom_base_url(self) -> None:
        c = HyperpingClient(api_key="sk_test", base_url="https://custom.api.io/")
        assert c.base_url == "https://custom.api.io"  # trailing slash stripped
        c.close()

    def test_context_manager(self) -> None:
        with HyperpingClient(api_key="sk_test") as c:
            assert repr(c).startswith("HyperpingClient(")
            assert not c._client.is_closed
        assert c._client.is_closed

    @respx.mock
    def test_context_manager_with_request(self) -> None:
        respx.get(f"{API_BASE}/v1/monitors").mock(return_value=httpx.Response(200, json=[]))
        with HyperpingClient(api_key="sk_test", retry_config=RetryConfig(max_retries=0)) as c:
            monitors = c.list_monitors()
            assert monitors == []


# ==================== Task 9: CRUD Operations ====================


class TestMonitorCRUD:
    """Monitor operations from an SDK consumer perspective."""

    @respx.mock
    def test_list_monitors(self, client: HyperpingClient) -> None:
        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "uuid": "mon_1",
                        "name": "Web",
                        "url": "https://web.example.com",
                        "protocol": "http",
                        "http_method": "GET",
                        "check_frequency": 30,
                        "regions": ["london"],
                        "request_headers": [],
                        "expected_status_code": "200",
                        "down": False,
                        "paused": False,
                    },
                ],
            )
        )
        monitors = client.list_monitors()
        assert len(monitors) == 1
        assert monitors[0].uuid == "mon_1"
        assert monitors[0].name == "Web"

    @respx.mock
    def test_get_monitor(self, client: HyperpingClient) -> None:
        respx.get(f"{API_BASE}{Endpoint.MONITORS}/mon_1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "uuid": "mon_1",
                    "name": "Web",
                    "url": "https://web.example.com",
                    "protocol": "http",
                    "http_method": "GET",
                    "check_frequency": 30,
                    "regions": ["london"],
                    "request_headers": [],
                    "expected_status_code": "200",
                    "down": False,
                    "paused": False,
                },
            )
        )
        monitor = client.get_monitor("mon_1")
        assert monitor.uuid == "mon_1"

    @respx.mock
    def test_create_monitor(self, client: HyperpingClient) -> None:
        respx.post(f"{API_BASE}{Endpoint.MONITORS}").mock(
            return_value=httpx.Response(
                201,
                json={
                    "uuid": "mon_new",
                    "name": "New Monitor",
                    "url": "https://new.example.com",
                    "protocol": "http",
                    "http_method": "GET",
                    "check_frequency": 60,
                    "regions": ["london"],
                    "request_headers": [],
                    "expected_status_code": "2xx",
                    "down": False,
                    "paused": False,
                },
            )
        )
        created = client.create_monitor(
            MonitorCreate(name="New Monitor", url="https://new.example.com")
        )
        assert created.uuid == "mon_new"
        assert created.name == "New Monitor"

    @respx.mock
    def test_delete_monitor(self, client: HyperpingClient) -> None:
        respx.delete(f"{API_BASE}{Endpoint.MONITORS}/mon_del").mock(
            return_value=httpx.Response(204)
        )
        client.delete_monitor("mon_del")  # Should not raise

    @respx.mock
    def test_pause_and_resume(self, client: HyperpingClient) -> None:
        monitor_data = {
            "uuid": "mon_1",
            "name": "Web",
            "url": "https://web.example.com",
            "protocol": "http",
            "http_method": "GET",
            "check_frequency": 30,
            "regions": ["london"],
            "request_headers": [],
            "expected_status_code": "200",
            "down": False,
            "paused": False,
        }
        respx.get(f"{API_BASE}{Endpoint.MONITORS}/mon_1").mock(
            return_value=httpx.Response(200, json=monitor_data)
        )
        respx.put(f"{API_BASE}{Endpoint.MONITORS}/mon_1").mock(
            return_value=httpx.Response(200, json={**monitor_data, "paused": True})
        )
        paused = client.pause_monitor("mon_1")
        assert paused.paused is True


class TestIncidentCRUD:
    """Incident operations from an SDK consumer perspective."""

    @respx.mock
    def test_list_incidents(self, client: HyperpingClient) -> None:
        respx.get(f"{API_BASE}{Endpoint.INCIDENTS}").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "uuid": "inci_1",
                        "title": {"en": "Outage"},
                        "type": "incident",
                        "statuspages": ["sp_1"],
                        "updates": [],
                    },
                ],
            )
        )
        incidents = client.list_incidents()
        assert len(incidents) == 1
        assert incidents[0].uuid == "inci_1"

    @respx.mock
    def test_create_incident(self, client: HyperpingClient) -> None:
        respx.post(f"{API_BASE}{Endpoint.INCIDENTS}").mock(
            return_value=httpx.Response(201, json={"uuid": "inci_new", "message": "created"})
        )
        respx.get(f"{API_BASE}{Endpoint.INCIDENTS}/inci_new").mock(
            return_value=httpx.Response(
                200,
                json={
                    "uuid": "inci_new",
                    "title": {"en": "New Incident"},
                    "type": "incident",
                    "statuspages": ["sp_1"],
                    "updates": [],
                },
            )
        )
        created = client.create_incident(
            IncidentCreate(
                title=LocalizedText(en="New Incident"),
                text=LocalizedText(en="Details"),
                statuspages=["sp_1"],
            )
        )
        assert created.uuid == "inci_new"

    @respx.mock
    def test_resolve_incident(self, client: HyperpingClient) -> None:
        respx.post(f"{API_BASE}{Endpoint.INCIDENTS}/inci_1/updates").mock(
            return_value=httpx.Response(200, json={"message": "updated"})
        )
        respx.get(f"{API_BASE}{Endpoint.INCIDENTS}/inci_1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "uuid": "inci_1",
                    "title": {"en": "Test"},
                    "type": "incident",
                    "statuspages": ["sp_1"],
                    "updates": [
                        {
                            "uuid": "upd_1",
                            "date": "2026-01-01T00:00:00Z",
                            "text": {"en": "Resolved"},
                            "type": "resolved",
                        },
                    ],
                },
            )
        )
        resolved = client.resolve_incident("inci_1", "All clear")
        assert resolved.is_resolved

    @respx.mock
    def test_delete_incident(self, client: HyperpingClient) -> None:
        respx.delete(f"{API_BASE}{Endpoint.INCIDENTS}/inci_del").mock(
            return_value=httpx.Response(204)
        )
        client.delete_incident("inci_del")  # Should not raise


class TestMaintenanceCRUD:
    """Maintenance operations from an SDK consumer perspective."""

    @respx.mock
    def test_list_maintenance(self, client: HyperpingClient) -> None:
        respx.get(f"{API_BASE}{Endpoint.MAINTENANCE}").mock(
            return_value=httpx.Response(
                200,
                json={
                    "maintenanceWindows": [
                        {
                            "uuid": "mw_1",
                            "name": "Deploy v2",
                            "start_date": "2026-01-01T00:00:00Z",
                            "end_date": "2026-01-01T01:00:00Z",
                            "monitors": ["mon_1"],
                        },
                    ]
                },
            )
        )
        windows = client.list_maintenance()
        assert len(windows) == 1
        assert windows[0].uuid == "mw_1"

    @respx.mock
    def test_create_maintenance(self, client: HyperpingClient) -> None:
        respx.post(f"{API_BASE}{Endpoint.MAINTENANCE}").mock(
            return_value=httpx.Response(201, json={"uuid": "mw_new"})
        )
        respx.get(f"{API_BASE}{Endpoint.MAINTENANCE}/mw_new").mock(
            return_value=httpx.Response(
                200,
                json={
                    "uuid": "mw_new",
                    "name": "Deploy",
                    "start_date": "2026-01-01T00:00:00Z",
                    "end_date": "2026-01-01T01:00:00Z",
                    "monitors": ["mon_1"],
                },
            )
        )
        created = client.create_maintenance(
            MaintenanceCreate(
                name="Deploy",
                start_date="2026-01-01T00:00:00Z",
                end_date="2026-01-01T01:00:00Z",
                monitors=["mon_1"],
            )
        )
        assert created.uuid == "mw_new"

    @respx.mock
    def test_delete_maintenance(self, client: HyperpingClient) -> None:
        respx.delete(f"{API_BASE}{Endpoint.MAINTENANCE}/mw_del").mock(
            return_value=httpx.Response(204)
        )
        client.delete_maintenance("mw_del")  # Should not raise


class TestOutageOperations:
    """Outage operations from an SDK consumer perspective."""

    @respx.mock
    def test_list_outages(self, client: HyperpingClient) -> None:
        respx.get(f"{API_BASE}{Endpoint.OUTAGES}").mock(
            return_value=httpx.Response(
                200,
                json={"outages": [{"uuid": "out_1", "monitor_uuid": "mon_1", "status": "active"}]},
            )
        )
        outages = client.list_outages()
        assert len(outages) == 1
        assert outages[0].uuid == "out_1"

    @respx.mock
    def test_list_outages_returns_empty_on_404(self, client: HyperpingClient) -> None:
        respx.get(f"{API_BASE}{Endpoint.OUTAGES}").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )
        outages = client.list_outages()
        assert outages == []

    @respx.mock
    def test_acknowledge_outage(self, client: HyperpingClient) -> None:
        respx.post(f"{API_BASE}{Endpoint.OUTAGES}/out_1/acknowledge").mock(
            return_value=httpx.Response(200, json={"status": "acknowledged"})
        )
        result = client.acknowledge_outage("out_1", message="On it")
        assert result["status"] == "acknowledged"

    @respx.mock
    def test_resolve_outage(self, client: HyperpingClient) -> None:
        respx.post(f"{API_BASE}{Endpoint.OUTAGES}/out_1/resolve").mock(
            return_value=httpx.Response(200, json={"status": "resolved"})
        )
        result = client.resolve_outage("out_1", message="Fixed")
        assert result["status"] == "resolved"


class TestReportOperations:
    """Report operations from an SDK consumer perspective."""

    @respx.mock
    def test_get_all_reports(self, client: HyperpingClient) -> None:
        respx.get(f"{API_BASE}{Endpoint.REPORTS}").mock(
            return_value=httpx.Response(
                200,
                json={
                    "period": {"from": "2026-01-01", "to": "2026-01-31"},
                    "monitors": [
                        {
                            "uuid": "mon_1",
                            "name": "Web",
                            "protocol": "http",
                            "sla": 99.95,
                            "outages": {
                                "count": 1,
                                "totalDowntime": 60,
                                "totalDowntimeFormatted": "1m",
                                "longestOutage": 60,
                                "longestOutageFormatted": "1m",
                                "details": [],
                            },
                            "mttr": 60,
                            "mttrFormatted": "1m",
                        },
                    ],
                },
            )
        )
        reports = client.get_all_reports(period="30d")
        assert len(reports) == 1
        assert reports[0].uuid == "mon_1"
        assert reports[0].sla == 99.95

    @respx.mock
    def test_get_monitor_report_found(self, client: HyperpingClient) -> None:
        respx.get(f"{API_BASE}{Endpoint.REPORTS}").mock(
            return_value=httpx.Response(
                200,
                json={
                    "period": {"from": "2026-01-01", "to": "2026-01-31"},
                    "monitors": [
                        {
                            "uuid": "mon_1",
                            "name": "Web",
                            "protocol": "http",
                            "sla": 99.95,
                            "outages": {
                                "count": 0,
                                "totalDowntime": 0,
                                "totalDowntimeFormatted": "0s",
                                "longestOutage": 0,
                                "longestOutageFormatted": "0s",
                                "details": [],
                            },
                            "mttr": 0,
                            "mttrFormatted": "0s",
                        },
                    ],
                },
            )
        )
        report = client.get_monitor_report("mon_1")
        assert report.uuid == "mon_1"

    @respx.mock
    def test_get_monitor_report_not_found(self, client: HyperpingClient) -> None:
        respx.get(f"{API_BASE}{Endpoint.REPORTS}").mock(
            return_value=httpx.Response(
                200,
                json={
                    "period": {"from": "2026-01-01", "to": "2026-01-31"},
                    "monitors": [],
                },
            )
        )
        with pytest.raises(HyperpingNotFoundError):
            client.get_monitor_report("mon_nonexistent")


# ==================== Task 10: Error Handling, Retry, Circuit Breaker ====================


class TestErrorHandling:
    """Verify correct exception types for each HTTP status."""

    @respx.mock
    def test_401_raises_auth_error(self, client: HyperpingClient) -> None:
        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(
            return_value=httpx.Response(401, json={"error": "Unauthorized"})
        )
        with pytest.raises(HyperpingAuthError):
            client.list_monitors()

    @respx.mock
    def test_403_raises_auth_error(self, client: HyperpingClient) -> None:
        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(
            return_value=httpx.Response(403, json={"error": "Forbidden"})
        )
        with pytest.raises(HyperpingAuthError):
            client.list_monitors()

    @respx.mock
    def test_404_raises_not_found(self, client: HyperpingClient) -> None:
        respx.get(f"{API_BASE}{Endpoint.MONITORS}/mon_nope").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )
        with pytest.raises(HyperpingNotFoundError):
            client.get_monitor("mon_nope")

    @respx.mock
    def test_422_raises_validation_error(self, client: HyperpingClient) -> None:
        respx.post(f"{API_BASE}{Endpoint.MONITORS}").mock(
            return_value=httpx.Response(
                422,
                json={
                    "error": "Validation failed",
                    "details": [{"field": "url", "message": "required"}],
                },
            )
        )
        with pytest.raises(HyperpingValidationError) as exc_info:
            client.create_monitor(MonitorCreate(name="Bad", url=""))
        assert len(exc_info.value.validation_errors) == 1

    @respx.mock
    def test_429_raises_rate_limit_error(self, client: HyperpingClient) -> None:
        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(
            return_value=httpx.Response(
                429, json={"error": "Too many requests"}, headers={"Retry-After": "60"}
            )
        )
        with pytest.raises(HyperpingRateLimitError) as exc_info:
            client.list_monitors()
        assert exc_info.value.retry_after == 60

    @respx.mock
    def test_500_raises_api_error(self, client: HyperpingClient) -> None:
        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(
            return_value=httpx.Response(500, json={"error": "Internal server error"})
        )
        with pytest.raises(HyperpingAPIError):
            client.list_monitors()


class TestRetryBehavior:
    """Verify retry logic with respx call counting."""

    @respx.mock
    def test_retries_on_500(self) -> None:
        route = respx.get(f"{API_BASE}{Endpoint.MONITORS}")
        route.side_effect = [
            httpx.Response(500, json={"error": "fail"}),
            httpx.Response(500, json={"error": "fail"}),
            httpx.Response(200, json=[]),
        ]
        c = HyperpingClient(
            api_key="sk_test",
            retry_config=RetryConfig(max_retries=2, initial_delay=0.01, max_delay=0.02),
        )
        monitors = c.list_monitors()
        c.close()
        assert monitors == []
        assert route.call_count == 3

    @respx.mock
    def test_retries_on_429_with_retry_after(self) -> None:
        route = respx.get(f"{API_BASE}{Endpoint.MONITORS}")
        route.side_effect = [
            httpx.Response(429, json={"error": "rate limited"}, headers={"Retry-After": "0"}),
            httpx.Response(200, json=[]),
        ]
        c = HyperpingClient(
            api_key="sk_test",
            retry_config=RetryConfig(max_retries=1, initial_delay=0.01),
        )
        monitors = c.list_monitors()
        c.close()
        assert monitors == []
        assert route.call_count == 2

    @respx.mock
    def test_does_not_retry_on_400(self) -> None:
        route = respx.get(f"{API_BASE}{Endpoint.MONITORS}")
        route.mock(return_value=httpx.Response(400, json={"error": "bad request"}))
        c = HyperpingClient(
            api_key="sk_test",
            retry_config=RetryConfig(max_retries=2, initial_delay=0.01),
        )
        with pytest.raises(HyperpingValidationError):
            c.list_monitors()
        c.close()
        assert route.call_count == 1  # No retries on 400

    @respx.mock
    def test_exhausted_retries_raises(self) -> None:
        route = respx.get(f"{API_BASE}{Endpoint.MONITORS}")
        route.mock(return_value=httpx.Response(500, json={"error": "fail"}))
        c = HyperpingClient(
            api_key="sk_test",
            retry_config=RetryConfig(max_retries=2, initial_delay=0.01, max_delay=0.02),
        )
        with pytest.raises(HyperpingAPIError):
            c.list_monitors()
        c.close()
        assert route.call_count == 3  # 1 initial + 2 retries


class TestCircuitBreakerBehavior:
    """Circuit breaker state transitions."""

    def test_initial_state_is_closed(self) -> None:
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_opens_after_threshold_failures(self) -> None:
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3))
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert not cb.call_allowed()

    def test_half_open_after_recovery_timeout(self) -> None:
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=2, recovery_timeout=0.01))
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        time.sleep(0.02)
        assert cb.call_allowed()
        assert cb.state == CircuitState.HALF_OPEN

    def test_closes_on_success_after_half_open(self) -> None:
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=2, recovery_timeout=0.01))
        cb.record_failure()
        cb.record_failure()

        time.sleep(0.02)
        cb.call_allowed()  # transitions to HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_reopens_on_failure_in_half_open(self) -> None:
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=2, recovery_timeout=0.01))
        cb.record_failure()
        cb.record_failure()

        time.sleep(0.02)
        cb.call_allowed()  # transitions to HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    @respx.mock
    def test_circuit_open_rejects_requests(self) -> None:
        c = HyperpingClient(
            api_key="sk_test",
            retry_config=RetryConfig(max_retries=0),
            circuit_breaker_config=CircuitBreakerConfig(failure_threshold=1),
        )
        respx.get(f"{API_BASE}{Endpoint.MONITORS}").mock(
            return_value=httpx.Response(500, json={"error": "fail"})
        )
        # First call fails and trips circuit
        with pytest.raises(HyperpingAPIError):
            c.list_monitors()
        # Second call rejected by circuit breaker (no HTTP request made)
        with pytest.raises(HyperpingAPIError, match="Circuit breaker OPEN"):
            c.list_monitors()
        c.close()


# ==================== Task 11: Model Validation ====================


class TestModelValidation:
    """Verify Pydantic models validate and parse correctly."""

    def test_monitor_parses_minimal_response(self) -> None:
        m = Monitor(
            uuid="mon_1",
            name="Test",
            url="https://example.com",
            protocol="http",
            down=False,
            paused=False,
        )
        assert m.uuid == "mon_1"
        assert m.protocol == "http"

    def test_monitor_parses_legacy_field_names(self) -> None:
        """API may return legacy field names -- model should remap them."""
        m = Monitor(
            monitorUuid="mon_legacy",
            name="Legacy",
            url="https://legacy.example.com",
            method="POST",
            frequency=60,
            headers={},
            expectedStatus=200,
            down=False,
            paused=False,
        )
        assert m.uuid == "mon_legacy"
        assert m.http_method == "POST"
        assert m.check_frequency == 60

    def test_monitor_ignores_extra_fields(self) -> None:
        """Response may contain undocumented fields -- extra='ignore' handles it."""
        m = Monitor(
            uuid="mon_1",
            name="Test",
            url="https://example.com",
            protocol="http",
            down=False,
            paused=False,
            some_future_field="ignored",
        )
        assert m.uuid == "mon_1"

    def test_incident_required_fields(self) -> None:
        with pytest.raises(PydanticValidationError):
            Incident(uuid="inci_1")  # type: ignore[call-arg]  # missing title, type

    def test_incident_is_resolved_property(self) -> None:
        i = Incident(
            uuid="inci_1",
            title=LocalizedText(en="Test"),
            type="incident",
            statuspages=["sp_1"],
            updates=[
                IncidentUpdate(
                    uuid="u1",
                    date="2026-01-01T00:00:00Z",
                    text=LocalizedText(en="fixed"),
                    type="resolved",
                ),
            ],
        )
        assert i.is_resolved

    def test_incident_not_resolved(self) -> None:
        i = Incident(
            uuid="inci_1",
            title=LocalizedText(en="Test"),
            type="incident",
            statuspages=["sp_1"],
            updates=[],
        )
        assert not i.is_resolved

    def test_maintenance_is_active(self) -> None:
        now = datetime.now(UTC)
        m = Maintenance(
            uuid="mw_1",
            name="Deploy",
            start_date=(now - timedelta(hours=1)).isoformat(),
            end_date=(now + timedelta(hours=1)).isoformat(),
            monitors=["mon_1"],
        )
        assert m.is_active()
        assert m.affects_monitor("mon_1")
        assert not m.affects_monitor("mon_other")

    def test_localized_text_from_string(self) -> None:
        lt = LocalizedText.from_string("Hello")
        assert lt.en == "Hello"
        assert lt.fr is None

    def test_enum_values(self) -> None:
        """Verify key enums have expected members."""
        assert HttpMethod.GET == "GET"
        assert MonitorProtocol.DNS == "dns"
        assert DnsRecordType.A == "A"
        assert Region.PARIS == "paris"
        assert NotificationOption.SCHEDULED == "scheduled"
        assert MonitorFrequency.MINUTES_1 == 60
        assert MonitorTimeout.SECONDS_10 == 10

    def test_monitor_create_excludes_none(self) -> None:
        mc = MonitorCreate(name="Test", url="https://example.com", check_frequency=60)
        dumped = mc.model_dump(exclude_none=True)
        assert "name" in dumped
        assert "dns_record_type" not in dumped

    def test_request_models_are_mutable(self) -> None:
        """Request models should allow mutation for incremental construction."""
        mc = MonitorCreate(name="Initial", url="https://example.com")
        mc.name = "Updated"
        assert mc.name == "Updated"

        maint = MaintenanceCreate(
            name="MW",
            start_date="2026-01-01T00:00:00Z",
            end_date="2026-01-01T01:00:00Z",
            monitors=["mon_1"],
        )
        maint.name = "Updated MW"
        assert maint.name == "Updated MW"

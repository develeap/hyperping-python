"""Tests for maintenance window models and API methods."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from hyperping.client import HyperpingClient
from hyperping.endpoints import API_BASE, Endpoint
from hyperping.exceptions import HyperpingNotFoundError, HyperpingValidationError
from hyperping.models import (
    Maintenance,
    MaintenanceCreate,
    MaintenanceUpdate,
)


class TestMaintenanceModels:
    """Tests for maintenance models (v1 API)."""

    def test_maintenance_create(self) -> None:
        """Test creating maintenance window."""
        start = datetime.now(UTC) + timedelta(hours=1)
        end = start + timedelta(hours=2)

        maintenance = MaintenanceCreate(
            name="Scheduled Maintenance",
            start_date=start.isoformat().replace("+00:00", "Z"),
            end_date=end.isoformat().replace("+00:00", "Z"),
            monitors=["mon_123"],
            statuspages=["sp_test"],
        )
        assert maintenance.name == "Scheduled Maintenance"
        assert maintenance.monitors == ["mon_123"]

    def test_maintenance_is_active_during_window(self) -> None:
        """Test is_active during maintenance window."""
        now = datetime.now(UTC)
        data = {
            "uuid": "mw_123",
            "name": "Active Maintenance",
            "start_date": (now - timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
            "end_date": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
            "monitors": ["mon_123"],
            "statuspages": [],
        }
        maintenance = Maintenance.model_validate(data)
        assert maintenance.is_active() is True

    def test_maintenance_is_active_outside_window(self) -> None:
        """Test is_active outside maintenance window."""
        now = datetime.now(UTC)
        data = {
            "uuid": "mw_456",
            "name": "Future Maintenance",
            "start_date": (now + timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
            "end_date": (now + timedelta(hours=4)).isoformat().replace("+00:00", "Z"),
            "monitors": [],
            "statuspages": [],
        }
        maintenance = Maintenance.model_validate(data)
        assert maintenance.is_active() is False

    def test_maintenance_affects_monitor(self) -> None:
        """Test affects_monitor method."""
        data = {
            "uuid": "mw_789",
            "name": "Test",
            "start_date": "2024-01-20T00:00:00Z",
            "end_date": "2024-01-20T02:00:00Z",
            "monitors": ["mon_aaa", "mon_bbb"],
            "statuspages": [],
        }
        maintenance = Maintenance.model_validate(data)
        assert maintenance.affects_monitor("mon_aaa") is True
        assert maintenance.affects_monitor("mon_ccc") is False

    def test_maintenance_frozen(self) -> None:
        """Test maintenance model is immutable."""
        m = Maintenance(uuid="mw_1", name="Test")
        with pytest.raises(Exception):
            m.name = "Changed"  # type: ignore[misc]

    def test_maintenance_empty_localized_text_coercion(self) -> None:
        """Test that empty dict for title/text is coerced to None."""
        data = {
            "uuid": "mw_1",
            "name": "Test",
            "title": {},
            "text": {},
            "monitors": [],
            "statuspages": [],
        }
        m = Maintenance.model_validate(data)
        assert m.title is None
        assert m.text is None


class TestMaintenanceAPIClient:
    """Tests for maintenance API operations."""

    @respx.mock
    def test_list_maintenance(self, client: HyperpingClient) -> None:
        """Test listing maintenance windows."""
        mock_response = {
            "maintenanceWindows": [
                {
                    "uuid": "mw_1",
                    "name": "Deploy v2",
                    "start_date": "2024-01-20T00:00:00Z",
                    "end_date": "2024-01-20T02:00:00Z",
                    "monitors": ["mon_123"],
                    "statuspages": [],
                },
                {
                    "uuid": "mw_2",
                    "name": "DB Upgrade",
                    "start_date": "2024-01-21T00:00:00Z",
                    "end_date": "2024-01-21T04:00:00Z",
                    "monitors": ["mon_456"],
                    "statuspages": [],
                },
            ]
        }
        respx.get(f"{API_BASE}{Endpoint.MAINTENANCE}").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        windows = client.list_maintenance()
        assert len(windows) == 2
        assert windows[0].uuid == "mw_1"
        assert windows[1].uuid == "mw_2"

    @respx.mock
    def test_list_maintenance_empty(self, client: HyperpingClient) -> None:
        """Test listing with no maintenance windows."""
        respx.get(f"{API_BASE}{Endpoint.MAINTENANCE}").mock(
            return_value=httpx.Response(200, json={"maintenanceWindows": []})
        )
        windows = client.list_maintenance()
        assert windows == []

    @respx.mock
    def test_get_maintenance(self, client: HyperpingClient) -> None:
        """Test getting a single maintenance window."""
        mock_response = {
            "uuid": "mw_123",
            "name": "Test Maintenance",
            "start_date": "2024-01-20T00:00:00Z",
            "end_date": "2024-01-20T02:00:00Z",
            "monitors": ["mon_1"],
            "statuspages": [],
        }
        respx.get(f"{API_BASE}{Endpoint.MAINTENANCE}/mw_123").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        mw = client.get_maintenance("mw_123")
        assert mw.uuid == "mw_123"
        assert mw.name == "Test Maintenance"

    @respx.mock
    def test_get_maintenance_not_found(self, client: HyperpingClient) -> None:
        """Test getting a non-existent maintenance window."""
        respx.get(f"{API_BASE}{Endpoint.MAINTENANCE}/mw_nope").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )
        with pytest.raises(HyperpingNotFoundError):
            client.get_maintenance("mw_nope")

    @respx.mock
    def test_create_maintenance(self, client: HyperpingClient) -> None:
        """Test creating a maintenance window."""
        create_response = {"uuid": "mw_new"}
        get_response = {
            "uuid": "mw_new",
            "name": "New Maintenance",
            "start_date": "2024-01-20T00:00:00Z",
            "end_date": "2024-01-20T02:00:00Z",
            "monitors": ["mon_1"],
            "statuspages": [],
        }
        respx.post(f"{API_BASE}{Endpoint.MAINTENANCE}").mock(
            return_value=httpx.Response(201, json=create_response)
        )
        respx.get(f"{API_BASE}{Endpoint.MAINTENANCE}/mw_new").mock(
            return_value=httpx.Response(200, json=get_response)
        )

        mw = client.create_maintenance(
            MaintenanceCreate(
                name="New Maintenance",
                start_date="2024-01-20T00:00:00Z",
                end_date="2024-01-20T02:00:00Z",
                monitors=["mon_1"],
            )
        )
        assert mw.uuid == "mw_new"
        assert mw.name == "New Maintenance"

    def test_create_maintenance_rejects_too_many_statuspages(
        self, client: HyperpingClient
    ) -> None:
        """>51 status pages must raise, not silently phantom-fail.

        Hyperping's API accepts the create (returns a uuid) but never persists
        the window above the limit; the client guards against it before the
        POST, so no HTTP call is made.
        """
        with pytest.raises(HyperpingValidationError, match="at most 51 status pages"):
            client.create_maintenance(
                MaintenanceCreate(
                    name="Too many pages",
                    start_date="2024-01-20T00:00:00Z",
                    end_date="2024-01-20T02:00:00Z",
                    monitors=["mon_1"],
                    statuspages=[f"sp_{i}" for i in range(52)],
                )
            )

    @respx.mock
    def test_create_maintenance_windows_chunks_statuspages(
        self, client: HyperpingClient
    ) -> None:
        """>51 status pages are split across multiple windows of <=chunk_size."""
        import json

        create_route = respx.post(f"{API_BASE}{Endpoint.MAINTENANCE}").mock(
            return_value=httpx.Response(201, json={"uuid": "mw_x"})
        )
        respx.get(f"{API_BASE}{Endpoint.MAINTENANCE}/mw_x").mock(
            return_value=httpx.Response(
                200,
                json={
                    "uuid": "mw_x",
                    "name": "Big",
                    "start_date": "2024-01-20T00:00:00Z",
                    "end_date": "2024-01-20T02:00:00Z",
                    "monitors": ["mon_1"],
                    "statuspages": [],
                },
            )
        )
        windows = client.create_maintenance_windows(
            MaintenanceCreate(
                name="Big",
                start_date="2024-01-20T00:00:00Z",
                end_date="2024-01-20T02:00:00Z",
                monitors=["mon_1"],
                statuspages=[f"sp_{i}" for i in range(60)],
            )
        )
        assert len(windows) == 2
        assert create_route.call_count == 2
        sizes = [len(json.loads(c.request.content)["statuspages"]) for c in create_route.calls]
        assert sizes == [51, 9]  # every chunk within the 51-page limit

    def test_create_maintenance_windows_rejects_bad_chunk_size(
        self, client: HyperpingClient
    ) -> None:
        """chunk_size outside 1..51 is rejected before any HTTP call."""
        with pytest.raises(HyperpingValidationError, match="chunk_size"):
            client.create_maintenance_windows(
                MaintenanceCreate(
                    name="X",
                    start_date="2024-01-20T00:00:00Z",
                    end_date="2024-01-20T02:00:00Z",
                    monitors=["mon_1"],
                    statuspages=["sp_1"],
                ),
                chunk_size=99,
            )

    @respx.mock
    def test_update_maintenance(self, client: HyperpingClient) -> None:
        """Test updating a maintenance window (read-modify-write)."""
        current = {
            "uuid": "mw_123",
            "name": "Old Name",
            "start_date": "2024-01-20T00:00:00Z",
            "end_date": "2024-01-20T02:00:00Z",
            "monitors": ["mon_1"],
            "statuspages": [],
        }
        updated = {**current, "name": "New Name"}
        respx.get(f"{API_BASE}{Endpoint.MAINTENANCE}/mw_123").mock(
            return_value=httpx.Response(200, json=current)
        )
        respx.put(f"{API_BASE}{Endpoint.MAINTENANCE}/mw_123").mock(
            return_value=httpx.Response(200, json=updated)
        )

        result = client.update_maintenance("mw_123", MaintenanceUpdate(name="New Name"))
        assert result.name == "New Name"

    @respx.mock
    def test_delete_maintenance(self, client: HyperpingClient) -> None:
        """Test deleting a maintenance window."""
        respx.delete(f"{API_BASE}{Endpoint.MAINTENANCE}/mw_del").mock(
            return_value=httpx.Response(204)
        )
        client.delete_maintenance("mw_del")  # Should not raise

    @respx.mock
    def test_get_active_maintenance(self, client: HyperpingClient) -> None:
        """Test getting active maintenance windows."""
        now = datetime.now(UTC)
        mock_response = {
            "maintenanceWindows": [
                {
                    "uuid": "mw_active",
                    "name": "Active",
                    "start_date": (now - timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
                    "end_date": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
                    "monitors": ["mon_1"],
                    "statuspages": [],
                },
                {
                    "uuid": "mw_future",
                    "name": "Future",
                    "start_date": (now + timedelta(hours=5)).isoformat().replace("+00:00", "Z"),
                    "end_date": (now + timedelta(hours=7)).isoformat().replace("+00:00", "Z"),
                    "monitors": ["mon_2"],
                    "statuspages": [],
                },
            ]
        }
        respx.get(f"{API_BASE}{Endpoint.MAINTENANCE}").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        active = client.get_active_maintenance()
        assert len(active) == 1
        assert active[0].uuid == "mw_active"

    @respx.mock
    def test_is_monitor_in_maintenance(self, client: HyperpingClient) -> None:
        """Test checking if a monitor is in active maintenance."""
        now = datetime.now(UTC)
        mock_response = {
            "maintenanceWindows": [
                {
                    "uuid": "mw_active",
                    "name": "Active",
                    "start_date": (now - timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
                    "end_date": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
                    "monitors": ["mon_1"],
                    "statuspages": [],
                },
            ]
        }
        respx.get(f"{API_BASE}{Endpoint.MAINTENANCE}").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        assert client.is_monitor_in_maintenance("mon_1") is True
        assert client.is_monitor_in_maintenance("mon_other") is False

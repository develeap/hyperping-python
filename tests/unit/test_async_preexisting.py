"""Tests for pre-existing async mixins: healthchecks, maintenance, incidents.

These bring coverage of existing async code that was previously untested.
"""

import httpx
import pytest
import pytest_asyncio
import respx

from hyperping._async_client import AsyncHyperpingClient
from hyperping.client import RetryConfig
from hyperping.endpoints import API_BASE, Endpoint
from hyperping.exceptions import HyperpingNotFoundError


@pytest_asyncio.fixture
async def async_client():
    """Async client with retries disabled."""
    client = AsyncHyperpingClient(
        api_key="sk_test_key",
        base_url=API_BASE,
        retry_config=RetryConfig(max_retries=0),
    )
    yield client
    await client.close()


# ==================== Async Healthchecks ====================


class TestAsyncHealthchecks:
    @respx.mock
    @pytest.mark.asyncio
    async def test_list_healthchecks(self, async_client):
        respx.get(f"{API_BASE}{Endpoint.HEALTHCHECKS}").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "uuid": "hc_1",
                        "name": "Cron Job",
                        "period": 300,
                        "grace": 60,
                    }
                ],
            )
        )
        result = await async_client.list_healthchecks()
        assert len(result) == 1
        assert result[0].uuid == "hc_1"

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_healthcheck(self, async_client):
        respx.get(f"{API_BASE}{Endpoint.HEALTHCHECKS}/hc_1").mock(
            return_value=httpx.Response(
                200,
                json={"uuid": "hc_1", "name": "Cron", "period": 300, "grace": 60},
            )
        )
        result = await async_client.get_healthcheck("hc_1")
        assert result.name == "Cron"

    @respx.mock
    @pytest.mark.asyncio
    async def test_create_healthcheck(self, async_client):
        from hyperping.models import HealthcheckCreate

        respx.post(f"{API_BASE}{Endpoint.HEALTHCHECKS}").mock(
            return_value=httpx.Response(
                201,
                json={"uuid": "hc_new", "name": "New HC", "period": 600, "grace": 120},
            )
        )
        hc = HealthcheckCreate(name="New HC", period=600, grace=120)
        result = await async_client.create_healthcheck(hc)
        assert result.uuid == "hc_new"

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_healthchecks_from_dict_key(self, async_client):
        """Handles API response wrapped in a 'healthchecks' key."""
        respx.get(f"{API_BASE}{Endpoint.HEALTHCHECKS}").mock(
            return_value=httpx.Response(
                200,
                json={
                    "healthchecks": [
                        {"uuid": "hc_d1", "name": "Dict HC", "period": 300, "grace": 60}
                    ]
                },
            )
        )
        result = await async_client.list_healthchecks()
        assert len(result) == 1
        assert result[0].uuid == "hc_d1"

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_healthchecks_unexpected_shape_returns_empty(self, async_client):
        """Returns empty list when response is neither list nor dict with key."""
        respx.get(f"{API_BASE}{Endpoint.HEALTHCHECKS}").mock(
            return_value=httpx.Response(200, json={"other_key": "value"})
        )
        result = await async_client.list_healthchecks()
        assert result == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_healthchecks_404_returns_empty(self, async_client):
        """Returns empty list on 404 (HyperpingNotFoundError is caught)."""
        respx.get(f"{API_BASE}{Endpoint.HEALTHCHECKS}").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )
        result = await async_client.list_healthchecks()
        assert result == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_update_healthcheck(self, async_client):
        """update_healthcheck sends PUT and returns updated Healthcheck."""
        from hyperping.models import HealthcheckUpdate

        respx.put(f"{API_BASE}{Endpoint.HEALTHCHECKS}/hc_1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "uuid": "hc_1",
                    "name": "Updated HC",
                    "period": 600,
                    "grace": 120,
                },
            )
        )
        update = HealthcheckUpdate(name="Updated HC", period=600)
        result = await async_client.update_healthcheck("hc_1", update)
        assert result.uuid == "hc_1"
        assert result.name == "Updated HC"
        assert result.period == 600

    @respx.mock
    @pytest.mark.asyncio
    async def test_delete_healthcheck(self, async_client):
        respx.delete(f"{API_BASE}{Endpoint.HEALTHCHECKS}/hc_1").mock(
            return_value=httpx.Response(204)
        )
        await async_client.delete_healthcheck("hc_1")

    @respx.mock
    @pytest.mark.asyncio
    async def test_pause_healthcheck(self, async_client):
        respx.post(f"{API_BASE}{Endpoint.HEALTHCHECKS}/hc_1/pause").mock(
            return_value=httpx.Response(
                200,
                json={
                    "uuid": "hc_1",
                    "name": "HC",
                    "period": 300,
                    "grace": 60,
                    "isPaused": True,
                },
            )
        )
        result = await async_client.pause_healthcheck("hc_1")
        assert result.uuid == "hc_1"

    @respx.mock
    @pytest.mark.asyncio
    async def test_resume_healthcheck(self, async_client):
        respx.post(f"{API_BASE}{Endpoint.HEALTHCHECKS}/hc_1/resume").mock(
            return_value=httpx.Response(
                200,
                json={
                    "uuid": "hc_1",
                    "name": "HC",
                    "period": 300,
                    "grace": 60,
                    "isPaused": False,
                },
            )
        )
        result = await async_client.resume_healthcheck("hc_1")
        assert result.uuid == "hc_1"


# ==================== Async Maintenance ====================


class TestAsyncMaintenance:
    @respx.mock
    @pytest.mark.asyncio
    async def test_list_maintenance(self, async_client):
        respx.get(f"{API_BASE}{Endpoint.MAINTENANCE}").mock(
            return_value=httpx.Response(
                200,
                json={
                    "maintenanceWindows": [
                        {
                            "uuid": "mw_1",
                            "name": "Upgrade",
                            "start_date": "2026-01-01T00:00:00Z",
                            "end_date": "2026-01-01T02:00:00Z",
                            "monitors": [],
                        }
                    ]
                },
            )
        )
        result = await async_client.list_maintenance()
        assert len(result) == 1
        assert result[0].uuid == "mw_1"

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_maintenance(self, async_client):
        respx.get(f"{API_BASE}{Endpoint.MAINTENANCE}/mw_1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "uuid": "mw_1",
                    "name": "Upgrade",
                    "start_date": "2026-01-01T00:00:00Z",
                    "end_date": "2026-01-01T02:00:00Z",
                    "monitors": [],
                },
            )
        )
        result = await async_client.get_maintenance("mw_1")
        assert result.name == "Upgrade"

    @respx.mock
    @pytest.mark.asyncio
    async def test_create_maintenance(self, async_client):
        from hyperping.models import MaintenanceCreate

        respx.post(f"{API_BASE}{Endpoint.MAINTENANCE}").mock(
            return_value=httpx.Response(
                201,
                json={
                    "uuid": "mw_new",
                    "name": "Deploy",
                    "start_date": "2026-02-01T00:00:00Z",
                    "end_date": "2026-02-01T02:00:00Z",
                    "monitors": ["mon_1"],
                },
            )
        )
        mw = MaintenanceCreate(
            name="Deploy",
            start_date="2026-02-01T00:00:00Z",
            end_date="2026-02-01T02:00:00Z",
            monitors=["mon_1"],
        )
        result = await async_client.create_maintenance(mw)
        assert result.uuid == "mw_new"

    @respx.mock
    @pytest.mark.asyncio
    async def test_delete_maintenance(self, async_client):
        respx.delete(f"{API_BASE}{Endpoint.MAINTENANCE}/mw_1").mock(
            return_value=httpx.Response(204)
        )
        await async_client.delete_maintenance("mw_1")

    @respx.mock
    @pytest.mark.asyncio
    async def test_update_maintenance(self, async_client):
        from hyperping.models import MaintenanceUpdate

        respx.get(f"{API_BASE}{Endpoint.MAINTENANCE}/mw_1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "uuid": "mw_1",
                    "name": "Old Name",
                    "start_date": "2026-01-01T00:00:00Z",
                    "end_date": "2026-01-01T02:00:00Z",
                    "monitors": ["mon_1"],
                },
            )
        )
        respx.put(f"{API_BASE}{Endpoint.MAINTENANCE}/mw_1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "uuid": "mw_1",
                    "name": "New Name",
                    "start_date": "2026-01-01T00:00:00Z",
                    "end_date": "2026-01-01T02:00:00Z",
                    "monitors": ["mon_1"],
                },
            )
        )
        result = await async_client.update_maintenance("mw_1", MaintenanceUpdate(name="New Name"))
        assert result.name == "New Name"

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_maintenance_with_status_filter(self, async_client):
        """list_maintenance passes status query param when provided (covers line 42)."""
        route = respx.get(f"{API_BASE}{Endpoint.MAINTENANCE}").mock(
            return_value=httpx.Response(
                200,
                json={
                    "maintenanceWindows": [
                        {
                            "uuid": "mw_active",
                            "name": "Active MW",
                            "start_date": "2026-01-01T00:00:00Z",
                            "end_date": "2026-12-31T23:59:59Z",
                            "monitors": [],
                        }
                    ]
                },
            )
        )
        result = await async_client.list_maintenance(status="active")
        assert len(result) == 1
        assert result[0].uuid == "mw_active"
        assert route.calls[0].request.url.params.get("status") == "active"

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_maintenance_fallback_maintenance_key(self, async_client):
        """list_maintenance uses 'maintenance' key as fallback (covers line 48)."""
        respx.get(f"{API_BASE}{Endpoint.MAINTENANCE}").mock(
            return_value=httpx.Response(
                200,
                json={
                    "maintenance": [
                        {
                            "uuid": "mw_fb",
                            "name": "Fallback MW",
                            "start_date": "2026-01-01T00:00:00Z",
                            "end_date": "2026-01-01T02:00:00Z",
                            "monitors": [],
                        }
                    ]
                },
            )
        )
        result = await async_client.list_maintenance()
        assert len(result) == 1
        assert result[0].uuid == "mw_fb"

    @respx.mock
    @pytest.mark.asyncio
    async def test_create_maintenance_uuid_only_response(self, async_client):
        """create_maintenance re-fetches when API returns uuid-only (covers line 91)."""
        from hyperping.models import MaintenanceCreate

        respx.post(f"{API_BASE}{Endpoint.MAINTENANCE}").mock(
            return_value=httpx.Response(201, json={"uuid": "mw_refetch"})
        )
        respx.get(f"{API_BASE}{Endpoint.MAINTENANCE}/mw_refetch").mock(
            return_value=httpx.Response(
                200,
                json={
                    "uuid": "mw_refetch",
                    "name": "Refetched MW",
                    "start_date": "2026-03-01T00:00:00Z",
                    "end_date": "2026-03-01T02:00:00Z",
                    "monitors": ["mon_1"],
                },
            )
        )
        mw = MaintenanceCreate(
            name="Refetched MW",
            start_date="2026-03-01T00:00:00Z",
            end_date="2026-03-01T02:00:00Z",
            monitors=["mon_1"],
        )
        result = await async_client.create_maintenance(mw)
        assert result.uuid == "mw_refetch"
        assert result.name == "Refetched MW"

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_active_maintenance(self, async_client):
        """get_active_maintenance filters to currently active windows (covers lines 153-155)."""
        respx.get(f"{API_BASE}{Endpoint.MAINTENANCE}").mock(
            return_value=httpx.Response(
                200,
                json={
                    "maintenanceWindows": [
                        {
                            "uuid": "mw_active",
                            "name": "Active Now",
                            "start_date": "2020-01-01T00:00:00Z",
                            "end_date": "2030-12-31T23:59:59Z",
                            "monitors": ["mon_1"],
                        },
                        {
                            "uuid": "mw_past",
                            "name": "Past MW",
                            "start_date": "2020-01-01T00:00:00Z",
                            "end_date": "2020-01-02T00:00:00Z",
                            "monitors": ["mon_2"],
                        },
                    ]
                },
            )
        )
        result = await async_client.get_active_maintenance()
        assert len(result) == 1
        assert result[0].uuid == "mw_active"

    @respx.mock
    @pytest.mark.asyncio
    async def test_is_monitor_in_maintenance(self, async_client):
        """is_monitor_in_maintenance returns True for monitored monitor (covers lines 170-171)."""
        respx.get(f"{API_BASE}{Endpoint.MAINTENANCE}").mock(
            return_value=httpx.Response(
                200,
                json={
                    "maintenanceWindows": [
                        {
                            "uuid": "mw_active",
                            "name": "Active MW",
                            "start_date": "2020-01-01T00:00:00Z",
                            "end_date": "2030-12-31T23:59:59Z",
                            "monitors": ["mon_in_mw"],
                        }
                    ]
                },
            )
        )
        assert await async_client.is_monitor_in_maintenance("mon_in_mw") is True

    @respx.mock
    @pytest.mark.asyncio
    async def test_is_monitor_not_in_maintenance(self, async_client):
        """is_monitor_in_maintenance returns False for unaffected monitor."""
        respx.get(f"{API_BASE}{Endpoint.MAINTENANCE}").mock(
            return_value=httpx.Response(
                200,
                json={"maintenanceWindows": []},
            )
        )
        assert await async_client.is_monitor_in_maintenance("mon_other") is False


# ==================== Async Outages ====================


class TestAsyncOutages:
    @respx.mock
    @pytest.mark.asyncio
    async def test_list_outages_404_returns_empty(self, async_client):
        """list_outages returns empty list on 404 (covers line 69 area)."""
        respx.get(f"{API_BASE}{Endpoint.OUTAGES}").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )
        result = await async_client.list_outages()
        assert result == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_outages_with_type_filter(self, async_client):
        """list_outages passes type query param when outage_type is not 'all' (covers line 69)."""
        route = respx.get(f"{API_BASE}{Endpoint.OUTAGES}").mock(
            return_value=httpx.Response(
                200,
                json={
                    "outages": [
                        {
                            "uuid": "out_manual",
                            "monitorUuid": "mon_1",
                            "acknowledged": False,
                            "resolved": False,
                        }
                    ]
                },
            )
        )
        result = await async_client.list_outages(page=0, outage_type="manual")
        assert len(result) == 1
        assert result[0].uuid == "out_manual"
        assert route.calls[0].request.url.params.get("type") == "manual"

    @respx.mock
    @pytest.mark.asyncio
    async def test_unacknowledge_outage(self, async_client):
        """unacknowledge_outage returns OutageAction (covers lines 160-162)."""
        respx.post(f"{API_BASE}{Endpoint.OUTAGES}/out_1/unacknowledge").mock(
            return_value=httpx.Response(200, json={"status": "unacknowledged"})
        )
        result = await async_client.unacknowledge_outage("out_1")
        assert result.status == "unacknowledged"

    @respx.mock
    @pytest.mark.asyncio
    async def test_delete_outage(self, async_client):
        """delete_outage sends DELETE request (covers lines 173-174)."""
        respx.delete(f"{API_BASE}{Endpoint.OUTAGES}/out_1").mock(return_value=httpx.Response(204))
        await async_client.delete_outage("out_1")

    @respx.mock
    @pytest.mark.asyncio
    async def test_create_outage(self, async_client):
        """create_outage sends POST and returns Outage (covers lines 189-191)."""
        respx.post(f"{API_BASE}{Endpoint.OUTAGES}").mock(
            return_value=httpx.Response(
                201,
                json={
                    "uuid": "out_new",
                    "monitorUuid": "mon_1",
                    "startedAt": "2026-04-17T10:00:00Z",
                    "acknowledged": False,
                    "resolved": False,
                },
            )
        )
        result = await async_client.create_outage("mon_1")
        assert result.uuid == "out_new"
        assert result.monitor_uuid == "mon_1"

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_outage(self, async_client):
        """get_outage fetches single outage by ID (covers lines 205-207)."""
        respx.get(f"{API_BASE}{Endpoint.OUTAGES}/out_1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "uuid": "out_1",
                    "monitorUuid": "mon_1",
                    "startedAt": "2026-04-17T10:00:00Z",
                    "acknowledged": True,
                    "resolved": False,
                },
            )
        )
        result = await async_client.get_outage("out_1")
        assert result.uuid == "out_1"
        assert result.acknowledged is True


# ==================== Async Incidents ====================


class TestAsyncIncidents:
    @respx.mock
    @pytest.mark.asyncio
    async def test_list_incidents(self, async_client):
        respx.get(f"{API_BASE}{Endpoint.INCIDENTS}").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "uuid": "inc_1",
                        "title": {"en": "Outage"},
                        "type": "outage",
                        "affected_components": [],
                        "statuspages": ["sp_1"],
                        "updates": [],
                    }
                ],
            )
        )
        result = await async_client.list_incidents()
        assert len(result) == 1
        assert result[0].uuid == "inc_1"

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_incident(self, async_client):
        respx.get(f"{API_BASE}{Endpoint.INCIDENTS}/inc_1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "uuid": "inc_1",
                    "title": {"en": "Outage"},
                    "type": "outage",
                    "affected_components": [],
                    "statuspages": ["sp_1"],
                    "updates": [],
                },
            )
        )
        result = await async_client.get_incident("inc_1")
        assert result.title_en == "Outage"

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_incidents_with_status_filter(self, async_client):
        """list_incidents passes status query param when provided."""
        respx.get(f"{API_BASE}{Endpoint.INCIDENTS}").mock(return_value=httpx.Response(200, json=[]))
        result = await async_client.list_incidents(status="investigating")
        assert result == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_create_incident(self, async_client):
        """create_incident POSTs and re-fetches the full incident when API returns uuid."""
        from hyperping.models import IncidentCreate, IncidentType, LocalizedText

        create_response = {"message": "Incident created", "uuid": "inc_new"}
        full_response = {
            "uuid": "inc_new",
            "title": {"en": "New Incident"},
            "type": "incident",
            "affected_components": [],
            "statuspages": ["sp_1"],
            "updates": [],
        }
        respx.post(f"{API_BASE}{Endpoint.INCIDENTS}").mock(
            return_value=httpx.Response(201, json=create_response)
        )
        respx.get(f"{API_BASE}{Endpoint.INCIDENTS}/inc_new").mock(
            return_value=httpx.Response(200, json=full_response)
        )
        incident = IncidentCreate(
            title=LocalizedText(en="New Incident"),
            text=LocalizedText(en="Body"),
            type=IncidentType.INCIDENT,
            statuspages=["sp_1"],
        )
        result = await async_client.create_incident(incident)
        assert result.uuid == "inc_new"
        assert result.title_en == "New Incident"

    @respx.mock
    @pytest.mark.asyncio
    async def test_create_incident_full_response(self, async_client):
        """create_incident returns directly when API returns full incident object."""
        from hyperping.models import IncidentCreate, IncidentType, LocalizedText

        full_response = {
            "uuid": "inc_full",
            "title": {"en": "Full Incident"},
            "type": "incident",
            "affected_components": [],
            "statuspages": ["sp_1"],
            "updates": [],
        }
        respx.post(f"{API_BASE}{Endpoint.INCIDENTS}").mock(
            return_value=httpx.Response(201, json=full_response)
        )
        incident = IncidentCreate(
            title=LocalizedText(en="Full Incident"),
            text=LocalizedText(en="Body"),
            type=IncidentType.INCIDENT,
            statuspages=["sp_1"],
        )
        result = await async_client.create_incident(incident)
        assert result.uuid == "inc_full"

    @respx.mock
    @pytest.mark.asyncio
    async def test_update_incident(self, async_client):
        """update_incident sends PUT and returns updated Incident."""
        from hyperping.models import IncidentUpdateRequest, LocalizedText

        updated_response = {
            "uuid": "inc_upd",
            "title": {"en": "Updated Title"},
            "type": "incident",
            "affected_components": [],
            "statuspages": ["sp_1"],
            "updates": [],
        }
        respx.put(f"{API_BASE}{Endpoint.INCIDENTS}/inc_upd").mock(
            return_value=httpx.Response(200, json=updated_response)
        )
        result = await async_client.update_incident(
            "inc_upd",
            IncidentUpdateRequest(title=LocalizedText(en="Updated Title")),
        )
        assert result.uuid == "inc_upd"
        assert result.title_en == "Updated Title"

    @respx.mock
    @pytest.mark.asyncio
    async def test_resolve_incident(self, async_client):
        # resolve_incident calls add_incident_update which POSTs then GETs
        respx.post(f"{API_BASE}{Endpoint.INCIDENTS}/inc_1/updates").mock(
            return_value=httpx.Response(200, json={"uuid": "u1", "message": "Update added"})
        )
        respx.get(f"{API_BASE}{Endpoint.INCIDENTS}/inc_1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "uuid": "inc_1",
                    "title": {"en": "Outage"},
                    "type": "outage",
                    "affected_components": [],
                    "statuspages": ["sp_1"],
                    "updates": [
                        {
                            "uuid": "u1",
                            "type": "resolved",
                            "date": "2026-01-01T01:00:00Z",
                            "text": {"en": "Fixed"},
                        }
                    ],
                },
            )
        )
        result = await async_client.resolve_incident("inc_1", message="Fixed")
        assert result.uuid == "inc_1"

    @respx.mock
    @pytest.mark.asyncio
    async def test_delete_incident(self, async_client):
        respx.delete(f"{API_BASE}{Endpoint.INCIDENTS}/inc_1").mock(return_value=httpx.Response(204))
        await async_client.delete_incident("inc_1")

    @respx.mock
    @pytest.mark.asyncio
    async def test_incident_not_found(self, async_client):
        respx.get(f"{API_BASE}{Endpoint.INCIDENTS}/inc_x").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )
        with pytest.raises(HyperpingNotFoundError):
            await async_client.get_incident("inc_x")


class TestAsyncBatchChunking:
    """Async chunking helpers added in 1.9.0."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_create_maintenance_windows_chunks(self, async_client):
        from hyperping.models import MaintenanceCreate

        route = respx.post(f"{API_BASE}{Endpoint.MAINTENANCE}").mock(
            return_value=httpx.Response(201, json={"uuid": "mw_x"})
        )
        respx.get(f"{API_BASE}{Endpoint.MAINTENANCE}/mw_x").mock(
            return_value=httpx.Response(
                200,
                json={
                    "uuid": "mw_x",
                    "name": "B",
                    "start_date": "2024-01-20T00:00:00Z",
                    "end_date": "2024-01-20T02:00:00Z",
                    "monitors": ["mon_1"],
                    "statuspages": [],
                },
            )
        )
        result = await async_client.create_maintenance_windows(
            MaintenanceCreate(
                name="B",
                start_date="2024-01-20T00:00:00Z",
                end_date="2024-01-20T02:00:00Z",
                monitors=["mon_1"],
                statuspages=[f"sp_{i}" for i in range(60)],
            )
        )
        assert len(result) == 2
        assert route.call_count == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_create_incidents_chunks(self, async_client):
        from hyperping.models import IncidentCreate, IncidentType, LocalizedText

        route = respx.post(f"{API_BASE}{Endpoint.INCIDENTS}").mock(
            return_value=httpx.Response(201, json={"message": "ok", "uuid": "inci_x"})
        )
        respx.get(f"{API_BASE}{Endpoint.INCIDENTS}/inci_x").mock(
            return_value=httpx.Response(
                200,
                json={
                    "uuid": "inci_x",
                    "date": "2024-01-15T10:00:00Z",
                    "title": {"en": "X"},
                    "text": {"en": "Y"},
                    "type": "incident",
                    "affectedComponents": [],
                    "statuspages": [],
                    "updates": [],
                },
            )
        )
        result = await async_client.create_incidents(
            IncidentCreate(
                title=LocalizedText(en="X"),
                text=LocalizedText(en="Y"),
                type=IncidentType.INCIDENT,
                statuspages=[f"sp_{i}" for i in range(60)],
            )
        )
        assert len(result) == 2
        assert route.call_count == 2

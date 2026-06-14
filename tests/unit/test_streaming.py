"""Tests for async streaming helpers (PY-10)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from hyperping._async_client import AsyncHyperpingClient
from hyperping.client import RetryConfig
from hyperping.exceptions import (
    HyperpingAPIError,
    HyperpingAuthError,
    HyperpingNotFoundError,
    HyperpingRateLimitError,
)
from hyperping.models import Incident, IncidentUpdate, LocalizedText
from hyperping.models._alert_models import Alert, AlertType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _monitor_dict(uuid: str, name: str, *, down: bool) -> dict:
    return {
        "uuid": uuid,
        "name": name,
        "url": "https://example.com",
        "protocol": "http",
        "down": down,
        "paused": False,
    }


def _incident(uuid: str, updates: list[dict]) -> Incident:
    return Incident(
        uuid=uuid,
        title=LocalizedText(en="Test Incident"),
        type="incident",
        statuspages=["sp_1"],
        updates=[
            IncidentUpdate(
                uuid=u["uuid"],
                date=u["date"],
                text=LocalizedText(en=u["text"]),
                type=u["type"],
            )
            for u in updates
        ],
    )


async def _drain(gen, *, until_cancelled: bool = False) -> list:
    """Collect items from an async generator, catching CancelledError."""
    items: list = []
    try:
        async for item in gen:
            items.append(item)
    except asyncio.CancelledError:
        if not until_cancelled:
            raise
    return items


@pytest_asyncio.fixture
async def async_client() -> AsyncHyperpingClient:
    client = AsyncHyperpingClient(
        api_key="sk_test_key",
        retry_config=RetryConfig(max_retries=0),
    )
    yield client
    await client.close()


# ---------------------------------------------------------------------------
# Alert model tests
# ---------------------------------------------------------------------------


class TestAlertModel:
    def test_alert_model_frozen(self) -> None:
        a = Alert(
            monitor_uuid="mon_1",
            monitor_name="Test",
            type=AlertType.DOWN,
            timestamp="2026-01-01T00:00:00+00:00",
        )
        with pytest.raises(Exception):
            a.monitor_uuid = "mon_2"  # type: ignore[misc]

    def test_alert_model_extra_fields_allowed(self) -> None:
        a = Alert(
            monitor_uuid="mon_1",
            monitor_name="Test",
            type=AlertType.DOWN,
            timestamp="2026-01-01T00:00:00+00:00",
            extra_field="ignored",
        )
        assert a.monitor_uuid == "mon_1"

    def test_alert_type_enum_values(self) -> None:
        assert AlertType.DOWN == "down"
        assert AlertType.UP == "up"
        assert AlertType.DEGRADED == "degraded"

    def test_alert_accepts_alias_names(self) -> None:
        a = Alert(
            monitorUuid="mon_alias",
            monitorName="Alias Test",
            type=AlertType.UP,
            timestamp="2026-01-01T00:00:00+00:00",
        )
        assert a.monitor_uuid == "mon_alias"
        assert a.monitor_name == "Alias Test"


# ---------------------------------------------------------------------------
# stream_alerts tests
# ---------------------------------------------------------------------------


class TestStreamAlerts:
    async def test_stream_alerts_no_alert_on_first_poll(
        self, async_client: AsyncHyperpingClient
    ) -> None:
        """First poll establishes baseline; nothing yielded."""
        monitor_data = [_monitor_dict("mon_1", "Test", down=False)]

        with (
            patch.object(async_client, "_request", new=AsyncMock(return_value=monitor_data)),
            patch("asyncio.sleep", new=AsyncMock(side_effect=asyncio.CancelledError)),
        ):
            results = await _drain(
                async_client.stream_alerts(poll_interval=0.0), until_cancelled=True
            )

        assert results == []

    async def test_stream_alerts_yields_down_alert_on_transition(
        self, async_client: AsyncHyperpingClient
    ) -> None:
        """Monitor flips from up to down; yields Alert(type='down')."""
        poll1 = [_monitor_dict("mon_1", "Test", down=False)]
        poll2 = [_monitor_dict("mon_1", "Test", down=True)]

        sleep_calls = 0

        async def controlled_sleep(_interval: float) -> None:
            nonlocal sleep_calls
            sleep_calls += 1
            if sleep_calls >= 2:
                raise asyncio.CancelledError

        with (
            patch.object(async_client, "_request", new=AsyncMock(side_effect=[poll1, poll2])),
            patch("asyncio.sleep", new=controlled_sleep),
        ):
            results = await _drain(
                async_client.stream_alerts(poll_interval=0.0), until_cancelled=True
            )

        assert len(results) == 1
        assert isinstance(results[0], Alert)
        assert results[0].type == AlertType.DOWN
        assert results[0].monitor_uuid == "mon_1"
        assert results[0].monitor_name == "Test"

    async def test_stream_alerts_yields_up_alert_on_recovery(
        self, async_client: AsyncHyperpingClient
    ) -> None:
        """Monitor recovers from down to up; yields Alert(type='up')."""
        poll1 = [_monitor_dict("mon_1", "Test", down=True)]
        poll2 = [_monitor_dict("mon_1", "Test", down=False)]

        sleep_calls = 0

        async def controlled_sleep(_interval: float) -> None:
            nonlocal sleep_calls
            sleep_calls += 1
            if sleep_calls >= 2:
                raise asyncio.CancelledError

        with (
            patch.object(async_client, "_request", new=AsyncMock(side_effect=[poll1, poll2])),
            patch("asyncio.sleep", new=controlled_sleep),
        ):
            results = await _drain(
                async_client.stream_alerts(poll_interval=0.0), until_cancelled=True
            )

        assert len(results) == 1
        assert results[0].type == AlertType.UP

    async def test_stream_alerts_no_alert_when_state_unchanged(
        self, async_client: AsyncHyperpingClient
    ) -> None:
        """Two identical polls produce no alerts."""
        monitor_data = [_monitor_dict("mon_1", "Test", down=False)]

        sleep_calls = 0

        async def controlled_sleep(_interval: float) -> None:
            nonlocal sleep_calls
            sleep_calls += 1
            if sleep_calls >= 2:
                raise asyncio.CancelledError

        with (
            patch.object(
                async_client,
                "_request",
                new=AsyncMock(side_effect=[monitor_data, monitor_data]),
            ),
            patch("asyncio.sleep", new=controlled_sleep),
        ):
            results = await _drain(
                async_client.stream_alerts(poll_interval=0.0), until_cancelled=True
            )

        assert results == []

    async def test_stream_alerts_multiple_monitors(
        self, async_client: AsyncHyperpingClient
    ) -> None:
        """Two monitors each flip independently; one alert per transition."""
        poll1 = [
            _monitor_dict("mon_1", "Alpha", down=False),
            _monitor_dict("mon_2", "Beta", down=False),
        ]
        poll2 = [
            _monitor_dict("mon_1", "Alpha", down=True),
            _monitor_dict("mon_2", "Beta", down=True),
        ]

        sleep_calls = 0

        async def controlled_sleep(_interval: float) -> None:
            nonlocal sleep_calls
            sleep_calls += 1
            if sleep_calls >= 2:
                raise asyncio.CancelledError

        with (
            patch.object(async_client, "_request", new=AsyncMock(side_effect=[poll1, poll2])),
            patch("asyncio.sleep", new=controlled_sleep),
        ):
            results = await _drain(
                async_client.stream_alerts(poll_interval=0.0), until_cancelled=True
            )

        assert len(results) == 2
        uuids = {a.monitor_uuid for a in results}
        assert uuids == {"mon_1", "mon_2"}
        assert all(a.type == AlertType.DOWN for a in results)

    async def test_stream_alerts_respects_poll_interval(
        self, async_client: AsyncHyperpingClient
    ) -> None:
        """asyncio.sleep is called with the configured interval."""
        monitor_data = [_monitor_dict("mon_1", "Test", down=False)]
        recorded_intervals: list[float] = []

        async def capturing_sleep(interval: float) -> None:
            recorded_intervals.append(interval)
            if len(recorded_intervals) >= 1:
                raise asyncio.CancelledError

        with (
            patch.object(async_client, "_request", new=AsyncMock(return_value=monitor_data)),
            patch("asyncio.sleep", new=capturing_sleep),
        ):
            await _drain(async_client.stream_alerts(poll_interval=42.0), until_cancelled=True)

        assert recorded_intervals[0] == 42.0

    async def test_stream_alerts_custom_poll_interval(
        self, async_client: AsyncHyperpingClient
    ) -> None:
        """Non-default poll_interval is forwarded to asyncio.sleep."""
        monitor_data = [_monitor_dict("mon_1", "Test", down=False)]
        recorded_intervals: list[float] = []

        async def capturing_sleep(interval: float) -> None:
            recorded_intervals.append(interval)
            raise asyncio.CancelledError

        with (
            patch.object(async_client, "_request", new=AsyncMock(return_value=monitor_data)),
            patch("asyncio.sleep", new=capturing_sleep),
        ):
            await _drain(async_client.stream_alerts(poll_interval=5.0), until_cancelled=True)

        assert recorded_intervals[0] == 5.0


# ---------------------------------------------------------------------------
# stream_incident_updates tests
# ---------------------------------------------------------------------------


class TestStreamIncidentUpdates:
    async def test_stream_incident_updates_yields_new_update(
        self, async_client: AsyncHyperpingClient
    ) -> None:
        """A new update appearing between polls is yielded."""
        upd1 = {
            "uuid": "upd_1",
            "date": "2026-01-01T00:00:00Z",
            "text": "first",
            "type": "investigating",
        }
        upd2 = {
            "uuid": "upd_2",
            "date": "2026-01-01T01:00:00Z",
            "text": "second",
            "type": "resolved",
        }

        incident_v1 = _incident("inci_1", [upd1])
        incident_v2 = _incident("inci_1", [upd1, upd2])

        sleep_calls = 0

        async def controlled_sleep(_interval: float) -> None:
            nonlocal sleep_calls
            sleep_calls += 1
            if sleep_calls >= 2:
                raise asyncio.CancelledError

        with (
            patch.object(
                async_client,
                "get_incident",
                new=AsyncMock(side_effect=[incident_v1, incident_v2]),
            ),
            patch("asyncio.sleep", new=controlled_sleep),
        ):
            results = await _drain(
                async_client.stream_incident_updates("inci_1", poll_interval=0.0),
                until_cancelled=True,
            )

        uuids = [r.uuid for r in results]
        assert "upd_2" in uuids

    async def test_stream_incident_updates_no_yield_for_seen_updates(
        self, async_client: AsyncHyperpingClient
    ) -> None:
        """Updates seen on a previous poll are not re-yielded."""
        upd1 = {
            "uuid": "upd_1",
            "date": "2026-01-01T00:00:00Z",
            "text": "first",
            "type": "investigating",
        }
        incident = _incident("inci_1", [upd1])

        sleep_calls = 0

        async def controlled_sleep(_interval: float) -> None:
            nonlocal sleep_calls
            sleep_calls += 1
            if sleep_calls >= 2:
                raise asyncio.CancelledError

        with (
            patch.object(
                async_client,
                "get_incident",
                new=AsyncMock(side_effect=[incident, incident]),
            ),
            patch("asyncio.sleep", new=controlled_sleep),
        ):
            results = await _drain(
                async_client.stream_incident_updates("inci_1", poll_interval=0.0),
                until_cancelled=True,
            )

        assert len([r for r in results if r.uuid == "upd_1"]) == 1

    async def test_stream_incident_updates_multiple_new_updates(
        self, async_client: AsyncHyperpingClient
    ) -> None:
        """Two new updates appearing at once are both yielded."""
        upd1 = {
            "uuid": "upd_1",
            "date": "2026-01-01T00:00:00Z",
            "text": "first",
            "type": "investigating",
        }
        upd2 = {
            "uuid": "upd_2",
            "date": "2026-01-01T01:00:00Z",
            "text": "second",
            "type": "identified",
        }
        upd3 = {
            "uuid": "upd_3",
            "date": "2026-01-01T02:00:00Z",
            "text": "third",
            "type": "resolved",
        }

        incident_v1 = _incident("inci_1", [upd1])
        incident_v2 = _incident("inci_1", [upd1, upd2, upd3])

        sleep_calls = 0

        async def controlled_sleep(_interval: float) -> None:
            nonlocal sleep_calls
            sleep_calls += 1
            if sleep_calls >= 2:
                raise asyncio.CancelledError

        with (
            patch.object(
                async_client,
                "get_incident",
                new=AsyncMock(side_effect=[incident_v1, incident_v2]),
            ),
            patch("asyncio.sleep", new=controlled_sleep),
        ):
            results = await _drain(
                async_client.stream_incident_updates("inci_1", poll_interval=0.0),
                until_cancelled=True,
            )

        new_uuids = {r.uuid for r in results} - {"upd_1"}
        assert new_uuids == {"upd_2", "upd_3"}

    async def test_stream_incident_updates_invalid_uuid_raises(
        self, async_client: AsyncHyperpingClient
    ) -> None:
        """Invalid UUID format raises ValueError before polling starts."""
        with pytest.raises(ValueError, match="Invalid"):
            async for _ in async_client.stream_incident_updates("not/a/valid/id"):
                pass

    async def test_stream_incident_updates_not_found_raises(
        self, async_client: AsyncHyperpingClient
    ) -> None:
        """Incident not found raises HyperpingNotFoundError on first poll."""
        with patch.object(
            async_client,
            "get_incident",
            new=AsyncMock(side_effect=HyperpingNotFoundError("not found", status_code=404)),
        ):
            with pytest.raises(HyperpingNotFoundError):
                async for _ in async_client.stream_incident_updates("inci_missing"):
                    pass

    async def test_stream_incident_updates_respects_poll_interval(
        self, async_client: AsyncHyperpingClient
    ) -> None:
        """asyncio.sleep is called with the configured interval."""
        incident = _incident("inci_1", [])
        recorded_intervals: list[float] = []

        async def capturing_sleep(interval: float) -> None:
            recorded_intervals.append(interval)
            raise asyncio.CancelledError

        with (
            patch.object(
                async_client,
                "get_incident",
                new=AsyncMock(return_value=incident),
            ),
            patch("asyncio.sleep", new=capturing_sleep),
        ):
            await _drain(
                async_client.stream_incident_updates("inci_1", poll_interval=15.0),
                until_cancelled=True,
            )

        assert recorded_intervals[0] == 15.0


# ---------------------------------------------------------------------------
# Error-recovery tests (max_errors parameter, #b854ab)
# ---------------------------------------------------------------------------


class TestStreamErrorRecovery:
    async def test_stream_alerts_tolerates_errors_within_budget(
        self, async_client: AsyncHyperpingClient
    ) -> None:
        """A transient API error within the max_errors budget does not raise; baseline preserved."""
        poll1 = [_monitor_dict("mon_1", "Test", down=False)]
        poll3 = [_monitor_dict("mon_1", "Test", down=True)]

        with (
            patch.object(
                async_client,
                "_request",
                new=AsyncMock(side_effect=[poll1, HyperpingAPIError("transient"), poll3]),
            ),
            patch(
                "asyncio.sleep",
                new=AsyncMock(side_effect=[None, None, asyncio.CancelledError()]),
            ),
        ):
            results = await _drain(
                async_client.stream_alerts(poll_interval=0.0, max_errors=3),
                until_cancelled=True,
            )

        assert len(results) == 1
        assert results[0].type == AlertType.DOWN
        assert results[0].monitor_uuid == "mon_1"

    async def test_stream_alerts_raises_after_exceeding_error_budget(
        self, async_client: AsyncHyperpingClient
    ) -> None:
        """Three consecutive errors with max_errors=3 re-raises the last exception."""
        poll1 = [_monitor_dict("mon_1", "Test", down=False)]
        err = HyperpingAPIError("persistent failure")

        with (
            patch.object(
                async_client,
                "_request",
                new=AsyncMock(side_effect=[poll1, err, err, err]),
            ),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            with pytest.raises(HyperpingAPIError):
                async for _ in async_client.stream_alerts(poll_interval=0.0, max_errors=3):
                    pass

    async def test_stream_alerts_reraises_auth_error_immediately(
        self, async_client: AsyncHyperpingClient
    ) -> None:
        """HyperpingAuthError bypasses tolerance and re-raises immediately."""
        poll1 = [_monitor_dict("mon_1", "Test", down=False)]

        with (
            patch.object(
                async_client,
                "_request",
                new=AsyncMock(
                    side_effect=[
                        poll1,
                        HyperpingAuthError("unauthorized", status_code=401),
                    ]
                ),
            ),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            with pytest.raises(HyperpingAuthError):
                async for _ in async_client.stream_alerts(poll_interval=0.0, max_errors=3):
                    pass

    async def test_stream_alerts_reraises_rate_limit_error_immediately(
        self, async_client: AsyncHyperpingClient
    ) -> None:
        """HyperpingRateLimitError bypasses tolerance and re-raises immediately."""
        poll1 = [_monitor_dict("mon_1", "Test", down=False)]

        with (
            patch.object(
                async_client,
                "_request",
                new=AsyncMock(
                    side_effect=[
                        poll1,
                        HyperpingRateLimitError("rate limited", status_code=429),
                    ]
                ),
            ),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            with pytest.raises(HyperpingRateLimitError):
                async for _ in async_client.stream_alerts(poll_interval=0.0, max_errors=3):
                    pass

    async def test_stream_alerts_error_counter_resets_on_success(
        self, async_client: AsyncHyperpingClient
    ) -> None:
        """Error counter resets after a successful poll; recovery poll alerts are yielded."""
        monitor_up = [_monitor_dict("mon_1", "Test", down=False)]
        monitor_down = [_monitor_dict("mon_1", "Test", down=True)]
        err = HyperpingAPIError("transient")

        with (
            patch.object(
                async_client,
                "_request",
                new=AsyncMock(
                    side_effect=[
                        monitor_up,  # poll 1: baseline (consecutive_errors stays 0)
                        err,  # poll 2: fail (consecutive_errors=1)
                        monitor_up,  # poll 3: success, no change (consecutive_errors=0)
                        err,  # poll 4: fail (consecutive_errors=1)
                        err,  # poll 5: fail (consecutive_errors=2)
                        monitor_down,  # poll 6: success, state change -> Alert(DOWN)
                    ]
                ),
            ),
            patch(
                "asyncio.sleep",
                new=AsyncMock(side_effect=[None, None, None, None, None, asyncio.CancelledError()]),
            ),
        ):
            results = await _drain(
                async_client.stream_alerts(poll_interval=0.0, max_errors=3),
                until_cancelled=True,
            )

        assert len(results) == 1
        assert results[0].type == AlertType.DOWN

    async def test_stream_alerts_max_errors_none_tolerates_infinite_errors(
        self, async_client: AsyncHyperpingClient
    ) -> None:
        """max_errors=None allows unlimited consecutive errors; generator recovers on success."""
        monitor_up = [_monitor_dict("mon_1", "Test", down=False)]
        monitor_down = [_monitor_dict("mon_1", "Test", down=True)]
        err = HyperpingAPIError("persistent")

        with (
            patch.object(
                async_client,
                "_request",
                new=AsyncMock(side_effect=[monitor_up] + [err] * 10 + [monitor_down]),
            ),
            patch(
                "asyncio.sleep",
                new=AsyncMock(side_effect=[None] * 11 + [asyncio.CancelledError()]),
            ),
        ):
            results = await _drain(
                async_client.stream_alerts(poll_interval=0.0, max_errors=None),
                until_cancelled=True,
            )

        assert len(results) == 1
        assert results[0].type == AlertType.DOWN

    async def test_stream_incident_updates_tolerates_errors_within_budget(
        self, async_client: AsyncHyperpingClient
    ) -> None:
        """A transient error within budget is tolerated; seen updates are not re-yielded."""
        upd1 = {
            "uuid": "upd_1",
            "date": "2026-01-01T00:00:00Z",
            "text": "first",
            "type": "investigating",
        }
        upd2 = {
            "uuid": "upd_2",
            "date": "2026-01-01T01:00:00Z",
            "text": "second",
            "type": "resolved",
        }
        incident_v1 = _incident("inci_1", [upd1])
        incident_v2 = _incident("inci_1", [upd1, upd2])

        with (
            patch.object(
                async_client,
                "get_incident",
                new=AsyncMock(
                    side_effect=[
                        incident_v1,
                        HyperpingAPIError("transient"),
                        incident_v2,
                    ]
                ),
            ),
            patch(
                "asyncio.sleep",
                new=AsyncMock(side_effect=[None, None, asyncio.CancelledError()]),
            ),
        ):
            results = await _drain(
                async_client.stream_incident_updates("inci_1", poll_interval=0.0, max_errors=3),
                until_cancelled=True,
            )

        uuids = [r.uuid for r in results]
        assert "upd_2" in uuids
        assert uuids.count("upd_1") == 1

    async def test_stream_incident_updates_raises_after_exceeding_error_budget(
        self, async_client: AsyncHyperpingClient
    ) -> None:
        """Three consecutive errors with max_errors=3 re-raises the exception."""
        incident_v1 = _incident("inci_1", [])
        err = HyperpingAPIError("persistent")

        with (
            patch.object(
                async_client,
                "get_incident",
                new=AsyncMock(side_effect=[incident_v1, err, err, err]),
            ),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            with pytest.raises(HyperpingAPIError):
                async for _ in async_client.stream_incident_updates(
                    "inci_1", poll_interval=0.0, max_errors=3
                ):
                    pass

    async def test_stream_alerts_backoff_sleep_between_failures(
        self, async_client: AsyncHyperpingClient
    ) -> None:
        """Backoff delays increase exponentially between failures and are capped at max_delay."""
        client = AsyncHyperpingClient(
            api_key="sk_test_key",
            retry_config=RetryConfig(
                max_retries=0, initial_delay=1.0, backoff_factor=2.0, max_delay=3.0
            ),
        )
        try:
            monitor_up = [_monitor_dict("mon_1", "Test", down=False)]
            err = HyperpingAPIError("transient")
            recorded_sleeps: list[float] = []
            call_count = 0

            async def tracking_sleep(delay: float) -> None:
                nonlocal call_count
                call_count += 1
                recorded_sleeps.append(delay)
                if call_count >= 4:
                    raise asyncio.CancelledError

            with (
                patch.object(
                    client,
                    "_request",
                    new=AsyncMock(side_effect=[monitor_up, err, err, err, err]),
                ),
                patch("asyncio.sleep", new=tracking_sleep),
            ):
                await _drain(
                    client.stream_alerts(poll_interval=0.0, max_errors=10),
                    until_cancelled=True,
                )
        finally:
            await client.close()

        # sleep[0]: poll_interval after poll 1 success
        # sleep[1]: 1st failure backoff = initial_delay * factor^0 = 1.0
        # sleep[2]: 2nd failure backoff = initial_delay * factor^1 = 2.0
        # sleep[3]: 3rd failure backoff = min(initial_delay * factor^2, max_delay) = 3.0 (capped)
        assert recorded_sleeps[0] == 0.0
        assert recorded_sleeps[1] == 1.0
        assert recorded_sleeps[2] == 2.0
        assert recorded_sleeps[3] == 3.0

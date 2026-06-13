"""Tests for hyp monitor subcommands."""

import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from hyperping.cli._app import app
from hyperping.exceptions import HyperpingNotFoundError
from hyperping.models import Monitor

runner = CliRunner()

FAKE_MONITOR = Monitor.model_validate(
    {
        "uuid": "mon_123",
        "name": "Test Monitor",
        "url": "https://example.com",
        "protocol": "http",
        "http_method": "GET",
        "check_frequency": 30,
        "regions": ["paris"],
        "down": False,
        "paused": False,
    }
)

FAKE_MONITOR_PAUSED = Monitor.model_validate(
    {
        "uuid": "mon_123",
        "name": "Test Monitor",
        "url": "https://example.com",
        "protocol": "http",
        "http_method": "GET",
        "check_frequency": 30,
        "regions": ["paris"],
        "down": False,
        "paused": True,
    }
)


def _make_client(monitors: list[Monitor] | None = None) -> MagicMock:
    client = MagicMock()
    client.list_monitors.return_value = monitors if monitors is not None else [FAKE_MONITOR]
    client.get_monitor.return_value = FAKE_MONITOR
    client.pause_monitor.return_value = FAKE_MONITOR_PAUSED
    client.resume_monitor.return_value = FAKE_MONITOR
    return client


class TestMonitorList:
    def test_monitor_list_table(self) -> None:
        with patch("hyperping.cli._monitors.get_client", return_value=_make_client()):
            result = runner.invoke(app, ["--api-key", "sk_test", "monitor", "list"])
        assert result.exit_code == 0, result.output
        assert "Test Monitor" in result.output

    def test_monitor_list_json(self) -> None:
        with patch("hyperping.cli._monitors.get_client", return_value=_make_client()):
            result = runner.invoke(app, ["--api-key", "sk_test", "--json", "monitor", "list"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert data[0]["uuid"] == "mon_123"

    def test_monitor_list_empty(self) -> None:
        with patch("hyperping.cli._monitors.get_client", return_value=_make_client(monitors=[])):
            result = runner.invoke(app, ["--api-key", "sk_test", "monitor", "list"])
        assert result.exit_code == 0, result.output

    def test_monitor_get(self) -> None:
        with patch("hyperping.cli._monitors.get_client", return_value=_make_client()):
            result = runner.invoke(app, ["--api-key", "sk_test", "monitor", "get", "mon_123"])
        assert result.exit_code == 0, result.output
        assert "mon_123" in result.output

    def test_monitor_get_not_found(self) -> None:
        client = _make_client()
        client.get_monitor.side_effect = HyperpingNotFoundError("not found")
        with patch("hyperping.cli._monitors.get_client", return_value=client):
            result = runner.invoke(app, ["--api-key", "sk_test", "monitor", "get", "mon_999"])
        assert result.exit_code != 0

    def test_monitor_pause(self) -> None:
        with patch("hyperping.cli._monitors.get_client", return_value=_make_client()):
            result = runner.invoke(app, ["--api-key", "sk_test", "monitor", "pause", "mon_123"])
        assert result.exit_code == 0, result.output
        assert "pause" in result.output.lower() or "mon_123" in result.output

    def test_monitor_resume(self) -> None:
        with patch("hyperping.cli._monitors.get_client", return_value=_make_client()):
            result = runner.invoke(app, ["--api-key", "sk_test", "monitor", "resume", "mon_123"])
        assert result.exit_code == 0, result.output
        assert "resume" in result.output.lower() or "mon_123" in result.output

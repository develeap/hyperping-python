"""Tests for hyp incident subcommands."""

import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from hyperping.cli._app import app
from hyperping.models import Incident, IncidentUpdate, LocalizedText

runner = CliRunner()

FAKE_INCIDENT = Incident.model_validate(
    {
        "uuid": "inci_123",
        "title": {"en": "Test Incident"},
        "text": {"en": "Something broke"},
        "type": "incident",
        "statuspages": ["sp_abc"],
        "updates": [],
    }
)

FAKE_INCIDENT_RESOLVED = Incident.model_validate(
    {
        "uuid": "inci_123",
        "title": {"en": "Test Incident"},
        "text": {"en": "Something broke"},
        "type": "incident",
        "statuspages": ["sp_abc"],
        "updates": [
            {
                "uuid": "upd_1",
                "date": "2024-01-01T00:00:00Z",
                "text": {"en": "Resolved"},
                "type": "resolved",
            }
        ],
    }
)


def _make_client() -> MagicMock:
    client = MagicMock()
    client.list_incidents.return_value = [FAKE_INCIDENT]
    client.create_incident.return_value = FAKE_INCIDENT
    client.resolve_incident.return_value = FAKE_INCIDENT_RESOLVED
    return client


class TestIncidentList:
    def test_incident_list(self) -> None:
        with patch("hyperping.cli._incidents.get_client", return_value=_make_client()):
            result = runner.invoke(app, ["--api-key", "sk_test", "incident", "list"])
        assert result.exit_code == 0, result.output
        assert "Test Incident" in result.output

    def test_incident_list_filter_status(self) -> None:
        with patch("hyperping.cli._incidents.get_client", return_value=_make_client()):
            result = runner.invoke(
                app, ["--api-key", "sk_test", "incident", "list", "--status", "investigating"]
            )
        assert result.exit_code == 0, result.output

    def test_incident_list_json(self) -> None:
        with patch("hyperping.cli._incidents.get_client", return_value=_make_client()):
            result = runner.invoke(app, ["--api-key", "sk_test", "--json", "incident", "list"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert data[0]["uuid"] == "inci_123"

    def test_incident_create(self) -> None:
        with patch("hyperping.cli._incidents.get_client", return_value=_make_client()):
            result = runner.invoke(
                app,
                [
                    "--api-key",
                    "sk_test",
                    "incident",
                    "create",
                    "--title",
                    "Outage",
                    "--text",
                    "DB down",
                    "--statuspage",
                    "sp_abc",
                ],
            )
        assert result.exit_code == 0, result.output
        assert "inci_123" in result.output

    def test_incident_create_missing_title_exits(self) -> None:
        with patch("hyperping.cli._incidents.get_client", return_value=_make_client()):
            result = runner.invoke(
                app,
                ["--api-key", "sk_test", "incident", "create", "--text", "DB down", "--statuspage", "sp_abc"],
            )
        assert result.exit_code != 0

    def test_incident_resolve(self) -> None:
        with patch("hyperping.cli._incidents.get_client", return_value=_make_client()):
            result = runner.invoke(
                app, ["--api-key", "sk_test", "incident", "resolve", "inci_123"]
            )
        assert result.exit_code == 0, result.output
        assert "inci_123" in result.output or "resolved" in result.output.lower()

    def test_incident_resolve_with_message(self) -> None:
        with patch("hyperping.cli._incidents.get_client", return_value=_make_client()):
            result = runner.invoke(
                app,
                ["--api-key", "sk_test", "incident", "resolve", "inci_123", "--message", "Fixed it"],
            )
        assert result.exit_code == 0, result.output

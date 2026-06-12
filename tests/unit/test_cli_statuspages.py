"""Tests for hyp statuspage subcommands."""

import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from hyperping.cli._app import app
from hyperping.exceptions import HyperpingNotFoundError
from hyperping.models import StatusPage, StatusPageSubscriber

runner = CliRunner()

FAKE_PAGE = StatusPage.model_validate(
    {
        "uuid": "sp_abc",
        "name": "My Status Page",
        "subdomain": "my-status",
        "customDomain": None,
        "public": True,
        "monitors": ["mon_123"],
    }
)

FAKE_SUBSCRIBER = StatusPageSubscriber.model_validate(
    {"id": "sub_1", "email": "user@example.com"}
)


def _make_client() -> MagicMock:
    client = MagicMock()
    client.get_status_page.return_value = FAKE_PAGE
    client.list_subscribers.return_value = [FAKE_SUBSCRIBER]
    return client


class TestStatusPageShow:
    def test_statuspage_show(self) -> None:
        with patch("hyperping.cli._statuspages.get_client", return_value=_make_client()):
            result = runner.invoke(app, ["--api-key", "sk_test", "statuspage", "show", "sp_abc"])
        assert result.exit_code == 0, result.output
        assert "My Status Page" in result.output

    def test_statuspage_show_not_found(self) -> None:
        client = _make_client()
        client.get_status_page.side_effect = HyperpingNotFoundError("not found")
        with patch("hyperping.cli._statuspages.get_client", return_value=client):
            result = runner.invoke(app, ["--api-key", "sk_test", "statuspage", "show", "sp_999"])
        assert result.exit_code != 0

    def test_statuspage_subscribers(self) -> None:
        with patch("hyperping.cli._statuspages.get_client", return_value=_make_client()):
            result = runner.invoke(
                app, ["--api-key", "sk_test", "statuspage", "subscribers", "sp_abc"]
            )
        assert result.exit_code == 0, result.output
        assert "user@example.com" in result.output

    def test_statuspage_subscribers_json(self) -> None:
        with patch("hyperping.cli._statuspages.get_client", return_value=_make_client()):
            result = runner.invoke(
                app, ["--api-key", "sk_test", "--json", "statuspage", "subscribers", "sp_abc"]
            )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert data[0]["email"] == "user@example.com"

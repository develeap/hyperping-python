"""Tests for hyp tenant onboard subcommand."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from hyperping.cli._app import app
from hyperping.exceptions import HyperpingValidationError
from hyperping.models import Monitor, StatusPage

runner = CliRunner()

FAKE_PAGE = StatusPage.model_validate(
    {
        "uuid": "sp_new",
        "name": "Acme Corp",
        "subdomain": "acme-corp",
        "public": True,
        "monitors": [],
    }
)

FAKE_PAGE_WITH_MONITORS = StatusPage.model_validate(
    {
        "uuid": "sp_new",
        "name": "Acme Corp",
        "subdomain": "acme-corp",
        "public": True,
        "monitors": ["mon_m1"],
    }
)

FAKE_MONITOR = Monitor.model_validate(
    {
        "uuid": "mon_m1",
        "name": "Acme Corp - https://acme.example.com",
        "url": "https://acme.example.com",
        "protocol": "http",
        "http_method": "GET",
        "check_frequency": 30,
        "regions": ["paris"],
        "down": False,
        "paused": False,
    }
)


def _make_client() -> MagicMock:
    client = MagicMock()
    client.create_status_page.return_value = FAKE_PAGE
    client.create_monitor.return_value = FAKE_MONITOR
    client.update_status_page.return_value = FAKE_PAGE_WITH_MONITORS
    return client


class TestTenantOnboard:
    def test_tenant_onboard_page_only(self) -> None:
        with patch("hyperping.cli._tenant.get_client", return_value=_make_client()):
            result = runner.invoke(app, ["--api-key", "sk_test", "tenant", "onboard", "Acme Corp"])
        assert result.exit_code == 0, result.output
        assert "sp_new" in result.output

    def test_tenant_onboard_with_monitors(self) -> None:
        client = _make_client()
        with patch("hyperping.cli._tenant.get_client", return_value=client):
            result = runner.invoke(
                app,
                [
                    "--api-key",
                    "sk_test",
                    "tenant",
                    "onboard",
                    "Acme Corp",
                    "--monitor-url",
                    "https://acme.example.com",
                ],
            )
        assert result.exit_code == 0, result.output
        assert "sp_new" in result.output
        client.create_monitor.assert_called_once()
        client.update_status_page.assert_called_once()

    def test_tenant_onboard_duplicate_name(self) -> None:
        client = _make_client()
        client.create_status_page.side_effect = HyperpingValidationError(
            "subdomain already taken", status_code=422
        )
        with patch("hyperping.cli._tenant.get_client", return_value=client):
            result = runner.invoke(app, ["--api-key", "sk_test", "tenant", "onboard", "Acme Corp"])
        assert result.exit_code != 0

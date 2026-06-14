"""Tests for CLI client factory and API key resolution."""

import pytest
import typer

from hyperping.cli._config import get_client
from hyperping.client import HyperpingClient


class TestGetClient:
    def test_get_client_from_flag(self) -> None:
        client = get_client("sk_test_flag")
        assert isinstance(client, HyperpingClient)

    def test_get_client_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYPERPING_API_KEY", "sk_test_env")
        client = get_client(None)
        assert isinstance(client, HyperpingClient)

    def test_get_client_missing_key_exits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("HYPERPING_API_KEY", raising=False)
        with pytest.raises(typer.BadParameter):
            get_client(None)

    def test_flag_overrides_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HYPERPING_API_KEY", "sk_env")
        client = get_client("sk_flag")
        assert client._api_key.get_secret_value() == "sk_flag"

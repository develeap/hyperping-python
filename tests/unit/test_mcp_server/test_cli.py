"""Tests for the MCP server CLI entrypoint (T9)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestMcpServerCli:
    def test_cli_reads_env_api_key(self):
        from hyperping.mcp_server.__main__ import _build_parser

        parser = _build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--help"])
        assert exc_info.value.code == 0

    def test_cli_missing_api_key_exits(self):
        from hyperping.mcp_server.__main__ import main

        with pytest.raises(SystemExit) as exc_info:
            main([])
        assert exc_info.value.code != 0

    def test_cli_default_transport_stdio(self):
        from hyperping.mcp_server.__main__ import main

        mock_server = MagicMock()
        patch_target = "hyperping.mcp_server.__main__.create_mcp_server"
        with patch(patch_target, return_value=mock_server) as mock_factory:
            main(["--api-key", "sk_test", "--transport", "stdio"])

        mock_factory.assert_called_once()
        mock_server.run.assert_called_once_with(transport="stdio")

    def test_cli_tool_filter_flag(self):
        from hyperping.mcp_server.__main__ import main

        mock_server = MagicMock()
        patch_target = "hyperping.mcp_server.__main__.create_mcp_server"
        with patch(patch_target, return_value=mock_server) as mock_factory:
            main(["--api-key", "sk_test", "--tools", "monitors,incidents"])

        call_kwargs = mock_factory.call_args.kwargs
        tools_arg = call_kwargs.get("tools", [])
        assert "monitors" in tools_arg
        assert "incidents" in tools_arg

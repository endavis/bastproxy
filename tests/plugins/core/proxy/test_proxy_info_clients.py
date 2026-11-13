"""Tests that proxy info gets its client tables from the clients API (#89)."""

from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins.core.proxy.plugin._proxy import ProxyPlugin

CLIENT_LINES = ["Clients table", "row"]


def test_info_ends_with_client_lines_without_commands_run() -> None:
    requested: list[str] = []
    stub = MagicMock()
    stub.mud_connection = None
    stub.api.proxy_start_time = None

    def api(name: str) -> Any:
        requested.append(name)
        if name == "plugins.core.commands:output.header.format":
            return lambda *a: ["H"]
        if name == "plugins.core.clients:client.list.formatted":
            return lambda: list(CLIENT_LINES)
        return MagicMock()

    stub.api.side_effect = api

    result = ProxyPlugin._command_info(stub)
    success = result.success
    msg = result.message

    assert success is True
    assert msg[-3:] == ["", *CLIENT_LINES]
    assert "plugins.core.commands:command.run" not in requested
    assert "plugins.core.clients:client.list.formatted" in requested

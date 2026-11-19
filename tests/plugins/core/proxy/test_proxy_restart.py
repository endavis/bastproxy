"""Tests that the restart command tells the client once (#575)."""

from typing import Any
from unittest.mock import MagicMock, patch

from bastproxy.plugins.core.proxy.plugin._proxy import ProxyPlugin

_PATCH = "bastproxy.plugins.core.proxy.plugin._proxy.SendDataDirectlyToClient"


def _stub() -> tuple[MagicMock, list[tuple[Any, ...]]]:
    stub = MagicMock()
    stub.plugin_id = "plugins.core.proxy"
    timers: list[tuple[Any, ...]] = []

    def api(name: str) -> Any:
        if name == "plugins.core.commands:command.current.args.get":
            return lambda: {"seconds": 7}
        if name == "plugins.core.settings:setting.get":
            return lambda *_a: 9999
        if name == "plugins.core.proxy:proxy.restart":
            return lambda seconds: ProxyPlugin._api_proxy_restart(stub, seconds)
        if name == "plugins.core.timers:timer.add":
            return lambda *a, **k: timers.append(a)
        return MagicMock()

    stub.api.side_effect = api
    return stub, timers


def test_restart_command_sends_the_message_once() -> None:
    stub, timers = _stub()

    with patch(_PATCH) as sender:
        result = ProxyPlugin._command_restart(stub)

    assert sender.call_count == 1
    network_data = sender.call_args.args[0]
    assert "in 7 seconds" in str(network_data[0])
    assert result.success is True
    assert not result.message
    assert [t[0] for t in timers] == ["restart"]

"""Tests that the restart command tells the client once (#575) and rejects bad delays (#577)."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from bastproxy.plugins.core.proxy.plugin._proxy import ProxyPlugin

_PATCH = "bastproxy.plugins.core.proxy.plugin._proxy.SendDataDirectlyToClient"


def _stub(seconds: int = 7) -> tuple[MagicMock, list[tuple[Any, ...]]]:
    stub = MagicMock()
    stub.plugin_id = "plugins.core.proxy"
    timers: list[tuple[Any, ...]] = []

    def api(name: str) -> Any:
        if name == "plugins.core.commands:command.current.args.get":
            return lambda: {"seconds": seconds}
        if name == "plugins.core.settings:setting.get":
            return lambda *_a: 9999
        if name == "plugins.core.proxy:proxy.restart":
            return lambda value: ProxyPlugin._api_proxy_restart(stub, value)
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


@pytest.mark.parametrize("seconds", [0, -5])
def test_restart_command_rejects_delay_below_one(seconds: int) -> None:
    stub, timers = _stub(seconds)

    with patch(_PATCH) as sender:
        result = ProxyPlugin._command_restart(stub)

    assert result.success is False
    assert result.message
    assert sender.call_count == 0
    assert timers == []


@pytest.mark.parametrize("seconds", [0, -5])
def test_restart_api_raises_for_delay_below_one(seconds: int) -> None:
    stub, timers = _stub()

    with patch(_PATCH) as sender, pytest.raises(ValueError, match="at least 1 second"):
        ProxyPlugin._api_proxy_restart(stub, seconds)

    assert sender.call_count == 0
    assert timers == []


def test_restart_api_defaults_to_ten_seconds() -> None:
    stub, timers = _stub()

    with patch(_PATCH):
        ProxyPlugin._api_proxy_restart(stub, None)

    assert timers[0][2] == 10


def test_restart_api_schedules_the_given_delay() -> None:
    stub, timers = _stub()

    with patch(_PATCH):
        ProxyPlugin._api_proxy_restart(stub, 3)

    assert timers[0][2] == 3

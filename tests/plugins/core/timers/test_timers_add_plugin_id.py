"""Tests for ``add.timer`` with an explicit ``plugin_id`` kwarg (#144)."""

from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins._baseplugin import BasePlugin
from bastproxy.plugins.core.timers.plugin._timers import TimersPlugin

PID = "plugins.test.a"


def _stub() -> tuple[MagicMock, list[str]]:
    """Build a stub timers plugin; ``get.plugin.instance`` returns None (not loaded)."""
    stub = MagicMock()
    stub.plugin_id = "plugins.core.timers"
    stub.timer_lookup = {}
    looked_up: list[str] = []

    def api(name: str) -> Any:
        looked_up.append(name)
        if name == "libs.api:get.caller.owner":
            return lambda **_kw: "plugins.test.caller"
        if name == "libs.plugins.loader:get.plugin.instance":
            return lambda _plugin_id: None
        if name == "libs.plugins.loader:is.plugin.id":
            return lambda _plugin_id: True
        return MagicMock()

    stub.api = api
    return stub, looked_up


def test_add_timer_accepts_string_plugin_id_for_unloaded_plugin() -> None:
    stub, looked_up = _stub()

    timer = TimersPlugin._api_add_timer(stub, "t", lambda: None, 5, plugin_id=PID)

    assert timer is not None
    assert timer.owner_id == PID
    assert "libs.plugins.loader:get.plugin.instance" not in looked_up
    stub._add_timer_internal.assert_called_once_with(timer)


def test_add_timer_accepts_plugin_instance() -> None:
    stub, _ = _stub()
    instance = MagicMock(spec=BasePlugin)
    instance.plugin_id = PID

    timer = TimersPlugin._api_add_timer(stub, "t", lambda: None, 5, plugin_id=instance)

    assert timer is not None
    assert timer.owner_id == PID

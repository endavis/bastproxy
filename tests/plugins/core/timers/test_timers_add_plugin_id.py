"""Tests for ``timer.add`` with an explicit ``plugin_id`` kwarg (#144)."""

from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins._baseplugin import BasePlugin
from bastproxy.plugins.core.timers.plugin._timers import TimersPlugin

PID = "plugins.test.a"


def _stub() -> tuple[MagicMock, list[str]]:
    """Build a stub timers plugin; ``plugin.instance.get`` returns None (not loaded)."""
    stub = MagicMock()
    stub.plugin_id = "plugins.core.timers"
    stub.timer_lookup = {}
    looked_up: list[str] = []

    def api(name: str) -> Any:
        looked_up.append(name)
        if name == "libs.api:caller.owner.get":
            return lambda **_kw: "plugins.test.caller"
        if name == "libs.plugins.loader:plugin.instance.get":
            return lambda _plugin_id: None
        if name == "libs.plugins.loader:plugin.id.is.valid":
            return lambda _plugin_id: True
        return MagicMock()

    stub.api = api
    return stub, looked_up


def test_add_timer_accepts_string_plugin_id_for_unloaded_plugin() -> None:
    stub, looked_up = _stub()

    timer = TimersPlugin._api_timer_add(stub, "t", lambda: None, 5, plugin_id=PID)

    assert timer is not None
    assert timer.owner_id == PID
    assert "libs.plugins.loader:plugin.instance.get" not in looked_up
    stub._add_timer_internal.assert_called_once_with(timer)


def test_add_timer_accepts_plugin_instance() -> None:
    stub, _ = _stub()
    instance = MagicMock(spec=BasePlugin)
    instance.plugin_id = PID

    timer = TimersPlugin._api_timer_add(stub, "t", lambda: None, 5, plugin_id=instance)

    assert timer is not None
    assert timer.owner_id == PID

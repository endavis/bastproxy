"""Tests for timer removal when a plugin is unloaded or fails to load (#121)."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins.core.timers.plugin._timers import TimersPlugin

PID = "plugins.test.a"
OTHER = "plugins.test.b"


def _stub() -> tuple[MagicMock, list[str], list[str]]:
    """Build a stub timers plugin; ``plugin.instance.get`` returns None (not loaded)."""
    stub = MagicMock()
    stub.plugin_id = "plugins.core.timers"
    stub.timer_lookup = {
        "t1": SimpleNamespace(owner_id=PID),
        "t2": SimpleNamespace(owner_id=OTHER),
        "t3": SimpleNamespace(owner_id=PID),
    }
    removed: list[str] = []
    looked_up: list[str] = []

    def api(name: str) -> Any:
        looked_up.append(name)
        if name == "libs.plugins.loader:plugin.instance.get":
            return lambda _plugin_id: None
        if name == "plugins.core.timers:timer.remove":
            return removed.append
        return MagicMock()

    stub.api = api
    return stub, removed, looked_up


def test_remove_data_for_plugin_removes_only_its_timers_when_not_loaded() -> None:
    stub, removed, _ = _stub()

    TimersPlugin._api_timer_remove_for_plugin(stub, PID)

    assert sorted(removed) == ["t1", "t3"]


def test_remove_data_for_plugin_does_not_look_up_the_instance() -> None:
    stub, _, looked_up = _stub()

    TimersPlugin._api_timer_remove_for_plugin(stub, PID)

    assert "libs.plugins.loader:plugin.instance.get" not in looked_up

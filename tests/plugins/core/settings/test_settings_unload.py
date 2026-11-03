"""Tests for settings cleanup when a plugin is unloaded or fails to load (#121)."""

from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins.core.settings.plugin._settings import SettingsPlugin

PID = "plugins.test.a"
OTHER = "plugins.test.b"


def _stub(event_plugin: str = PID) -> MagicMock:
    stub = MagicMock()
    stub.plugin_id = "plugins.core.settings"
    stub.settings_info = {OTHER: {"x": {}}}
    stub.settings_values = {OTHER: MagicMock()}
    stub.settings_map = {"x": OTHER}
    stub.order = []

    def api(name: str) -> Any:
        if name == "plugins.core.events:get.current.event.record":
            return lambda: {"plugin_id": event_plugin}
        if name == "plugins.core.settings:save.plugin":
            return lambda p: (stub.order.append("save"), SettingsPlugin._api_save_plugin(stub, p))
        if name == "plugins.core.settings:remove.plugin.settings":
            return lambda p: SettingsPlugin._api_remove_plugin_settings(stub, p)
        return MagicMock()

    stub.api = api
    return stub


def test_unloaded_event_for_plugin_without_settings_is_a_noop() -> None:
    stub = _stub()

    SettingsPlugin._eventcb_settings_plugin_unloaded(stub)

    assert OTHER in stub.settings_info
    assert OTHER in stub.settings_values
    assert stub.settings_map == {"x": OTHER}


def test_unloaded_event_syncs_then_closes_and_removes_entries() -> None:
    stub = _stub()
    values = MagicMock()
    calls = MagicMock()
    calls.attach_mock(values.sync, "sync")
    calls.attach_mock(values.close, "close")
    stub.settings_info[PID] = {"a": {}}
    stub.settings_values[PID] = values
    stub.settings_map["a"] = PID

    SettingsPlugin._eventcb_settings_plugin_unloaded(stub)

    assert [c[0] for c in calls.mock_calls] == ["sync", "close"]
    assert PID not in stub.settings_info
    assert PID not in stub.settings_values
    assert "a" not in stub.settings_map
    assert OTHER in stub.settings_info
    assert stub.settings_map == {"x": OTHER}


def test_remove_plugin_settings_for_unknown_plugin_is_a_noop() -> None:
    stub = _stub()

    SettingsPlugin._api_remove_plugin_settings(stub, PID)

    assert list(stub.settings_info) == [OTHER]
    assert list(stub.settings_values) == [OTHER]

"""Reset-all keeps hidden settings, raises events and tolerates unknown plugins (#607)."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins.core.settings.plugin._settings import SettingsPlugin

PID = "plugins.test.a"


def _stub() -> tuple[MagicMock, MagicMock, Any]:
    stub = MagicMock()
    stub.plugin_id = "plugins.core.settings"
    stub.settings_info = {
        PID: {
            "_version": SimpleNamespace(default=1, hidden=True),
            "changed": SimpleNamespace(default=7, hidden=False),
            "same": SimpleNamespace(default=3, hidden=False),
        }
    }
    values: dict[str, Any] = {"_version": 2, "changed": 5, "same": 3, "stale": 9}
    raise_event = MagicMock()

    class Values(dict[str, Any]):
        sync = MagicMock()

    stub.settings_values = {PID: Values(values)}
    live = stub.settings_values[PID]

    def api(name: str) -> Any:
        if name == "libs.plugins.loader:plugin.is.loaded":
            return lambda pid: pid == PID
        if name == "plugins.core.settings:setting.get":
            return lambda _pid, setting: live[setting]
        if name == "plugins.core.settings:setting.is.hidden":
            return lambda pid, setting: SettingsPlugin._api_setting_is_hidden(stub, pid, setting)
        if name == "libs.api:api.exists":
            return lambda _name: True
        if name == "plugins.core.events:event.raise":
            return raise_event
        raise AssertionError(name)

    stub.api = api
    stub.api.startup = False
    return stub, raise_event, live


def test_reset_all_keeps_hidden_and_resets_visible() -> None:
    stub, _raise, live = _stub()
    assert SettingsPlugin._api_setting_reset(stub, PID) is None
    assert live["_version"] == 2
    assert live["changed"] == 7
    assert "stale" not in live
    live.sync.assert_called()


def test_reset_all_raises_event_only_for_changed_visible() -> None:
    stub, raise_event, _live = _stub()
    SettingsPlugin._api_setting_reset(stub, PID)
    raise_event.assert_called_once_with(
        f"ev_{PID}_var_changed_modified",
        event_args={"var": "changed", "newvalue": 7, "oldvalue": 5},
    )


def test_reset_all_unknown_plugin_returns_none() -> None:
    stub, raise_event, _live = _stub()
    assert SettingsPlugin._api_setting_reset(stub, "plugins.unknown") is None
    raise_event.assert_not_called()


def test_apis_tolerate_unknown_plugin_and_setting() -> None:
    stub, raise_event, _live = _stub()
    assert SettingsPlugin._api_setting_list(stub, "plugins.unknown") == {}
    assert SettingsPlugin._api_setting_save_for_plugin(stub, "plugins.unknown") is None
    assert SettingsPlugin._api_setting_is_hidden(stub, "plugins.unknown", "x") is False
    assert SettingsPlugin._api_setting_is_hidden(stub, PID, "nope") is False
    assert SettingsPlugin._api_setting_is_hidden(stub, PID, "_version") is True
    assert SettingsPlugin._api_setting_event_raise_all(stub, "plugins.unknown") is None
    raise_event.assert_not_called()

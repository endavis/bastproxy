"""Tests for the settings setting.set.from.user API and the pset command (#89)."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins.core.settings.plugin._settings import SettingsPlugin

PID = "plugins.test.a"
OTHER = "plugins.test.b"


def _info(**kwargs: Any) -> SimpleNamespace:
    values: dict[str, Any] = {
        "hidden": False,
        "readonly": False,
        "stype": "int",
        "aftersetmessage": "",
    }
    values.update(kwargs)
    return SimpleNamespace(**values)


def _stub(info: Any = None, change_error: Exception | None = None) -> MagicMock:
    stub = MagicMock()
    stub.plugin_id = "plugins.core.settings"
    stub.settings_map = {"foo": PID}
    stub.format_setting_for_print.return_value = "5"
    change = MagicMock(side_effect=change_error)
    stub.change = change
    infos = {PID: info if info is not None else _info()}

    def api(name: str) -> Any:
        if name == "plugins.core.settings:setting.info.get":
            return lambda pid, _setting: infos.get(pid)
        if name == "plugins.core.settings:setting.set":
            return change
        return MagicMock()

    stub.api = api
    return stub


def test_empty_value_fails_without_changing() -> None:
    stub = _stub()
    assert SettingsPlugin._api_setting_set_from_user(stub, "foo", "") == (
        False,
        ["please specify a value to set the setting to"],
    )
    stub.change.assert_not_called()


def test_unknown_name() -> None:
    assert SettingsPlugin._api_setting_set_from_user(_stub(), "nope", "5") == (
        True,
        ["plugin setting nope does not exist"],
    )


def test_setting_owned_by_another_plugin() -> None:
    stub = _stub()
    assert SettingsPlugin._api_setting_set_from_user(stub, "foo", "5", OTHER) == (
        True,
        [f"plugin setting {OTHER} foo does not exist"],
    )
    stub.change.assert_not_called()


def test_hidden_setting() -> None:
    stub = _stub(_info(hidden=True))
    assert SettingsPlugin._api_setting_set_from_user(stub, "foo", "5", PID) == (
        True,
        [f"plugin setting {PID} foo does not exist"],
    )
    stub.change.assert_not_called()


def test_readonly_setting() -> None:
    stub = _stub(_info(readonly=True))
    assert SettingsPlugin._api_setting_set_from_user(stub, "foo", "5", PID) == (
        True,
        ["foo is a readonly setting"],
    )
    stub.change.assert_not_called()


def test_success_uses_plugin_from_settings_map_when_empty() -> None:
    stub = _stub()
    assert SettingsPlugin._api_setting_set_from_user(stub, "foo", "5") == (
        True,
        [f"{PID} : foo is now set to 5"],
    )
    stub.change.assert_called_once_with(PID, "foo", "5")


def test_success_with_aftersetmessage() -> None:
    stub = _stub(_info(aftersetmessage="restart needed"))
    assert SettingsPlugin._api_setting_set_from_user(stub, "foo", "5", PID) == (
        True,
        [f"{PID} : foo is now set to 5", "\n", "restart needed"],
    )


def test_value_error() -> None:
    stub = _stub(change_error=ValueError("bad"))
    assert SettingsPlugin._api_setting_set_from_user(stub, "foo", "bad", PID) == (
        True,
        ["Cannot convert bad to int"],
    )


def test_pset_passes_args_through() -> None:
    stub = MagicMock()
    stub.plugin_id = "plugins.core.settings"
    args = {"name": "foo", "value": "5", "plugin": PID}
    calls: dict[str, Any] = {}

    def api(name: str) -> Any:
        if name == "plugins.core.commands:command.current.args.get":
            return lambda: args
        if name == "plugins.core.settings:setting.set.from.user":
            return lambda *a: (calls.setdefault("args", a), (True, ["ok"]))[1]
        raise AssertionError(name)

    stub.api = api

    assert SettingsPlugin._command_settings_plugin_sets(stub) == (True, ["ok"])
    assert calls["args"] == ("foo", "5", PID)

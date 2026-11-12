"""Tests for the setting validator (#399)."""

from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins.core.settings.libs._settinginfo import SettingInfo
from bastproxy.plugins.core.settings.plugin._settings import SettingsPlugin

PID = "plugins.test.a"


class _Values(dict):
    """PersistentDict stand-in that records writes."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.writes: list[tuple[str, Any]] = []

    def __setitem__(self, key: str, value: Any) -> None:
        self.writes.append((key, value))
        super().__setitem__(key, value)

    def sync(self) -> None:
        """Do nothing."""


def _validator(value: str) -> str:
    return "no dots" if "." in value else ""


def _stub(validator: Any = None, stored: str = "old") -> MagicMock:
    stub = MagicMock()
    stub.plugin_id = "plugins.core.settings"
    stub.settings_info = {PID: {"foo": SettingInfo("foo", "d", "help", str, validator=validator)}}
    stub.settings_values = {PID: _Values({"foo": stored})}

    def api(name: str) -> Any:
        if name == "plugins.core.settings:setting.get":
            return lambda pid, setting: stub.settings_values[pid].get(setting)
        return lambda *a, **k: False

    stub.api = api
    return stub


def test_setting_info_validator_defaults_to_none() -> None:
    assert SettingInfo("a", 1, "h", int).validator is None


def test_valid_value_is_stored() -> None:
    stub = _stub(_validator)
    assert SettingsPlugin._api_setting_set(stub, PID, "foo", "new") is True
    assert stub.settings_values[PID].writes == [("foo", "new")]


def test_rejected_value_raises_and_keeps_old_value() -> None:
    stub = _stub(_validator)
    try:
        SettingsPlugin._api_setting_set(stub, PID, "foo", "a.b")
    except ValueError as err:
        assert str(err) == "no dots"
    else:
        raise AssertionError("expected ValueError")
    assert stub.settings_values[PID].writes == []
    assert stub.settings_values[PID].get("foo") == "old"


def test_no_validator_behaves_as_before() -> None:
    stub = _stub(None)
    assert SettingsPlugin._api_setting_set(stub, PID, "foo", "a.b") is True
    assert stub.settings_values[PID].writes == [("foo", "a.b")]


def test_set_from_user_shows_validator_message() -> None:
    stub = MagicMock()
    stub.plugin_id = "plugins.core.settings"
    stub.settings_map = {"foo": PID}
    info = SettingInfo("foo", "d", "help", str, validator=_validator)

    def api(name: str) -> Any:
        if name == "plugins.core.settings:setting.info.get":
            return lambda pid, _s: info
        if name == "plugins.core.settings:setting.set":
            return lambda pid, s, v: SettingsPlugin._api_setting_set(_stub(_validator), pid, s, v)
        return MagicMock()

    stub.api = api
    result = SettingsPlugin._api_setting_set_from_user(stub, "foo", "a.b")
    assert result == (True, ["no dots"])

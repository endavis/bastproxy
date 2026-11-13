"""Tests for the per-setting modified event raised by settings change (#157)."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins.core.settings.plugin._settings import SettingsPlugin

PID = "plugins.test.a"


def _stub(
    *,
    loaded: bool = True,
    hidden: bool = False,
    startup: bool = False,
    old: Any = 1,
) -> tuple[MagicMock, MagicMock]:
    stub = MagicMock()
    stub.plugin_id = "plugins.core.settings"
    stub.settings_info = {
        PID: {"foo": SimpleNamespace(default=7, stype="int")},
    }
    stub.settings_values = {PID: MagicMock()}
    values: dict[str, Any] = {"foo": old}

    def setitem(key: str, val: Any) -> None:
        values[key] = val

    stub.settings_values[PID].__setitem__.side_effect = setitem
    raise_event = MagicMock()

    def api(name: str) -> Any:
        if name == "libs.plugins.loader:plugin.is.loaded":
            return lambda pid: loaded if pid == PID else False
        if name == "plugins.core.settings:setting.get":
            return lambda _pid, setting: values[setting]
        if name == "plugins.core.settings:setting.is.hidden":
            return lambda _pid, _setting: hidden
        if name == "libs.api:api.exists":
            return lambda _name: True
        if name == "plugins.core.events:event.raise":
            return raise_event
        raise AssertionError(name)

    stub.api = api
    stub.api.startup = startup
    stub.values = values
    return stub, raise_event


def test_loaded_plugin_change_raises_event() -> None:
    stub, raise_event = _stub()
    assert SettingsPlugin._api_setting_set(stub, PID, "foo", 5) is True
    raise_event.assert_called_once_with(
        f"ev_{PID}_var_foo_modified",
        event_args={"var": "foo", "newvalue": 5, "oldvalue": 1},
    )


def test_plugin_not_loaded_stores_without_event() -> None:
    stub, raise_event = _stub(loaded=False)
    assert SettingsPlugin._api_setting_set(stub, PID, "foo", 5) is True
    assert stub.values["foo"] == 5
    raise_event.assert_not_called()


def test_hidden_setting_no_event() -> None:
    stub, raise_event = _stub(hidden=True)
    assert SettingsPlugin._api_setting_set(stub, PID, "foo", 5) is True
    raise_event.assert_not_called()


def test_startup_no_event() -> None:
    stub, raise_event = _stub(startup=True)
    assert SettingsPlugin._api_setting_set(stub, PID, "foo", 5) is True
    raise_event.assert_not_called()


def test_same_value_no_event() -> None:
    stub, raise_event = _stub(old=5)
    assert SettingsPlugin._api_setting_set(stub, PID, "foo", 5) is True
    raise_event.assert_not_called()


def test_default_keyword_is_stored_as_itself() -> None:
    stub, raise_event = _stub()
    assert SettingsPlugin._api_setting_set(stub, PID, "foo", "default") is True
    assert stub.values["foo"] == "default"
    raise_event.assert_called_once_with(
        f"ev_{PID}_var_foo_modified",
        event_args={"var": "foo", "newvalue": "default", "oldvalue": 1},
    )


def test_empty_string_is_stored() -> None:
    stub, _raise_event = _stub()
    assert SettingsPlugin._api_setting_set(stub, PID, "foo", "") is True
    assert stub.values["foo"] == ""


def test_validator_refusing_empty_keeps_old_value() -> None:
    import pytest

    from bastproxy.plugins.core.settings import SettingValidationError, non_empty

    stub, raise_event = _stub()
    stub.settings_info[PID]["foo"].validator = non_empty()
    with pytest.raises(SettingValidationError):
        SettingsPlugin._api_setting_set(stub, PID, "foo", "")
    assert stub.values["foo"] == 1
    raise_event.assert_not_called()


def test_reset_stores_default_and_raises_event() -> None:
    stub, raise_event = _stub()
    assert SettingsPlugin._api_setting_reset(stub, PID, "foo") is True
    assert stub.values["foo"] == 7
    stub.settings_values[PID].sync.assert_called_once_with()
    raise_event.assert_called_once_with(
        f"ev_{PID}_var_foo_modified",
        event_args={"var": "foo", "newvalue": 7, "oldvalue": 1},
    )


def test_reset_does_not_call_validator() -> None:
    stub, _raise_event = _stub()
    validator = MagicMock(return_value="refused")
    stub.settings_info[PID]["foo"].validator = validator
    assert SettingsPlugin._api_setting_reset(stub, PID, "foo") is True
    validator.assert_not_called()


def test_reset_at_default_raises_no_event() -> None:
    stub, raise_event = _stub(old=7)
    assert SettingsPlugin._api_setting_reset(stub, PID, "foo") is True
    raise_event.assert_not_called()


def test_reset_unknown_plugin_or_setting() -> None:
    stub, _raise_event = _stub()
    assert SettingsPlugin._api_setting_reset(stub, "nope", "foo") is False
    assert SettingsPlugin._api_setting_reset(stub, PID, "nope") is False


def test_reset_without_event_cases() -> None:
    for kwargs in ({"loaded": False}, {"hidden": True}, {"startup": True}):
        stub, raise_event = _stub(**kwargs)
        assert SettingsPlugin._api_setting_reset(stub, PID, "foo") is True
        assert stub.values["foo"] == 7
        raise_event.assert_not_called()

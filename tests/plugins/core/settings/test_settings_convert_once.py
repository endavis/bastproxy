"""Tests for converting a setting once, in add and set, not in get (#428)."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.plugins.core.settings import validate_port
from bastproxy.plugins.core.settings.libs._settinginfo import SettingInfo
from bastproxy.plugins.core.settings.plugin._settings import SettingsPlugin
from bastproxy.plugins.core.utils.plugin._utils import CONVERTERS

PID = "plugins.test.a"


def _stub(stored: dict[str, Any] | None = None) -> MagicMock:
    stub = MagicMock()
    stub.plugin_id = "plugins.core.settings"
    stub.settings_map = {}
    stub.settings_info = {}
    stub.settings_values = {PID: dict(stored or {})}
    stub.verify_calls = 0
    stub._convert_and_validate = lambda *a: SettingsPlugin._convert_and_validate(stub, *a)

    def verify(value: Any, vtype: Any) -> Any:
        stub.verify_calls += 1
        return CONVERTERS[vtype](value)

    def api(name: str) -> Any:
        if name == "libs.api:api.exists":
            return lambda _n: True
        if name == "plugins.core.utils:value.verify":
            return verify
        if name == "libs.plugins.loader:plugin.is.loaded":
            return lambda _n: True
        if name == "plugins.core.settings:setting.get":
            return lambda pid, s: SettingsPlugin._api_setting_get(stub, pid, s)
        if name == "plugins.core.settings:setting.is.hidden":
            return lambda *_a: False
        return lambda *a, **k: False

    stub.api = api
    stub.api.startup = True
    return stub


def _add(stub: MagicMock, default: Any, stype: Any, **kwargs: Any) -> None:
    SettingsPlugin._api_setting_add(stub, PID, "foo", default, stype, "help", **kwargs)


def test_string_default_is_converted() -> None:
    stub = _stub()
    _add(stub, "True", bool)
    assert stub.settings_info[PID]["foo"].default is True
    assert stub.settings_values[PID]["foo"] is True


def test_stored_values_are_converted() -> None:
    stub = _stub({"foo": "5"})
    _add(stub, 1, int)
    assert stub.settings_values[PID]["foo"] == 5
    stub = _stub({"foo": "False"})
    _add(stub, True, bool)
    assert stub.settings_values[PID]["foo"] is False


def test_invalid_stored_bool_falls_back_with_warning(caplog: pytest.LogCaptureFixture) -> None:
    stub = _stub({"foo": "maybe"})
    with caplog.at_level("WARNING"):
        _add(stub, True, bool)
    assert stub.settings_values[PID]["foo"] is True


def test_invalid_stored_port_falls_back() -> None:
    stub = _stub({"foo": 99999})
    _add(stub, 9999, int, validator=validate_port)
    assert stub.settings_values[PID]["foo"] == 9999


def test_get_never_calls_verify() -> None:
    stub = _stub({"foo": 3})
    stub.settings_info = {PID: {"foo": SettingInfo("foo", 1, "h", int)}}
    assert SettingsPlugin._api_setting_get(stub, PID, "foo") == 3
    assert stub.verify_calls == 0


def test_get_unknown_returns_none() -> None:
    stub = _stub()
    assert SettingsPlugin._api_setting_get(stub, PID, "nope") is None
    assert SettingsPlugin._api_setting_get(stub, "other", "foo") is None


def test_get_returns_a_copy_of_a_list() -> None:
    stub = _stub({"foo": ["a"]})
    got = SettingsPlugin._api_setting_get(stub, PID, "foo")
    got.append("b")
    assert stub.settings_values[PID]["foo"] == ["a"]


def test_set_converts_and_rejects() -> None:
    stub = _stub({"foo": False})
    stub.settings_values[PID] = _SyncDict(stub.settings_values[PID])
    stub.settings_info = {PID: {"foo": SettingInfo("foo", False, "h", bool)}}
    assert SettingsPlugin._api_setting_set(stub, PID, "foo", "on") is True
    assert stub.settings_values[PID]["foo"] is True
    with pytest.raises(ValueError):
        SettingsPlugin._api_setting_set(stub, PID, "foo", "maybe")
    assert stub.settings_values[PID]["foo"] is True


class _SyncDict(dict):
    def sync(self) -> None:
        """Do nothing."""

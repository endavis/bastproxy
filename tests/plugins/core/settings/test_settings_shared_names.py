"""Tests for setting names shared by several plugins (#609)."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins._baseplugin import BasePlugin
from bastproxy.plugins.core.commands import CommandResult
from bastproxy.plugins.core.settings.plugin._settings import SettingsPlugin

A = "plugins.test.a"
B = "plugins.test.b"


class _Values(dict[str, Any]):
    def close(self) -> None:
        pass

    def sync(self) -> None:
        pass


def _info(name: str, hidden: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        default=1,
        hidden=hidden,
        readonly=False,
        stype="int",
        aftersetmessage="",
        nocolor=False,
    )


def _stub() -> MagicMock:
    stub = MagicMock()
    stub.plugin_id = "plugins.core.settings"
    stub.settings_map = {}
    stub.settings_info = {}
    stub.settings_values = {A: _Values(), B: _Values()}
    stub._convert_and_validate = lambda _pid, _info, value: value
    stub.format_setting_for_print.return_value = "5"
    stub.calls = []

    def api(name: str) -> Any:
        if name.endswith(":data.directory.get"):
            return MagicMock()
        if name == "plugins.core.settings:setting.info.get":
            return lambda pid, s: stub.settings_info.get(pid, {}).get(s)
        if name == "plugins.core.settings:setting.set":
            return lambda pid, s, v: stub.calls.append(("set", pid, s, v))
        if name == "plugins.core.settings:setting.reset":
            return lambda pid, s: stub.calls.append(("reset", pid, s))
        return MagicMock()

    stub.api = api
    return stub


def _add(stub: MagicMock, pid: str, name: str, **kwargs: Any) -> None:
    SettingsPlugin._api_setting_add(stub, pid, name, 1, int, "help", **kwargs)


def test_two_plugins_share_a_name() -> None:
    stub = _stub()
    _add(stub, A, "foo")
    _add(stub, B, "foo")
    assert stub.settings_map == {"foo": [A, B]}
    assert stub.settings_values[A]["foo"] == 1
    assert stub.settings_values[B]["foo"] == 1
    assert "foo" in stub.settings_info[A]
    assert "foo" in stub.settings_info[B]


def test_hidden_not_indexed() -> None:
    stub = _stub()
    _add(stub, A, "foo", hidden=True)
    assert stub.settings_map == {}
    assert "foo" in stub.settings_info[A]


def test_map_add_appends_without_duplicates() -> None:
    stub = _stub()
    SettingsPlugin._api_setting_map_add(stub, A, "foo")
    SettingsPlugin._api_setting_map_add(stub, B, "foo")
    SettingsPlugin._api_setting_map_add(stub, B, "foo")
    assert stub.settings_map == {"foo": [A, B]}


def test_remove_for_plugin_keeps_other_owner() -> None:
    stub = _stub()
    _add(stub, A, "foo")
    _add(stub, B, "foo")
    _add(stub, A, "only_a")
    SettingsPlugin._api_setting_remove_for_plugin(stub, A)
    assert stub.settings_map == {"foo": [B]}
    SettingsPlugin._api_setting_remove_for_plugin(stub, B)
    assert stub.settings_map == {}


def test_set_from_user_unique_name_resolves() -> None:
    stub = _stub()
    _add(stub, A, "foo")
    result = SettingsPlugin._api_setting_set_from_user(stub, "foo", "5")
    assert result[1] == [f"{A} : foo is now set to 5"]
    assert stub.calls == [("set", A, "foo", "5")]


def test_set_from_user_shared_name_without_plugin_changes_nothing() -> None:
    stub = _stub()
    _add(stub, A, "foo")
    _add(stub, B, "foo")
    for kwargs in ({}, {"reset": True}):
        value = None if kwargs else "5"
        _, msg = SettingsPlugin._api_setting_set_from_user(stub, "foo", value, **kwargs)
        assert msg == [f"foo exists in several plugins: {A}, {B}; use -p <plugin>"]
    assert stub.calls == []


def test_set_from_user_shared_name_with_plugin_changes_only_that_plugin() -> None:
    stub = _stub()
    _add(stub, A, "foo")
    _add(stub, B, "foo")
    SettingsPlugin._api_setting_set_from_user(stub, "foo", "5", B)
    SettingsPlugin._api_setting_set_from_user(stub, "foo", None, A, reset=True)
    assert stub.calls == [("set", B, "foo", "5"), ("reset", A, "foo")]


def test_unknown_name_does_not_exist() -> None:
    stub = _stub()
    _, msg = SettingsPlugin._api_setting_set_from_user(stub, "nope", "5")
    assert msg == ["plugin setting nope does not exist"]


def test_per_plugin_set_command_changes_only_its_plugin() -> None:
    stub = _stub()
    _add(stub, A, "foo")
    _add(stub, B, "foo")

    class _Args(dict[str, Any]):
        arg_string = "foo 5"

    class _Plugin(BasePlugin):
        def __init__(self, pid: str) -> None:
            self.plugin_id = pid

            def api(name: str) -> Any:
                if name == "plugins.core.commands:command.current.args.get":
                    return lambda: _Args(name="foo", value="5", plugin=pid)
                if name.endswith(":setting.set.from.user"):
                    return lambda *a, **k: SettingsPlugin._api_setting_set_from_user(stub, *a, **k)
                return MagicMock()

            self.api = MagicMock(side_effect=api)

    result = _Plugin(B)._command_settings_plugin_set()
    assert isinstance(result, CommandResult)
    assert stub.calls == [("set", B, "foo", "5")]

"""Tests for the settings plugin cleanup (#611)."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins.core.settings.plugin._settings import SettingsPlugin


def _list_stub(infos: dict[str, Any]) -> MagicMock:
    stub = MagicMock()
    stub.plugin_id = "plugins.core.settings"
    plugin = "plugins.test.a"

    def api(name: str) -> Any:
        if name == "plugins.core.commands:command.current.args.get":
            return lambda: {"plugin": "", "search": ""}
        if name == "plugins.core.commands:output.line.length.get":
            return lambda: 20
        if name == "plugins.core.settings:setting.get":
            return lambda *_a: ""
        if name == "libs.plugins.loader:plugin.list.loaded":
            return lambda: [plugin]
        if name == "plugins.core.settings:setting.list":
            return lambda _p: infos
        if name == "plugins.core.settings:setting.format":
            return lambda _p, s: f"{s} : value"
        return MagicMock()

    stub.api = api
    return stub


def test_settings_list_shows_readonly_marked() -> None:
    infos = {
        "rw": SimpleNamespace(readonly=False),
        "ro": SimpleNamespace(readonly=True),
    }
    result = SettingsPlugin._command_list(_list_stub(infos))
    lines = [line for line in result.message if "plugins.test.a" in line]
    assert any("rw : value" in line and "(readonly)" not in line for line in lines)
    assert any("ro : value" in line and "(readonly)" in line for line in lines)


def _format_stub(value: Any, **info: Any) -> MagicMock:
    stub = MagicMock()
    stub.plugin_id = "plugins.core.settings"
    setting_info = SimpleNamespace(nocolor=True, stype="int", **info)

    def api(name: str) -> Any:
        if name.endswith(":setting.get"):
            return lambda _p, _s: value
        if name.endswith(":setting.info.get"):
            return lambda _p, _s: setting_info
        return MagicMock()

    stub.api = api
    return stub


def test_format_nocolor_non_string_value() -> None:
    assert SettingsPlugin.format_setting_for_print(_format_stub(5), "p", "s") == "5"


def test_format_nocolor_string_escapes_at() -> None:
    assert SettingsPlugin.format_setting_for_print(_format_stub("a@b"), "p", "s") == "a@@b"


def test_failed_set_from_user_is_a_failed_command_result() -> None:
    """Both set commands pass a failure from setting.set.from.user through (#611)."""
    from bastproxy.plugins._baseplugin import BasePlugin
    from bastproxy.plugins.core.commands import CommandResult

    failure = (False, ["foo is a readonly setting"])
    apis = {
        "plugins.core.commands:command.current.args.get": lambda: {
            "name": "foo",
            "value": "5",
            "plugin": "plugins.test.stub",
        },
        "plugins.core.settings:setting.set.from.user": lambda *_a, **_k: failure,
    }
    expected = CommandResult(False, ["foo is a readonly setting"])

    base = MagicMock()
    base.plugin_id = "plugins.test.stub"
    base.api = lambda name: apis[name]
    assert BasePlugin._command_settings_plugin_set(base) == expected

    settings = MagicMock()
    settings.plugin_id = "plugins.core.settings"
    settings.api = lambda name: apis[name]
    assert SettingsPlugin._command_settings_plugin_sets(settings) == expected


def test_shared_setting_name_without_plugin_is_a_failure() -> None:
    owners = ["plugins.test.a", "plugins.test.b"]
    stub = MagicMock()
    stub.settings_map = {"foo": owners}
    for value, reset in (("5", False), (None, True)):
        success, msg = SettingsPlugin._api_setting_set_from_user(stub, "foo", value, reset=reset)
        assert success is False
        assert msg == [f"foo exists in several plugins: {', '.join(owners)}; use -p <plugin>"]

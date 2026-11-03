"""Tests for the Settings mixin on BasePlugin (#131)."""

import importlib.util
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import bastproxy.plugins._baseplugin as baseplugin_pkg
from bastproxy.libs.plugins.plugininfo import PluginInfo
from bastproxy.plugins._baseplugin import BasePlugin
from bastproxy.plugins._baseplugin.libs._commands import Commands
from bastproxy.plugins._baseplugin.libs._settings import Settings
from bastproxy.plugins.core.commands.plugin._commands import CommandsPlugin
from bastproxy.plugins.core.events.plugin._events import EventsPlugin

INIT_API = "plugins.core.settings:initialize.plugin.settings"


class _Stub(BasePlugin):
    """A BasePlugin that skips __init__."""

    def __init__(self, apis: dict[str, Callable[..., Any]]) -> None:
        self.plugin_id = "plugins.test.stub"
        self.api = MagicMock(side_effect=lambda name: apis.get(name, MagicMock()))


def test_methods_defined_on_settings_mixin() -> None:
    assert Settings in BasePlugin.__mro__
    assert BasePlugin._command_settings_plugin_set.__qualname__.startswith("Settings.")
    assert BasePlugin._phook_settings_post_initialize.__qualname__.startswith("Settings.")


def test_command_help_not_clobbered() -> None:
    assert BasePlugin._command_help is Commands._command_help


def test_hook_registered_at_priority_75() -> None:
    hooks = _Stub({})._api_get_plugin_hooks()["initialize"]
    assert [f.__name__ for f in hooks[75]] == ["_phook_settings_post_initialize"]
    assert {1, 50, 90, 91} <= set(hooks)


def test_set_command_data() -> None:
    command = BasePlugin._command_settings_plugin_set.command_data.command
    assert command["name"] == "set"
    assert command["kwargs"]["group"] == "Base"
    assert command["kwargs"]["show_in_history"] is False


def test_hook_initializes_settings() -> None:
    init = MagicMock()
    stub: Any = _Stub({"libs.api:has": lambda _n: True, INIT_API: init})
    stub._phook_settings_post_initialize()
    init.assert_called_once_with("plugins.test.stub")
    assert stub.reset_f is False


def test_hook_without_settings_plugin_is_a_noop() -> None:
    init = MagicMock()
    stub: Any = _Stub({"libs.api:has": lambda _n: False, INIT_API: init})
    stub._phook_settings_post_initialize()
    init.assert_not_called()
    assert stub.reset_f is False


class _Args(dict):
    arg_string = ""

    def __init__(self, name: str) -> None:
        super().__init__(name=name, value="")
        self.arg_string = f"{name} 5"


def test_set_list_returns_formatted_settings() -> None:
    for name in ("", "list"):
        stub = _Stub(
            {
                "plugins.core.commands:get.current.command.args": lambda n=name: _Args(n),
                "plugins.core.settings:get.all.settings.formatted": lambda pid: f"fmt {pid}",
            }
        )
        assert stub._command_settings_plugin_set() == (True, "fmt plugins.test.stub")


def test_set_with_name_runs_pset() -> None:
    run = MagicMock(return_value=(True, "done"))
    stub = _Stub(
        {
            "plugins.core.commands:get.current.command.args": lambda: _Args("foo"),
            "plugins.core.commands:run": run,
        }
    )
    assert stub._command_settings_plugin_set() == (True, "done")
    run.assert_called_once_with(
        "plugins.core.settings", "pset", argument_string="-p plugins.test.stub foo 5"
    )


def test_patch_machinery_removed() -> None:
    assert "patch" not in baseplugin_pkg.__all__
    assert not hasattr(baseplugin_pkg, "patch")
    assert importlib.util.find_spec("bastproxy.plugins._baseplugin._patch") is None
    assert not hasattr(PluginInfo("plugins.x"), "has_been_reloaded")
    assert not hasattr(EventsPlugin, "_eventcb_baseplugin_patched")
    assert not hasattr(CommandsPlugin, "_eventcb_commands_baseplugin_patched")

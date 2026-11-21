"""The debug plugins commands refuse a plugin that is not loaded (#684)."""

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.plugins.debug.plugins.plugin._plugins import PluginsPlugin

LOADED = ["plugins.test.a"]
COMMANDS = ["_command_dump", "_command_hooks", "_command_summary", "_command_detail"]


def _run(command: str, plugin: str) -> tuple[Any, list[str]]:
    stub = MagicMock()
    requested: list[str] = []

    def api(name: str) -> Callable[..., Any]:
        requested.append(name)
        if name == "plugins.core.commands:command.current.args.get":
            return lambda: {"plugin": plugin, "object": "", "detailed": False}
        if name == "libs.plugins.loader:plugin.list.loaded":
            return lambda: LOADED
        if name == "plugins.core.commands:output.header.format":
            return lambda title: [f"== {title} =="]
        if name == "libs.api:api.exists":
            return lambda _api: False
        if name.endswith(":plugin.dump"):
            return lambda *_: (True, ["x"])
        if name.endswith(":plugin.hook.list"):
            return lambda: {}
        raise AssertionError(name)

    stub.api = api
    return getattr(PluginsPlugin, command)(stub), requested


@pytest.mark.parametrize("command", COMMANDS)
@pytest.mark.parametrize("plugin", ["plugins.nosuch", "plugins.debug.api"])
def test_plugin_not_loaded_fails(command: str, plugin: str) -> None:
    result, requested = _run(command, plugin)
    assert result.success is False
    assert result.message == [f"Plugin {plugin} is not loaded"]
    assert not any(name.startswith(f"{plugin}:") for name in requested)
    assert not any(name.endswith((":plugin.dump", ":plugin.hook.list")) for name in requested)


def test_dump_loaded_plugin_reaches_api() -> None:
    result, requested = _run("_command_dump", "plugins.test.a")
    assert result.success is True
    assert "plugins.test.a:plugin.dump" in requested


def test_hooks_loaded_plugin_reaches_api() -> None:
    result, requested = _run("_command_hooks", "plugins.test.a")
    assert result.success is True
    assert "plugins.test.a:plugin.hook.list" in requested

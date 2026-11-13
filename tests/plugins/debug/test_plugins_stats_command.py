"""Tests for the debug plugins stats command (#466)."""

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins.debug.plugins.plugin._plugins import PluginsPlugin


def _run(plugin: str, loaded: list[str], sections: dict[str, Any]) -> tuple[Any, list[str]]:
    stub = MagicMock()
    requested: list[str] = []

    def api(name: str) -> Callable[..., Any]:
        requested.append(name)
        if name == "plugins.core.commands:command.current.args.get":
            return lambda: {"plugin": plugin}
        if name == "libs.plugins.loader:plugin.list.loaded":
            return lambda: loaded
        if name == "plugins.core.commands:output.header.format":
            return lambda title: [f"== {title} =="]
        if name.endswith(":plugin.stats.get"):
            return lambda: sections
        raise AssertionError(name)

    stub.api = api
    return PluginsPlugin._command_stats(stub), requested


def test_missing_plugin_name_fails() -> None:
    result, _ = _run("", ["plugins.test.a"], {})
    assert result.success is False


def test_unknown_plugin_fails() -> None:
    result, requested = _run("plugins.test.zz", ["plugins.test.a"], {})
    assert result.success is False
    assert "plugins.test.zz:plugin.stats.get" not in requested


def test_no_sections() -> None:
    result, _ = _run("plugins.test.a", ["plugins.test.a"], {})
    assert result.success is True
    assert result.message == ["No stats for plugins.test.a"]


def test_output_follows_showorder() -> None:
    sections = {"Sec": {"showorder": ["B", "A"], "A": 1, "B": 2}}
    result, _ = _run("plugins.test.a", ["plugins.test.a"], sections)
    assert result.success is True
    assert result.message == ["== Sec ==", f"{'B':<20} : 2", f"{'A':<20} : 1", ""]

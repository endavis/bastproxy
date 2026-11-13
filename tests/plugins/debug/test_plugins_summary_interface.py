"""Tests for the summary/detail interface names between debug/plugins and its providers (#166)."""

import ast
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.plugins.core.commands.plugin import _commands
from bastproxy.plugins.core.events.plugin import _events
from bastproxy.plugins.debug.plugins.plugin._plugins import PluginsPlugin

NEW_NAMES = {"summary.get.for.plugin", "detail.get.for.plugin"}
OLD_NAMES = {"get.summary.data.for.plugin", "get.detailed.data.for.plugin"}


def _registered_api_names(module: Any) -> set[str]:
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "AddAPI"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            names.add(node.args[0].value)
    return names


@pytest.mark.parametrize("module", [_commands, _events])
def test_providers_register_new_names_only(module: Any) -> None:
    registered = _registered_api_names(module)
    assert registered >= NEW_NAMES
    assert not OLD_NAMES & registered


@pytest.mark.parametrize(
    ("command", "expected"),
    [("_command_summary", "summary.get.for.plugin"), ("_command_detail", "detail.get.for.plugin")],
)
def test_debug_plugins_requests_new_names(command: str, expected: str) -> None:
    requested: list[str] = []
    stub = MagicMock()
    stub.api.side_effect = lambda name: _fake_api(name, requested)

    result = getattr(PluginsPlugin, command)(stub)

    assert result.success is True
    assert f"plugins.test.a:{expected}" in requested


def _fake_api(name: str, requested: list[str]) -> Any:
    requested.append(name)
    if name == "plugins.core.commands:command.current.args.get":
        return lambda: {"plugin": "x"}
    if name == "libs.plugins.loader:plugin.list.loaded":
        return lambda: ["plugins.test.a"]
    if name == "libs.api:api.exists":
        return lambda api: True
    if name == "plugins.core.commands:output.header.format":
        return lambda *a: ["H"]
    return lambda *a: ["data"]

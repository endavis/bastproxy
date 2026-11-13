"""Tests for cmdprefix validation and prefix stripping (#399)."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.plugins.core.commands.plugin._commands import (
    CommandSplit,
    CommandsPlugin,
    validate_cmdprefix,
)


@pytest.mark.parametrize("value", ["#bp", "@@", "bp!"])
def test_valid_prefix(value: str) -> None:
    assert validate_cmdprefix(value) == ""


@pytest.mark.parametrize("value", ["#bp.x", ".", "#b p", "#bp ", "\t#bp", "#", ""])
def test_invalid_prefix(value: str) -> None:
    assert validate_cmdprefix(value) != ""


def _split(prefix: str, command: str) -> tuple[CommandSplit, list[str], MagicMock]:
    seen = MagicMock(return_value=("plugins.core", "commands"))

    def api(name: str) -> Any:
        if name == "plugins.core.settings:setting.get":
            return lambda pid, key: prefix
        if name == "libs.plugins.loader:plugin.id.match":
            return seen
        raise AssertionError(name)

    stub = MagicMock()
    stub.plugin_id = "plugins.core.commands"
    stub.api = api
    result = CommandsPlugin.find_command_split_command_string(stub, command)
    return result, result.parts, seen


def test_split_strips_prefix_before_splitting() -> None:
    result, split, seen = _split("#bp", "#bp.core.commands.list arg")
    assert split == ["core", "commands", "list"]
    assert result.args == "arg"
    seen.assert_called_once_with("core.commands", active_only=True)


def test_split_handles_plugins_literal() -> None:
    _, split, _ = _split("#bp", "#bp.plugins.core.commands.list")
    assert split == ["core", "commands", "list"]


def test_split_without_prefix_unchanged() -> None:
    _, split, _ = _split("#bp", "core.commands.list")
    assert split == ["core", "commands", "list"]

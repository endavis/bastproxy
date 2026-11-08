"""Tests for command data removal on plugin unload (#96)."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins.core.commands.plugin._commands import CommandsPlugin

PID = "plugins.test.a"
SIBLING = "plugins.test.ab"


def _stub() -> MagicMock:
    """Build a stub commands plugin with real containers."""
    stub = MagicMock()
    stub.plugin_id = "plugins.core.commands"
    stub.api = MagicMock()
    stub.api.startup = True
    stub.api.side_effect = lambda name: lambda *a, **k: True
    stub.command_data = {}
    stub.commands_list = []
    stub.saved_command_counts = {}
    return stub


def _cmd(count: int = 0) -> Any:
    return SimpleNamespace(count=count)


def _populate(stub: MagicMock) -> None:
    stub.command_data[PID] = {"x": _cmd(3), "y": _cmd(5)}
    stub.command_data[SIBLING] = {"x": _cmd(7)}
    stub.commands_list.extend([f"{PID}.x", f"{PID}.y", f"{SIBLING}.x"])


def test_remove_data_clears_data_and_list() -> None:
    """Unload drops the plugin's command_data and commands_list entries."""
    stub = _stub()
    _populate(stub)

    CommandsPlugin._api_command_remove_for_plugin(stub, PID)

    assert PID not in stub.command_data
    assert stub.commands_list == [f"{SIBLING}.x"]
    assert stub.saved_command_counts == {PID: {"x": 3, "y": 5}}


def test_remove_data_leaves_prefix_sibling_untouched() -> None:
    """A plugin id sharing a prefix keeps its data."""
    stub = _stub()
    _populate(stub)

    CommandsPlugin._api_command_remove_for_plugin(stub, PID)

    assert stub.command_data[SIBLING]["x"].count == 7
    assert f"{SIBLING}.x" in stub.commands_list
    assert SIBLING not in stub.saved_command_counts


def test_update_command_after_unload_restores_count() -> None:
    """A redefined command gets its old count; an undefined one stays absent."""
    stub = _stub()
    _populate(stub)
    CommandsPlugin._api_command_remove_for_plugin(stub, PID)

    new = _cmd()
    CommandsPlugin.update_command(stub, PID, "x", new)

    assert new.count == 3
    assert set(stub.command_data[PID]) == {"x"}
    assert stub.saved_command_counts == {PID: {"y": 5}}


def test_saved_entry_dropped_when_empty() -> None:
    """The plugin's saved entry is removed once all counts are restored."""
    stub = _stub()
    stub.command_data[PID] = {"x": _cmd(3)}
    CommandsPlugin._api_command_remove_for_plugin(stub, PID)

    CommandsPlugin.update_command(stub, PID, "x", _cmd())

    assert PID not in stub.saved_command_counts


def test_reload_without_unload_carries_count() -> None:
    """Replacing a live command copies its count in place."""
    stub = _stub()
    stub.command_data[PID] = {"x": _cmd(4)}

    new = _cmd()
    CommandsPlugin.update_command(stub, PID, "x", new)

    assert new.count == 4
    assert stub.command_data[PID]["x"] is new

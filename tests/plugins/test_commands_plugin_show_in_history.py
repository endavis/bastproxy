"""Tests that a command's show_in_history setting is honoured (#388)."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from bastproxy.libs.records.rtypes.networkdata import NetworkDataLine
from bastproxy.plugins.core.commands.plugin._commands import CommandsPlugin


class _Record(dict):
    """Event-record stand-in with the `addupdate` method."""

    def addupdate(self, *args: Any, **kwargs: Any) -> None:
        """Ignore updates."""


def _stub() -> MagicMock:
    """Build a plugin stub that can find `hist` (shown) and `nohist` (hidden)."""
    data = {
        "hist": SimpleNamespace(full_cmd="p.hist", show_in_history=True),
        "nohist": SimpleNamespace(full_cmd="p.nohist", show_in_history=False),
    }

    def api(name: str) -> Any:
        if name.endswith("setting.get"):
            return lambda plugin_id, key: "#bp"
        if name.endswith("command.data.get"):
            return lambda plugin: data
        if name.endswith("string.match.best"):
            return lambda text, choices, scorer=None: text if text in choices else None
        raise AssertionError(name)

    stub = MagicMock()
    stub.plugin_id = "plugins.core.commands"
    stub.api = api
    stub.find_command_split_command_string.side_effect = lambda s: (
        True,
        "pkg",
        "pkg.p",
        "",
        ["pkg", "p", s.split(" ")[0]],
        "",
    )
    stub.error_command_not_found_in_plugin.return_value = ["not found"]
    return stub


def test_find_command_false_for_hidden_command() -> None:
    """A command with show_in_history=False is reported as not shown."""
    assert CommandsPlugin.find_command(_stub(), "nohist")[2] is False


def test_find_command_true_for_shown_command() -> None:
    """A command with show_in_history=True is reported as shown."""
    assert CommandsPlugin.find_command(_stub(), "hist")[2] is True


def test_find_command_unknown_command_false() -> None:
    """An unknown command is not shown in history."""
    assert CommandsPlugin.find_command(_stub(), "nope")[2] is False


def test_run_internal_command_sets_showinhistory() -> None:
    """The event record's showinhistory follows find_command's value."""
    line = NetworkDataLine("#bp.p.nohist", originated="client")
    record: Any = _Record({"line": line, "client_id": None, "showinhistory": True})
    stub = MagicMock()
    stub.plugin_id = "plugins.core.commands"
    stub.api = lambda name: lambda: record
    stub.find_command.return_value = (None, "", False, "", [])

    CommandsPlugin.run_internal_command_from_event(stub)

    assert record["showinhistory"] is False

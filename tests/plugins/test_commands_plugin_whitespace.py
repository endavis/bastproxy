"""Tests for leading-whitespace handling in the commands plugin (#52)."""

from typing import Any
from unittest.mock import MagicMock

from bastproxy.libs.records.rtypes.networkdata import NetworkDataLine
from bastproxy.plugins.core.commands.plugin._commands import CommandLookup, CommandsPlugin


class _Record(dict):
    """Event-record stand-in with the `addupdate` method."""

    def addupdate(self, *args: Any, **kwargs: Any) -> None:
        """Ignore updates."""


def _run(text: str) -> MagicMock:
    """Run `_eventcb_check_for_command` for `text`; return the stub plugin."""
    line = NetworkDataLine(text, originated="client")
    record: dict[str, Any] = {"line": line, "showinhistory": False}

    def api(name: str) -> Any:
        if name == "plugins.core.settings:setting.get":
            return lambda plugin_id, key: "#bp"
        if name == "plugins.core.events:event.current.record.get":
            return lambda: record
        raise AssertionError(name)

    stub = MagicMock()
    stub.plugin_id = "plugins.core.commands"
    stub.api = api
    stub.current_input_event = None
    CommandsPlugin._eventcb_check_for_command(stub)
    return stub


def test_indented_proxy_command_is_recognized() -> None:
    """`  #bp.foo` is run as a proxy command, not passed to the MUD."""
    stub = _run("  #bp.foo")

    stub.run_internal_command_from_event.assert_called_once()
    stub.pass_through_command_from_event.assert_not_called()


def test_indented_non_command_passes_through_unchanged() -> None:
    """An indented MUD line is passed through and its whitespace is kept."""
    stub = _run("  look")

    stub.pass_through_command_from_event.assert_called_once()
    stub.run_internal_command_from_event.assert_not_called()


def test_indented_command_is_parsed_like_unindented() -> None:
    """find_command receives the left-stripped text for an indented command."""
    line = NetworkDataLine("  #bp.foo arg", originated="client")
    record: Any = _Record({"line": line, "client_id": None, "showinhistory": False})
    stub = MagicMock()
    stub.plugin_id = "plugins.core.commands"
    stub.api = lambda name: lambda: record
    stub.find_command.return_value = CommandLookup(None, "", False, "", [])

    CommandsPlugin.run_internal_command_from_event(stub)

    stub.find_command.assert_called_once_with("#bp.foo arg")
    assert line.line == "  #bp.foo arg"

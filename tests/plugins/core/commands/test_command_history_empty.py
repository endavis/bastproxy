"""The history command says so when the history is empty (#701)."""

from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins.core.commands.plugin._commands import CommandsPlugin


class _HistoryDict(dict[str, Any]):
    """A dict with the sync() the persistent dict offers."""

    def sync(self) -> None:
        """Do nothing; there is no file."""


def _stub(history: list[str], clear: bool = False) -> MagicMock:
    stub = MagicMock()
    stub.command_history_data = history
    stub.command_history_dict = _HistoryDict(history=history)

    def api(name: str) -> Any:
        if name == "plugins.core.commands:command.current.args.get":
            return lambda: {"clear": clear}
        raise AssertionError(name)

    stub.api = api
    return stub


def test_empty_history_shows_message() -> None:
    result = CommandsPlugin._command_history(_stub([]))
    assert result.success is True
    assert result.message == ["No commands in history"]


def test_history_lists_numbered_entries() -> None:
    result = CommandsPlugin._command_history(_stub(["a", "b"]))
    assert result.message == ["0 : a", "1 : b"]


def test_clear_reports_cleared() -> None:
    stub = _stub(["a"], clear=True)
    result = CommandsPlugin._command_history(stub)
    assert result.message == ["Command history cleared"]
    assert stub.command_history_dict["history"] == []

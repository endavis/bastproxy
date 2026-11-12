"""Command history keeps historysize entries and `!` indexes them consistently (#395)."""

from typing import Any
from unittest.mock import MagicMock, patch

from bastproxy.plugins.core.commands.plugin import _commands
from bastproxy.plugins.core.commands.plugin._commands import CommandsPlugin

PID = "plugins.core.commands"


def _stub(history: list[str], historysize: int = 5, client_id: str | None = "c1") -> MagicMock:
    stub = MagicMock()
    stub.plugin_id = PID
    stub.command_history_data = history
    stub.args = {"number": 0}

    def api(name: str) -> Any:
        if name == "plugins.core.settings:setting.get":
            return lambda _pid, _setting: historysize
        if name == "plugins.core.commands:command.current.args.get":
            return lambda: stub.args
        if name == "plugins.core.events:event.current.record.get":
            return lambda: {"client_id": client_id} if client_id is not None else None
        raise AssertionError(name)

    stub.api = api
    return stub


def _run(stub: MagicMock, number: int) -> tuple[Any, list[str], MagicMock]:
    stub.args = {"number": number}
    with patch.object(_commands, "SendDataDirectlyToClient") as sender:
        ok, msg = CommandsPlugin._command_run_history(stub)
    return ok, msg, sender


def test_history_keeps_exactly_historysize() -> None:
    stub = _stub([], historysize=3)
    for cmd in ("a", "b", "c", "d"):
        CommandsPlugin.add_command_to_history(stub, cmd)
    assert stub.command_history_data == ["b", "c", "d"]


def test_history_not_trimmed_below_size() -> None:
    stub = _stub([], historysize=3)
    for cmd in ("a", "b", "c"):
        CommandsPlugin.add_command_to_history(stub, cmd)
    assert stub.command_history_data == ["a", "b", "c"]


def test_history_dedupe_moves_to_end() -> None:
    stub = _stub([], historysize=3)
    for cmd in ("a", "b", "a"):
        CommandsPlugin.add_command_to_history(stub, cmd)
    assert stub.command_history_data == ["b", "a"]


def _run_capture(stub: MagicMock, number: int) -> tuple[list[str], list[Any]]:
    stub.args = {"number": number}
    captured: list[Any] = []

    def fake_network_data(lines: list[str], owner_id: str = "") -> Any:
        return lines

    with (
        patch.object(_commands, "SendDataDirectlyToClient") as sender,
        patch.object(_commands, "NetworkData", side_effect=fake_network_data),
    ):
        ok, msg = CommandsPlugin._command_run_history(stub)
        assert ok is True
        captured = list(sender.call_args_list)
    return msg, captured


def test_bang_index_with_full_history_shows_fifth() -> None:
    stub = _stub(["a", "b", "c", "d", "e"], historysize=5)
    msg, calls = _run_capture(stub, 4)
    assert msg == []
    assert calls[1].args[0] == ["e"]


def test_bang_zero_shows_first() -> None:
    stub = _stub(["a", "b", "c", "d", "e"], historysize=5)
    _, calls = _run_capture(stub, 0)
    assert calls[1].args[0] == ["a"]


def test_bang_negative_one_full_and_not_full() -> None:
    full = _stub(["a", "b", "c"], historysize=3)
    _, calls = _run_capture(full, -1)
    assert calls[1].args[0] == ["c"]
    partial = _stub(["a", "b", "c"], historysize=10)
    _, calls = _run_capture(partial, -1)
    assert calls[1].args[0] == ["c"]


def test_bang_out_of_range() -> None:
    stub = _stub(["a", "b", "c"], historysize=3)
    for number in (3, -4):
        ok, msg, sender = _run(stub, number)
        assert ok is True
        assert msg == ["# is outside of history length"]
        sender.assert_not_called()


def test_reply_goes_to_originating_client() -> None:
    stub = _stub(["a", "b"], historysize=5, client_id="client-7")
    _, calls = _run_capture(stub, 1)
    assert all(c.kwargs["clients"] == ["client-7"] for c in calls)


def test_reply_without_event_falls_back_to_all_clients() -> None:
    stub = _stub(["a", "b"], historysize=5, client_id=None)
    _, calls = _run_capture(stub, 1)
    assert all(c.kwargs["clients"] is None for c in calls)

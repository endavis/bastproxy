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
    with (
        patch.object(_commands, "SendDataDirectlyToClient") as sender,
        patch.object(_commands, "ProcessDataToMud"),
    ):
        result = CommandsPlugin._command_run_history(stub)
        ok = result.success
        msg = result.message
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


def _run_capture(stub: MagicMock, number: int) -> tuple[list[str], MagicMock]:
    """Run `!`; return its message and the ProcessDataToMud mock (the rerun)."""
    stub.args = {"number": number}

    with (
        patch.object(_commands, "SendDataDirectlyToClient"),
        patch.object(_commands, "ProcessDataToMud") as process,
    ):
        result = CommandsPlugin._command_run_history(stub)
        assert result.success is True
    return result.message, process


def _rerun_line(process: MagicMock) -> str:
    network_data = process.call_args.args[0]
    return str(network_data[0].line)


def test_bang_index_with_full_history_reruns_fifth() -> None:
    stub = _stub(["a", "b", "c", "d", "e"], historysize=5)
    msg, process = _run_capture(stub, 4)
    assert msg == []
    assert _rerun_line(process) == "e"


def test_bang_zero_reruns_first() -> None:
    stub = _stub(["a", "b", "c", "d", "e"], historysize=5)
    _, process = _run_capture(stub, 0)
    assert _rerun_line(process) == "a"


def test_bang_negative_one_full_and_not_full() -> None:
    full = _stub(["a", "b", "c"], historysize=3)
    _, process = _run_capture(full, -1)
    assert _rerun_line(process) == "c"
    partial = _stub(["a", "b", "c"], historysize=10)
    _, process = _run_capture(partial, -1)
    assert _rerun_line(process) == "c"


def test_bang_rerun_is_client_input_of_issuing_client_not_recorded() -> None:
    stub = _stub(["a", "b"], client_id="c9")
    _, process = _run_capture(stub, 0)
    line = process.call_args.args[0][0]
    assert line.fromclient
    assert process.call_args.kwargs == {"show_in_history": False, "client_id": "c9"}
    process.return_value.assert_called_once_with()
    assert stub.command_history_data == ["a", "b"]


def test_bang_notice_record_is_called_with_no_arguments() -> None:
    """The notice record is executed with `()`; `_exec_` takes no arguments."""
    stub = _stub(["a"], client_id="c1")
    stub.args = {"number": 0}
    with (
        patch.object(_commands, "SendDataDirectlyToClient", autospec=True) as sender,
        patch.object(_commands, "ProcessDataToMud"),
    ):
        result = CommandsPlugin._command_run_history(stub)
    assert result.success is True
    sender.return_value.assert_called_once_with()


def test_bang_rerun_without_event_record_has_no_client() -> None:
    stub = _stub(["a"], client_id=None)
    _, process = _run_capture(stub, 0)
    assert process.call_args.kwargs["client_id"] is None


def test_bang_out_of_range() -> None:
    stub = _stub(["a", "b", "c"], historysize=3)
    for number in (3, -4):
        ok, msg, sender = _run(stub, number)
        assert ok is True
        assert msg == ["# is outside of history length"]
        sender.assert_not_called()


def _notice_calls(stub: MagicMock, number: int) -> list[Any]:
    """Run `!`; return the SendDataDirectlyToClient constructor calls (the notice)."""
    stub.args = {"number": number}
    with (
        patch.object(_commands, "SendDataDirectlyToClient") as sender,
        patch.object(_commands, "ProcessDataToMud"),
    ):
        CommandsPlugin._command_run_history(stub)
    return list(sender.call_args_list)


def test_reply_goes_to_originating_client() -> None:
    stub = _stub(["a", "b"], historysize=5, client_id="client-7")
    calls = _notice_calls(stub, 1)
    assert calls
    assert all(c.kwargs["clients"] == ["client-7"] for c in calls)


def test_reply_without_event_falls_back_to_all_clients() -> None:
    stub = _stub(["a", "b"], historysize=5, client_id=None)
    calls = _notice_calls(stub, 1)
    assert calls
    assert all(c.kwargs["clients"] is None for c in calls)

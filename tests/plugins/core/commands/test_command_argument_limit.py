"""Command arguments longer than MAX_ARGUMENT_LENGTH are refused (#699)."""

# Standard Library
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

# 3rd Party
import pytest

# Project
from bastproxy.libs import argp
from bastproxy.plugins.core.commands import CommandResult
from bastproxy.plugins.core.commands.libs import _command
from bastproxy.plugins.core.commands.libs._command import MAX_ARGUMENT_LENGTH, CommandClass
from bastproxy.plugins.core.commands.plugin import _commands
from bastproxy.plugins.core.commands.plugin._commands import CommandsPlugin

from .test_add_by_func_bad_placeholder import _stub_command_class

__all__ = ["_stub_command_class"]


@pytest.fixture(autouse=True)
def _patch_command_module(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_command, "API", MagicMock())
    monkeypatch.setattr(_command, "CmdArgsRecord", lambda owner, data, **kw: dict(data))


def _command_with(ran: list[bool]) -> CommandClass:
    parser = argp.ArgumentParser(add_help=False)
    parser.add_argument("-h", "--help", action="store_true")
    parser.add_argument("text", nargs="?", default="")

    def function() -> CommandResult:
        ran.append(True)
        return CommandResult(True)

    return CommandClass("plugins.test699", "cmd", function, parser, format=False)


def test_limit_value() -> None:
    assert MAX_ARGUMENT_LENGTH == 8192


def test_arguments_at_the_limit_are_parsed() -> None:
    text = "a" * MAX_ARGUMENT_LENGTH
    parsed = _command_with([]).parse_args(text)
    assert parsed.success is True
    assert vars(parsed.args)["text"] == text


def test_arguments_over_the_limit_are_refused_without_splitting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    split = MagicMock()
    monkeypatch.setattr(_command.shlex, "split", split)
    parsed = _command_with([]).parse_args("a" * (MAX_ARGUMENT_LENGTH + 1))
    assert parsed.success is False
    assert parsed.args == {}
    assert "8192" in parsed.message[0]
    split.assert_not_called()


def test_run_with_arguments_over_the_limit_does_not_run_the_command() -> None:
    ran: list[bool] = []
    result = _command_with(ran).run("a" * (MAX_ARGUMENT_LENGTH + 1))
    assert result.success is False
    assert result.reason == "arguments too long"
    assert ran == []


def _line_recorded(args: str, monkeypatch: pytest.MonkeyPatch) -> bool:
    """Send a `#bp` line through the input callback and say if it reached the history."""
    command = _command_with([])
    record = MagicMock()
    data: dict[str, Any] = {
        "line": SimpleNamespace(
            line=f"#bp.x.cmd {args}", internal=False, mask_log=False, send=True
        ),
        "showinhistory": True,
        "client_id": None,
    }
    record.__getitem__.side_effect = data.__getitem__
    record.__setitem__.side_effect = data.__setitem__

    recorded: list[str] = []
    stub = MagicMock()
    stub.plugin_id = "plugins.core.commands"
    stub.current_input_event = None
    stub.add_command_to_history.side_effect = recorded.append
    stub.find_command.return_value = SimpleNamespace(
        command=command, args=args, show_in_history=True, notes="", message=""
    )
    stub.run_internal_command_from_event = lambda: CommandsPlugin.run_internal_command_from_event(
        stub
    )

    def api(name: str) -> Any:
        if name == "plugins.core.settings:setting.get":
            return lambda _pid, _key: "#bp"
        if name == "plugins.core.events:event.current.record.get":
            return lambda: record
        raise AssertionError(name)

    stub.api = api
    monkeypatch.setattr(_commands, "SendDataDirectlyToClient", MagicMock())
    monkeypatch.setattr(_commands, "output_to_client", MagicMock())
    CommandsPlugin._eventcb_check_for_command(stub)
    return bool(recorded)


def test_refused_command_line_is_not_recorded_in_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _line_recorded("a" * (MAX_ARGUMENT_LENGTH + 1), monkeypatch) is False


def test_command_line_at_the_limit_is_recorded_in_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _line_recorded("a" * MAX_ARGUMENT_LENGTH, monkeypatch) is True

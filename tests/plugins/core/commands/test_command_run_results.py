"""The result classes of CommandClass.run and parse_args (#426)."""

import argparse
import dataclasses
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs import argp
from bastproxy.plugins.core.commands import CommandResult
from bastproxy.plugins.core.commands.libs import _command
from bastproxy.plugins.core.commands.libs._command import (
    CommandClass,
    CommandRunResult,
    ParsedArgs,
)
from bastproxy.plugins.core.commands.plugin import _commands
from bastproxy.plugins.core.commands.plugin._commands import CommandLookup, CommandsPlugin


@pytest.fixture(autouse=True)
def _patch_command_module(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_command, "API", MagicMock())
    monkeypatch.setattr(_command, "CmdArgsRecord", lambda owner, data, **kw: dict(data))


def _make(function: Any) -> CommandClass:
    parser = argp.ArgumentParser(add_help=False)
    parser.add_argument("-h", "--help", action="store_true")
    return CommandClass("plugins.test.a", "x", function, parser)


def _raiser() -> None:
    raise ValueError("boom")


def test_field_order_and_slots() -> None:
    assert [f.name for f in dataclasses.fields(CommandRunResult)] == [
        "success",
        "message",
        "reason",
    ]
    assert [f.name for f in dataclasses.fields(ParsedArgs)] == ["success", "args", "message"]
    assert not hasattr(CommandRunResult(True, [], ""), "__dict__")
    assert not hasattr(ParsedArgs(True, {}, []), "__dict__")


def test_run_unclosed_quote() -> None:
    result = _make(lambda: CommandResult(True)).run('"abc')
    assert isinstance(result, CommandRunResult)
    assert result.success is False
    assert result.reason == "could not parse args"
    assert result.message


def test_run_help() -> None:
    result = _make(lambda: CommandResult(True)).run("-h")
    assert isinstance(result, CommandRunResult)
    assert (result.success, result.reason) == (True, "help")


def test_run_exception() -> None:
    result = _make(_raiser).run("")
    assert isinstance(result, CommandRunResult)
    assert (result.success, result.reason) == (False, "function raised an exception")


def test_run_returns_false() -> None:
    result = _make(lambda: CommandResult(False)).run("")
    assert isinstance(result, CommandRunResult)
    assert (result.success, result.reason) == (False, "function returned False")


def test_run_success() -> None:
    result = _make(lambda: CommandResult(True, ["ok"])).run("")
    assert isinstance(result, CommandRunResult)
    assert (result.success, result.message, result.reason) == (
        True,
        ["ok"],
        "command ran successfully",
    )


def test_run_format_failure() -> None:
    cmd = _make(lambda: CommandResult(True))

    def bad(message: list[str]) -> list[str]:
        raise RuntimeError("x")

    cmd.format_return_message = bad  # type: ignore[method-assign]
    result = cmd.run("", format=True)
    assert isinstance(result, CommandRunResult)
    assert (result.success, result.reason) == (False, "could not format output")


def test_parse_args_unclosed_quote() -> None:
    parsed = _make(lambda: CommandResult(True)).parse_args('"abc')
    assert isinstance(parsed, ParsedArgs)
    assert parsed.success is False
    assert parsed.args == {}
    assert isinstance(parsed.message, list)
    assert parsed.message


def test_parse_args_unknown_option() -> None:
    parsed = _make(lambda: CommandResult(True)).parse_args("--nope 1")
    assert parsed.success is False
    assert parsed.args == {}
    assert parsed.message


def test_parse_args_valid() -> None:
    parsed = _make(lambda: CommandResult(True)).parse_args("-h")
    assert parsed.success is True
    assert isinstance(parsed.args, argparse.Namespace)
    assert parsed.message == []


def _plugin_stub(command: Any) -> MagicMock:
    stub = MagicMock()
    stub.plugin_id = "plugins.core.commands"
    stub.get_command_data_from_plugin.return_value = command
    return stub


def test_api_command_run_returns_plain_tuple() -> None:
    command = MagicMock()
    command.run.return_value = CommandRunResult(True, ["x"], "r")
    result = CommandsPlugin._api_command_run(_plugin_stub(command), "plugins.x", "cmd", "")
    assert type(result) is tuple
    assert result == (True, ["x"])


def test_api_command_run_missing_command() -> None:
    result = CommandsPlugin._api_command_run(_plugin_stub(None), "plugins.x", "cmd", "")
    assert type(result) is tuple
    assert result == (None, [])


def test_internal_command_failure_records_reason_and_sends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[Any] = []

    def fake_send(data: Any, clients: Any = None) -> Any:
        sent.append(data)
        return lambda: None

    monkeypatch.setattr(_commands, "SendDataDirectlyToClient", fake_send)
    updates: list[str] = []
    record: Any = MagicMock()
    record.__getitem__.side_effect = lambda key: {
        "client_id": None,
        "showinhistory": True,
        "line": MagicMock(line="#bp.x"),
    }[key]
    record.addupdate.side_effect = lambda flag, text, **kw: updates.append(text)
    command_item = MagicMock()
    command_item.format = False
    command_item.run.return_value = CommandRunResult(False, ["m"], "function returned False")
    stub = MagicMock()
    stub.plugin_id = "plugins.core.commands"
    stub.api = lambda name: lambda: record
    stub.find_command.return_value = CommandLookup(command_item, "", True, "", [])

    CommandsPlugin.run_internal_command_from_event(stub)

    assert "run_command returned error: function returned False" in updates
    assert sent

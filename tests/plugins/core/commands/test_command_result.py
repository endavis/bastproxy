"""CommandResult and how CommandClass.run treats command return values (#426)."""

import dataclasses
import logging
import signal
from typing import Any
from unittest.mock import MagicMock

import pytest

import bastproxy.plugins.core.commands as commands_pkg
from bastproxy.libs import argp
from bastproxy.plugins.core.commands import CommandResult
from bastproxy.plugins.core.commands.libs import _command
from bastproxy.plugins.core.commands.libs._command import CommandClass, CommandRunResult
from bastproxy.plugins.core.commands.plugin import _commands
from bastproxy.plugins.core.commands.plugin._commands import CommandLookup, CommandsPlugin
from bastproxy.plugins.core.proxy.plugin._proxy import ProxyPlugin


@pytest.fixture(autouse=True)
def _patch_command_module(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_command, "API", MagicMock())
    monkeypatch.setattr(_command, "CmdArgsRecord", lambda owner, data, **kw: dict(data))


def _make(function: Any) -> CommandClass:
    parser = argp.ArgumentParser(add_help=False)
    parser.add_argument("-h", "--help", action="store_true")
    return CommandClass("plugins.test.a", "x", function, parser)


def test_fields_and_slots() -> None:
    assert [f.name for f in dataclasses.fields(CommandResult)] == ["success", "message"]
    assert not hasattr(CommandResult(True), "__dict__")


def test_default_message_is_not_shared() -> None:
    first, second = CommandResult(True), CommandResult(True)
    assert first.message == []
    first.message.append("x")
    assert second.message == []


def test_exported_and_same_object_as_dispatcher() -> None:
    assert "CommandResult" in commands_pkg.__all__
    assert _command.CommandResult is CommandResult


def test_success() -> None:
    result = _make(lambda: CommandResult(True, ["ok"])).run("")
    assert result == CommandRunResult(True, ["ok"], "command ran successfully")


def test_failure_appends_help_and_keeps_own_list() -> None:
    own = ["bad"]
    result = _make(lambda: CommandResult(False, own)).run("")
    assert result.success is False
    assert result.reason == "function returned False"
    assert result.message[:2] == ["bad", ""]
    assert len(result.message) > 2
    assert own == ["bad"]


def test_str_message_is_one_line() -> None:
    result = _make(lambda: CommandResult(True, "hi")).run("")  # type: ignore[arg-type]
    assert result.message == ["hi"]


@pytest.mark.parametrize("value", [(True, ["x"]), True, False, None, "text"])
def test_invalid_result(value: Any, caplog: pytest.LogCaptureFixture) -> None:
    cmd = _make(lambda: value)
    with caplog.at_level(logging.ERROR):
        result = cmd.run("")
    assert result.success is False
    assert result.reason == "function returned an invalid result"
    assert len(result.message) == 1
    assert result.message[0].startswith("Error running command: ")
    assert cmd.stats.error_count == 1
    assert cmd.stats.last_error.startswith("TypeError:")
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert type(value).__name__ in errors[0].getMessage()


def test_internal_command_with_tuple_result_reports_error(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    sent: list[Any] = []

    def fake_send(data: Any, clients: Any = None) -> Any:
        sent.append(data)
        return lambda: None

    monkeypatch.setattr(_commands, "SendDataDirectlyToClient", fake_send)
    record: Any = MagicMock()
    record.__getitem__.side_effect = lambda key: {
        "client_id": None,
        "showinhistory": True,
        "line": MagicMock(line="#bp.x"),
    }[key]
    cmd = _make(lambda: (True, ["old style"]))
    cmd.format = False
    stub = MagicMock()
    stub.plugin_id = "plugins.core.commands"
    stub.api = lambda name: lambda: record
    stub.find_command.return_value = CommandLookup(cmd, "", True, "", [])
    with caplog.at_level(logging.ERROR):
        CommandsPlugin.run_internal_command_from_event(stub)
    assert sent
    assert any("Error running command" in str(item) for item in sent[0])
    assert any("not a CommandResult" in r.getMessage() for r in caplog.records)


def test_shutdown_returns_command_result(monkeypatch: pytest.MonkeyPatch) -> None:
    raised: list[int] = []
    monkeypatch.setattr(signal, "raise_signal", raised.append)
    assert ProxyPlugin._command_shutdown(MagicMock()) == CommandResult(True)
    assert raised == [signal.SIGINT]

"""Tests that a failure on the command path is reported to the client (#397)."""

import logging
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs import argp
from bastproxy.libs.records.rtypes.networkdata import NetworkDataLine
from bastproxy.plugins.core.commands import CommandResult
from bastproxy.plugins.core.commands.libs import _command
from bastproxy.plugins.core.commands.libs._command import CommandClass, CommandRunResult
from bastproxy.plugins.core.commands.plugin import _commands
from bastproxy.plugins.core.commands.plugin._commands import CommandLookup, CommandsPlugin


class _Record(dict):
    """Event-record stand-in with the `addupdate` method."""

    def addupdate(self, *args: Any, **kwargs: Any) -> None:
        """Ignore updates."""


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Capture what is sent to the client."""
    calls: list[Any] = []

    def fake_send(data: Any, clients: Any = None) -> Any:
        calls.append(data)
        return lambda: None

    monkeypatch.setattr(_commands, "SendDataDirectlyToClient", fake_send)
    return calls


def _stub() -> tuple[MagicMock, Any]:
    line = NetworkDataLine("#bp.core.commands.list", originated="client")
    record: Any = _Record({"line": line, "client_id": None, "showinhistory": False})
    stub = MagicMock()
    stub.plugin_id = "plugins.core.commands"
    stub.api = lambda name: lambda: record
    return stub, line


def _text(data: Any) -> list[str]:
    return [str(item) for item in data]


def test_find_command_failure_tells_the_client(sent: list[Any]) -> None:
    """An exception in find_command gives an error reply instead of silence."""
    stub, line = _stub()
    stub.find_command.side_effect = RuntimeError("injected find_command failure")

    CommandsPlugin.run_internal_command_from_event(stub)

    assert line.send is False
    assert len(sent) == 1
    assert any("Error running command" in text for text in _text(sent[0]))


def test_error_log_has_command_token_not_arguments(
    sent: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ERROR record names the command but not the user's arguments."""
    logged: list[tuple[int, str]] = []

    def fake_log_to(sources: Any, level: int, msg: str, *args: Any, **kwargs: Any) -> None:
        logged.append((level, msg % args))

    monkeypatch.setattr(_commands, "log_to", fake_log_to)
    stub, line = _stub()
    line.line = "#bp.core.commands.list secretarg"
    stub._command_token = CommandsPlugin._command_token
    stub.find_command.side_effect = RuntimeError("injected find_command failure")

    CommandsPlugin.run_internal_command_from_event(stub)

    errors = [text for level, text in logged if level == logging.ERROR]
    assert any("#bp.core.commands.list" in text for text in errors)
    assert not any("secretarg" in text for text in errors)


@pytest.mark.parametrize("value", ["", "   ", None, 5])
def test_command_token_never_raises(value: Any) -> None:
    """An empty line or a non-string gives a placeholder, not an exception."""
    record = {"line": MagicMock(line=value)}
    assert isinstance(CommandsPlugin._command_token(record), str)
    assert CommandsPlugin._command_token({}) == "<unknown>"


def test_send_failure_is_contained(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failure while sending the command output does not escape."""
    stub, _ = _stub()
    command = MagicMock()
    command.run.return_value = CommandRunResult(True, ["hi"], "command ran successfully")
    stub.find_command.return_value = CommandLookup(command, "", True, "", [])

    def boom(data: Any, clients: Any = None) -> Any:
        raise RuntimeError("send failed")

    monkeypatch.setattr(_commands, "SendDataDirectlyToClient", boom)
    CommandsPlugin.run_internal_command_from_event(stub)


@pytest.fixture
def _patch_command_module(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_command, "API", MagicMock())
    monkeypatch.setattr(_command, "CmdArgsRecord", lambda owner, data, **kw: dict(data))


def _make(function: Any) -> CommandClass:
    parser = argp.ArgumentParser(add_help=False)
    parser.add_argument("-h", "--help", action="store_true")
    return CommandClass("plugins.test.a", "x", function, parser)


def _raiser() -> None:
    raise ValueError("boom")


@pytest.mark.usefixtures("_patch_command_module")
def test_exception_has_its_own_reason() -> None:
    """An exception in the command is not reported as `function returned False`."""
    result = _make(_raiser).run("")
    assert result.success is False
    assert result.reason == "function raised an exception"
    assert any("Error running command" in line for line in result.message)
    assert _make(lambda: CommandResult(False)).run("").reason == "function returned False"


@pytest.mark.usefixtures("_patch_command_module")
def test_format_failure_is_contained() -> None:
    """A failure in format_return_message gives an error reply and its own reason."""
    cmd = _make(lambda: CommandResult(True, ["ok"]))

    def bad_format(message: list[str]) -> list[str]:
        raise RuntimeError("format failed")

    cmd.format_return_message = bad_format  # type: ignore[method-assign]
    result = cmd.run("", format=True)
    assert result.success is False
    assert result.reason == "could not format output"
    assert any("Error running command" in line for line in result.message)
    assert cmd.stats.error_count == 1
    assert cmd.current_args == {}


@pytest.mark.usefixtures("_patch_command_module")
def test_str_message_is_one_line() -> None:
    """A command returning `(True, "hi")` gives one line, not `h` and `i`."""
    result = _make(lambda: CommandResult(True, "hi")).run("")  # type: ignore[arg-type]
    assert result.success is True
    assert result.message == ["hi"]


@pytest.mark.usefixtures("_patch_command_module")
def test_run_finish_str_message_is_one_line() -> None:
    """run_finish treats a str message as a single line."""
    assert _make(lambda: CommandResult(True)).run_finish(True, "hello", "x").message == ["hello"]  # type: ignore[arg-type]


def test_str_find_command_message_is_one_line(sent: list[Any]) -> None:
    """A str message from find_command is sent as one line."""
    stub, _ = _stub()
    stub.find_command.return_value = CommandLookup(None, "", False, "", "Bad Plugin")

    CommandsPlugin.run_internal_command_from_event(stub)

    assert len(sent) == 1
    assert _text(sent[0]) == ["Bad Plugin"]

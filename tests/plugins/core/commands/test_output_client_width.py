"""Tests that command output is formatted for the client that ran it (#421)."""

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs.context import get_output_client
from bastproxy.plugins.core.commands.libs import _command
from bastproxy.plugins.core.commands.libs._command import CommandClass, CommandRunResult
from bastproxy.plugins.core.commands.plugin import _commands
from bastproxy.plugins.core.commands.plugin._commands import CommandLookup, CommandsPlugin

WIDTH = 50


def _record(client_id: str | None) -> Any:
    record: Any = MagicMock()
    record.__getitem__.side_effect = lambda key: {
        "client_id": client_id,
        "showinhistory": True,
        "line": MagicMock(line="#bp.x"),
    }[key]
    return record


def _run(
    monkeypatch: pytest.MonkeyPatch, client_id: str | None, run: Callable[..., Any]
) -> MagicMock:
    sender = MagicMock()
    monkeypatch.setattr(_commands, "SendDataDirectlyToClient", sender)
    command_item = MagicMock()
    command_item.format = True
    command_item.run.side_effect = run
    stub = MagicMock()
    stub.plugin_id = "plugins.core.commands"
    stub.api = lambda name: lambda: _record(client_id)
    stub.find_command.return_value = CommandLookup(command_item, "", True, "", [])
    CommandsPlugin.run_internal_command_from_event(stub)
    return sender


def test_output_client_is_the_records_client_during_the_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str | None] = []

    def run(*_a: Any, **_k: Any) -> CommandRunResult:
        seen.append(get_output_client())
        return CommandRunResult(True, [], "")

    _run(monkeypatch, "c1", run)

    assert seen == ["c1"]
    assert get_output_client() is None


def test_output_client_is_none_for_a_broadcast(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str | None] = []

    def run(*_a: Any, **_k: Any) -> CommandRunResult:
        seen.append(get_output_client())
        return CommandRunResult(True, [], "")

    _run(monkeypatch, None, run)

    assert seen == [None]


def test_output_client_is_cleared_when_the_command_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def run(*_a: Any, **_k: Any) -> CommandRunResult:
        raise RuntimeError("boom")

    sender = _run(monkeypatch, "c1", run)

    assert get_output_client() is None
    assert sender.called  # "Error running command" is still sent


def _record_call(calls: list[Any], result: Any) -> Callable[..., Any]:
    def recorder(*args: Any, **kwargs: Any) -> Any:
        calls.append((args, kwargs))
        return result

    return recorder


def _record_width(widths: list[int], length: int) -> str:
    widths.append(length)
    return "line"


def _commands_stub() -> MagicMock:
    stub = MagicMock()
    stub.plugin_id = "plugins.core.commands"
    calls: dict[str, list[Any]] = {"cap": [], "center": []}
    values: dict[str, Any] = {
        "plugins.core.proxy:line.length.get": lambda: WIDTH,
        "plugins.core.settings:setting.get": lambda _pid, _key: True,
        "plugins.core.commands:command.indent.get": lambda: 2,
        "plugins.core.commands:output.indent.get": lambda: 3,
        "plugins.core.utils:line.cap": _record_call(calls["cap"], "cap"),
        "plugins.core.utils:string.center.colored": _record_call(calls["center"], ["center"]),
    }
    stub.api = lambda name: values[name]
    stub.calls = calls
    stub._format_output_header = lambda *a, **k: CommandsPlugin._format_output_header(stub, *a, **k)
    return stub


def test_header_apis_default_to_the_line_length_api() -> None:
    for call in (
        lambda s: CommandsPlugin._api_output_header_format(s, "T"),
        lambda s: CommandsPlugin._api_output_subheader_format(s, "T"),
        lambda s: CommandsPlugin._api_header_format(s, "T", "@B"),
    ):
        stub = _commands_stub()
        stub.api = lambda name, _api=stub.api: (
            (lambda _pid, key: False if key == "multiline_headers" else "@B")
            if name == "plugins.core.settings:setting.get"
            else _api(name)
        )
        call(stub)
        assert stub.calls["center"][0][0][2] == WIDTH


def test_multiline_header_caps_at_the_line_length_api() -> None:
    stub = _commands_stub()
    CommandsPlugin._format_output_header(stub, "T", "@B")
    assert all(call[1]["line_length"] == WIDTH for call in stub.calls["cap"])


def test_line_length_apis_subtract_the_indent() -> None:
    stub = _commands_stub()
    assert CommandsPlugin._api_command_line_length_get(stub) == WIDTH - 4
    assert CommandsPlugin._api_output_line_length_get(stub) == WIDTH - 6


def test_format_return_message_uses_the_line_length_api(monkeypatch: pytest.MonkeyPatch) -> None:
    widths: list[int] = []
    values: dict[str, Any] = {
        "plugins.core.proxy:line.length.get": lambda: WIDTH,
        "plugins.core.settings:setting.get": lambda _pid, key: key == "simple_output",
        "plugins.core.proxy:preamble.color.get": lambda: "@x",
        "plugins.core.commands:command.indent.get": lambda: 0,
        "plugins.core.commands:command.line.length.get": lambda: WIDTH,
        "plugins.core.commands:output.indent.get": lambda: 0,
        "plugins.core.commands:command.format": lambda plugin_id, cmd: f"{plugin_id}.{cmd}",
        "plugins.core.utils:string.center.colored": lambda _t, _c, length, **_k: _record_width(
            widths, length
        ),
    }
    api_cls = MagicMock()
    api_cls.return_value.side_effect = lambda name: values.get(name, MagicMock())
    monkeypatch.setattr(_command, "API", api_cls)
    monkeypatch.setattr(_command, "CmdArgsRecord", lambda owner, data, **kw: dict(data))
    from bastproxy.libs import argp
    from bastproxy.plugins.core.commands import CommandResult

    parser = argp.ArgumentParser(add_help=False)
    parser.add_argument("-h", "--help", action="store_true")
    command = CommandClass(
        "plugins.test.a", "x", lambda: CommandResult(True, ["hi"]), parser, preamble=True
    )
    command.run("", format=True)

    assert widths
    assert set(widths) == {WIDTH}

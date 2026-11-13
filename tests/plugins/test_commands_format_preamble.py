"""Tests that a command's `format` and `preamble` options are honoured (#389)."""

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs import argp
from bastproxy.plugins.core.commands import CommandResult
from bastproxy.plugins.core.commands.libs import _command
from bastproxy.plugins.core.commands.libs._command import CommandClass, CommandRunResult
from bastproxy.plugins.core.commands.plugin import _commands
from bastproxy.plugins.core.commands.plugin._commands import CommandLookup, CommandsPlugin

PID = "plugins.test.a"


def _api_value(name: str) -> Callable[..., Any]:
    """Return a callable giving a sensible value for the API call `name`."""
    values: dict[str, Any] = {
        "plugins.core.settings:setting.get": lambda plugin_id, key: {
            "simple_output": True,
            "include_date": False,
            "linelen": 80,
            "header_color": "@B",
        }[key],
        "plugins.core.proxy:preamble.color.get": lambda: "@x",
        "plugins.core.commands:command.indent.get": lambda: 2,
        "plugins.core.commands:command.line.length.get": lambda: 70,
        "plugins.core.commands:output.indent.get": lambda: 4,
        "plugins.core.commands:command.format": lambda plugin_id, cmd: f"{plugin_id}.{cmd}",
        "plugins.core.utils:string.center.colored": lambda text, *a, **kw: text,
    }
    result: Callable[..., Any] = values.get(name, MagicMock())
    return result


@pytest.fixture(autouse=True)
def _patch_command_module(monkeypatch: pytest.MonkeyPatch) -> None:
    api_cls = MagicMock()
    api_cls.return_value.side_effect = _api_value
    monkeypatch.setattr(_command, "API", api_cls)
    monkeypatch.setattr(_command, "CmdArgsRecord", lambda owner, data, **kw: dict(data))


def _make(**kwargs: Any) -> CommandClass:
    parser = argp.ArgumentParser(add_help=False)
    parser.add_argument("-h", "--help", action="store_true")
    return CommandClass(PID, "x", lambda: CommandResult(True, ["hello"]), parser, **kwargs)


def test_unformatted_run_returns_plain_messages() -> None:
    result = _make().run("", format=False)
    assert result.success is True
    assert result.message == ["hello"]


def test_formatted_with_preamble_has_begin_and_end() -> None:
    text = "\n".join(_make(preamble=True).run("", format=True).message)
    assert "Begin Command" in text
    assert "End Command" in text
    assert "hello" in text


def test_formatted_without_preamble_drops_begin_and_end() -> None:
    text = "\n".join(_make(preamble=False).run("", format=True).message)
    assert "Begin Command" not in text
    assert "End Command" not in text
    assert "hello" in text


@pytest.mark.parametrize("fmt", [True, False])
def test_run_internal_command_passes_command_format(
    monkeypatch: pytest.MonkeyPatch, fmt: bool
) -> None:
    monkeypatch.setattr(_commands, "SendDataDirectlyToClient", MagicMock())
    record: Any = MagicMock()
    record.__getitem__.side_effect = lambda key: {
        "client_id": None,
        "showinhistory": True,
        "line": MagicMock(line="#bp.x"),
    }[key]
    command_item = MagicMock()
    command_item.format = fmt
    command_item.run.return_value = CommandRunResult(True, [], "")
    stub = MagicMock()
    stub.plugin_id = "plugins.core.commands"
    stub.api = lambda name: lambda: record
    stub.find_command.return_value = CommandLookup(command_item, "", True, "", [])

    CommandsPlugin.run_internal_command_from_event(stub)

    command_item.run.assert_called_once_with("", format=fmt)

"""Tests that #bp command arguments pass through the args-modify event (#776)."""

from collections.abc import Callable
from types import MethodType
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.plugins.core.commands.libs._command import CommandRunResult
from bastproxy.plugins.core.commands.plugin import _commands
from bastproxy.plugins.core.commands.plugin._commands import (
    COMMAND_ARGS_MODIFY_EVENT,
    CommandLookup,
    CommandsPlugin,
)

TYPED = "#bp.test.go %{dest}"


class _Record(dict[str, Any]):
    """Event-record stand-in that keeps the updates it is given."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.updates: list[str] = []

    def addupdate(self, flag: Any, message: str, **kwargs: Any) -> None:
        self.updates.append(message)


class _Event:
    def __init__(self, data: dict[str, Any]) -> None:
        self.event_data = data


def _run(
    *,
    args: str = "go %{dest}",
    literal: bool = False,
    mask_log: bool = False,
    raised: Any = "go home",
) -> tuple[MagicMock, MagicMock, _Record, MagicMock]:
    """Run `run_internal_command_from_event`; return stub, command, record, event.raise."""
    line = MagicMock(line=TYPED, mask_log=mask_log)
    record = _Record({"client_id": "c1", "showinhistory": True, "line": line})
    command_item = MagicMock()
    command_item.plugin_id = "plugins.test"
    command_item.name = "go"
    command_item.literal_args = literal
    command_item.run.return_value = CommandRunResult(True, [], "")
    raise_event = MagicMock(
        return_value=None if raised is None else _Event({"args": raised}),
    )

    def api(name: str) -> Callable[..., Any]:
        if name == "plugins.core.events:event.raise":
            return raise_event
        return lambda: record

    stub = MagicMock()
    stub.plugin_id = "plugins.core.commands"
    stub.api = api
    stub.find_command.return_value = CommandLookup(command_item, args, True, "", [])
    CommandsPlugin.run_internal_command_from_event(stub)
    return stub, command_item, record, raise_event


@pytest.fixture(autouse=True)
def _restore_send(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_commands, "SendDataDirectlyToClient", MagicMock())


def test_args_are_replaced_and_event_raised() -> None:
    _, command_item, record, raise_event = _run()
    command_item.run.assert_called_once()
    assert command_item.run.call_args.args[0] == "go home"
    raise_event.assert_called_once_with(
        COMMAND_ARGS_MODIFY_EVENT,
        event_args={
            "plugin_id": "plugins.test",
            "command": "go",
            "args": "go %{dest}",
            "client_id": "c1",
        },
    )
    assert "command arguments modified" in record.updates


def test_history_keeps_the_typed_line() -> None:
    _, _, record, _ = _run()
    assert record["line"].line == TYPED


def test_literal_args_raise_no_event() -> None:
    _, command_item, _, raise_event = _run(literal=True)
    raise_event.assert_not_called()
    assert command_item.run.call_args.args[0] == "go %{dest}"


def test_masked_line_raises_no_event() -> None:
    _, command_item, _, raise_event = _run(mask_log=True)
    raise_event.assert_not_called()
    assert command_item.run.call_args.args[0] == "go %{dest}"


def test_empty_args_raise_no_event() -> None:
    _, command_item, _, raise_event = _run(args="")
    raise_event.assert_not_called()
    assert command_item.run.call_args.args[0] == ""


@pytest.mark.parametrize("raised", [None, 5, "go %{dest}"])
def test_unusable_event_result_keeps_args(raised: Any) -> None:
    _, command_item, record, _ = _run(raised=raised)
    assert command_item.run.call_args.args[0] == "go %{dest}"
    assert "command arguments modified" not in record.updates


class _Data:
    def __init__(self, kwargs: dict[str, Any]) -> None:
        self.command: dict[str, Any] = {"autoadd": True, "kwargs": kwargs}
        self.argparse: dict[str, Any] = {"kwargs": {"add_help": False, "description": "fine"}}
        self.arguments: list[Any] = []


class _Target:
    plugin_id = "plugins.test.fake"
    name = "fake"


class _FakeCommands:
    def __init__(self) -> None:
        self.plugin_id = "plugins.core.commands"
        self.made: list[dict[str, Any]] = []
        self.commands_list: list[str] = []

    def api(self, name: str) -> Callable[..., Any]:
        if name == "plugins.core.commands:command.format":
            return lambda plugin_id, command: f"#bp.{command}"
        return lambda *a, **kw: None

    def update_command(self, plugin_id: str, command_name: str, command: Any) -> None:
        self.made.append(command.kwargs)


@pytest.mark.parametrize(("kwargs", "expected"), [({"literal_args": True}, True), ({}, False)])
def test_add_by_func_forwards_literal_args(
    monkeypatch: pytest.MonkeyPatch, kwargs: dict[str, Any], expected: bool
) -> None:
    class _Cmd:
        def __init__(self, *args: Any, literal_args: bool = False, **kw: Any) -> None:
            self.kwargs = {"literal_args": literal_args}

    monkeypatch.setattr(_commands, "CommandClass", _Cmd)
    monkeypatch.setattr(_commands, "log_to", lambda *args, **kwargs: None)

    def _func(self: Any) -> None:
        return None

    _func.__name__ = "_command_x"
    _func.command_data = _Data(dict(kwargs))  # type: ignore[attr-defined]
    fake = _FakeCommands()
    CommandsPlugin._api_command_add_by_func(fake, MethodType(_func, _Target()))
    assert fake.made == [{"literal_args": expected}]

"""Tests for variable expansion in #bp command arguments (#776)."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs.persistentdict import PersistentDict
from bastproxy.plugins.client.actions.plugin._actions import ActionsPlugin
from bastproxy.plugins.client.aliases.plugin._aliases import AliasesPlugin
from bastproxy.plugins.client.loop.plugin._loop import LoopPlugin
from bastproxy.plugins.client.substitutes.plugin._substitutes import SubstitutesPlugin
from bastproxy.plugins.client.variables.plugin._variables import VariablesPlugin
from bastproxy.plugins.core.commands.libs._command import CommandRunResult
from bastproxy.plugins.core.commands.plugin import _commands
from bastproxy.plugins.core.commands.plugin._commands import CommandLookup, CommandsPlugin


class _Record(dict[str, Any]):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.updates: list[str] = []

    def addupdate(self, flag: Any, message: str, **kwargs: Any) -> None:
        self.updates.append(message)


class _Event:
    def __init__(self, data: dict[str, Any]) -> None:
        self.event_data = data


def _variables(tmp_path: Path, args: str | None, **values: str) -> tuple[Any, _Record]:
    stub = MagicMock()
    stub.variables = PersistentDict("x", tmp_path / "variables.txt", "c")
    for key, value in values.items():
        stub.variables[key] = value
    record = _Record({"args": args} if args is not None else {})
    stub.api = lambda name: lambda: record if args is not None else None
    return stub, record


@pytest.mark.parametrize(
    ("args", "expected", "updated"),
    [
        ("goto %{t}", "goto orc", True),
        ("goto %{x}", "goto %{x}", False),
        ("goto %%{t}", "goto %{t}", True),
    ],
)
def test_callback_expands_args(tmp_path: Path, args: str, expected: str, updated: bool) -> None:
    stub, record = _variables(tmp_path, args, t="orc")
    VariablesPlugin._eventcb_expand_command_args(stub)
    assert record["args"] == expected
    assert bool(record.updates) is updated
    assert all("orc" not in message for message in record.updates)


def test_callback_without_record_is_quiet(tmp_path: Path) -> None:
    stub, _ = _variables(tmp_path, None, t="orc")
    VariablesPlugin._eventcb_expand_command_args(stub)


def test_callback_registration() -> None:
    registration = VariablesPlugin._eventcb_expand_command_args.event_registration
    assert "ev_plugins.core.commands_args_modify" in str(registration)


def _dispatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, literal: bool) -> MagicMock:
    """Wire the commands plugin to the variables callback; return the command's run mock."""
    monkeypatch.setattr(_commands, "SendDataDirectlyToClient", MagicMock())
    variables_stub, _ = _variables(tmp_path, "", name="orc")
    record = _Record(
        {
            "client_id": "c1",
            "showinhistory": True,
            "line": MagicMock(line="#bp.x.cmd v %{name}", mask_log=False),
            "args": "",
        }
    )
    variables_stub.api = lambda name: lambda: record
    command_item = MagicMock()
    command_item.plugin_id = "plugins.test"
    command_item.name = "cmd"
    command_item.literal_args = literal
    command_item.run.return_value = CommandRunResult(True, [], "")

    def raise_event(name: str, event_args: dict[str, Any]) -> _Event:
        record["args"] = event_args["args"]
        VariablesPlugin._eventcb_expand_command_args(variables_stub)
        return _Event({"args": record["args"]})

    def api(name: str) -> Any:
        if name == "plugins.core.events:event.raise":
            return raise_event
        return lambda: record

    stub = MagicMock()
    stub.plugin_id = "plugins.core.commands"
    stub.api = api
    stub.find_command.return_value = CommandLookup(command_item, "v %{name}", True, "", [])
    CommandsPlugin.run_internal_command_from_event(stub)
    run: MagicMock = command_item.run
    return run


def test_end_to_end_expands(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run = _dispatch(tmp_path, monkeypatch, literal=False)
    assert run.call_args.args[0] == "v orc"


def test_end_to_end_literal_keeps_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    flag = VariablesPlugin._command_add.command_data.command["kwargs"]["literal_args"]
    run = _dispatch(tmp_path, monkeypatch, literal=flag)
    assert run.call_args.args[0] == "v %{name}"


_LITERAL_PLUGINS = [
    VariablesPlugin,
    AliasesPlugin,
    ActionsPlugin,
    SubstitutesPlugin,
    LoopPlugin,
]
_LITERAL_COMMANDS = [
    (cls, name)
    for cls in _LITERAL_PLUGINS
    for name in sorted(vars(cls))
    if name.startswith("_command_")
]


@pytest.mark.parametrize(("cls", "name"), _LITERAL_COMMANDS)
def test_definition_commands_are_literal(cls: type, name: str) -> None:
    kwargs = getattr(cls, name).command_data.command["kwargs"]
    assert kwargs["literal_args"] is True


def test_literal_command_set_is_complete() -> None:
    found = {(cls.__name__, name) for cls, name in _LITERAL_COMMANDS}
    assert len(found) == 3 + 7 + 7 + 4 + 1


def test_other_commands_expand_by_default() -> None:
    from bastproxy.plugins._baseplugin.libs._settings import Settings
    from bastproxy.plugins.client.mapper.plugin._mapper import MapperPlugin

    for func in (MapperPlugin._command_goto, Settings._command_settings_plugin_set):
        assert "literal_args" not in func.command_data.command["kwargs"]

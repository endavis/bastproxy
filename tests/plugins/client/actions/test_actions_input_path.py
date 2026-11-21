# Project: bastproxy
# Filename: tests/plugins/client/aliases/test_aliases_input_path.py
#
# File Description: the actions command output on the input path with commands and variables
#
# By: Bast
"""Action commands go through commands (50) and variables (60) (issue #709)."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs.persistentdict import PersistentDict
from bastproxy.libs.records.rtypes.muddata import ProcessDataToMud
from bastproxy.libs.records.rtypes.networkdata import NetworkData, NetworkDataLine
from bastproxy.plugins.client.actions.plugin._actions import ActionsPlugin
from bastproxy.plugins.client.variables.plugin._variables import VariablesPlugin
from bastproxy.plugins.core.commands.plugin._commands import CommandsPlugin

from .conftest import SPLIT_REGEX, FakeConnection, StandIns


class Record:
    """A stand-in event record: item access, a client id and addupdate."""

    def __init__(self, line: Any, event_args: dict[str, Any]) -> None:
        self.data = {
            "line": line,
            "showinhistory": event_args["showinhistory"],
            "client_id": event_args["client_id"],
        }
        self.addupdate = MagicMock()

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)


class Wired:
    """The wired plugins and what they saw."""

    def __init__(self) -> None:
        self.history: list[str] = []
        self.dispatched: list[str] = []
        self.connection = FakeConnection()
        self.actions: Any = None
        self.variables: Any = None

    @property
    def sent(self) -> list[str]:
        # the colour stand-in wraps the text as ANSI(...) and the line ends in CRLF
        texts = [str(line.line).rstrip("\r\n") for line in self.connection.sent]
        return [text.removeprefix("ANSI(").removesuffix(")") for text in texts]


class _Api:
    command_split_regex = SPLIT_REGEX
    command_separator = "|"

    def __init__(self, table: dict[str, Any]) -> None:
        self.table = table

    def __call__(self, name: str) -> Any:
        return self.table[name]


def _wire(stand_ins: StandIns, tmp_path: Path) -> Wired:
    wired = Wired()
    stand_ins.connection = wired.connection
    current: dict[str, Any] = {}

    commands = MagicMock()
    commands.plugin_id = "plugins.core.commands"
    commands.current_input_event = None
    commands.add_command_to_history.side_effect = wired.history.append

    def run_internal() -> None:
        record = current["record"]
        record["line"].send = False
        record["showinhistory"] = True
        wired.dispatched.append(record["line"].line)

    commands.run_internal_command_from_event.side_effect = run_internal

    shared = {
        "plugins.core.settings:setting.get": lambda plugin_id, key: "#bp",
        "plugins.core.events:event.current.record.get": lambda: current.get("record"),
        "libs.api:caller.owner.get": lambda: "plugins.client.actions",
        "plugins.core.commands:command.prefix.get": lambda: "#bp",
    }
    commands.api = _Api(shared)

    actions: Any = object.__new__(ActionsPlugin)
    actions.plugin_id = "plugins.client.actions"
    actions.actions = PersistentDict("a", tmp_path / "actions.txt", "c")
    actions.groups = PersistentDict("a", tmp_path / "groups.txt", "c")
    actions.session_hits = {}
    actions.api = _Api(
        {
            **shared,
            "plugins.core.commands:command.line.run": lambda line, **kw: (
                CommandsPlugin._api_command_line_run(commands, line, **kw)
            ),
            "plugins.core.triggers:trigger.add": lambda *a, **k: SimpleNamespace(success=True),
            "plugins.core.triggers:trigger.get": lambda *a, **k: None,
            "plugins.core.triggers:trigger.register": lambda *a, **k: True,
        }
    )
    commands.api.table["plugins.core.events:event.current.record.get"] = lambda: current.get(
        "record"
    )

    variables: Any = object.__new__(VariablesPlugin)
    variables.plugin_id = "plugins.client.variables"
    variables.variables = PersistentDict("v", tmp_path / "variables.txt", "c")
    variables.api = _Api(shared)

    def hook(_name: str, data_list: list[Any]) -> None:
        event_args = stand_ins.events[-1]["event_args"]
        for line in data_list:
            outer = current.get("record")
            current["record"] = Record(line, event_args)
            CommandsPlugin._eventcb_check_for_command(commands)
            variables._eventcb_expand_line()
            current["record"] = outer

    stand_ins.hook = hook
    wired.actions = actions
    wired.variables = variables
    return wired


def _type(line: str, client_id: str = "c1") -> None:
    ProcessDataToMud(
        NetworkData([NetworkDataLine(line, originated="client")]), client_id=client_id
    )()


def _fire(wired: Any, name: str, groups: tuple[str | None, ...], text: str = "x") -> None:
    """Call the trigger callback as the triggers plugin would on a match."""
    actions = wired.actions
    record = {
        "trigger_name": name,
        "groups": groups,
        "matches": {},
        "line": SimpleNamespace(noansi=text),
    }
    actions.api.table["plugins.core.events:event.current.record.get"] = lambda: record
    actions._trigger_matched()


def _add(wired: Any, command: str, regex: str = r"(.*)") -> None:
    wired.actions._api_action_add("a", regex, command)


@pytest.mark.usefixtures("split_regex")
def test_variable_in_command_is_expanded(plugin_stand_ins: StandIns, tmp_path: Path) -> None:
    """A %{t} reference in the action command is expanded at 60."""
    wired = _wire(plugin_stand_ins, tmp_path)
    wired.variables.variables["t"] = "orc"
    _add(wired, "kill %{t}")
    _fire(wired, "a", ("x",))
    assert wired.sent == ["kill orc"]
    assert wired.history == []


@pytest.mark.usefixtures("split_regex")
def test_escaped_variable_reaches_mud_literally(plugin_stand_ins: StandIns, tmp_path: Path) -> None:
    """%%{t} in the command is sent as %{t}."""
    wired = _wire(plugin_stand_ins, tmp_path)
    wired.variables.variables["t"] = "orc"
    _add(wired, "say %%{t}")
    _fire(wired, "a", ("x",))
    assert wired.sent == ["say %{t}"]


@pytest.mark.usefixtures("split_regex")
def test_matched_variable_reference_stays_literal(
    plugin_stand_ins: StandIns, tmp_path: Path
) -> None:
    """A matched value %{t} is sent as typed, not expanded."""
    wired = _wire(plugin_stand_ins, tmp_path)
    wired.variables.variables["t"] = "orc"
    _add(wired, "say %1")
    _fire(wired, "a", ("%{t}",))
    assert wired.sent == ["say %{t}"]


@pytest.mark.usefixtures("split_regex")
def test_matched_separator_is_one_line(plugin_stand_ins: StandIns, tmp_path: Path) -> None:
    """A matched value a|b reaches the MUD as one line."""
    wired = _wire(plugin_stand_ins, tmp_path)
    _add(wired, "say %1")
    _fire(wired, "a", ("a|b",))
    assert wired.sent == ["say a|b"]


@pytest.mark.usefixtures("split_regex")
def test_matched_prefix_at_part_start_runs_nothing(
    plugin_stand_ins: StandIns, tmp_path: Path
) -> None:
    """A matched value #bp.x at the start of a part sends and dispatches nothing."""
    wired = _wire(plugin_stand_ins, tmp_path)
    _add(wired, "stand|%1")
    _fire(wired, "a", ("#bp.x",))
    assert wired.sent == []
    assert wired.dispatched == []


@pytest.mark.usefixtures("split_regex")
def test_command_part_is_dispatched_with_quoted_value(
    plugin_stand_ins: StandIns, tmp_path: Path
) -> None:
    """A #bp template part runs as a proxy command with the value quoted."""
    wired = _wire(plugin_stand_ins, tmp_path)
    _add(wired, "#bp.client.actions.show %1")
    _fire(wired, "a", ("x -g evil",))
    assert wired.dispatched == ["#bp.client.actions.show 'x -g evil'"]
    assert wired.sent == []


@pytest.mark.usefixtures("split_regex")
def test_multi_command_order(plugin_stand_ins: StandIns, tmp_path: Path) -> None:
    """stand|kill %1 sends two lines, in order."""
    wired = _wire(plugin_stand_ins, tmp_path)
    _add(wired, "stand|kill %1")
    _fire(wired, "a", ("orc",))
    assert wired.sent == ["stand", "kill orc"]

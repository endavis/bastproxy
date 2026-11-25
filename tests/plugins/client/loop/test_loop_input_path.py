# Project: bastproxy
# Filename: tests/plugins/client/loop/test_loop_input_path.py
#
# File Description: the loop on the input path with commands, aliases and variables
#
# By: Bast
"""Loop passes go through commands (50), aliases (55) and variables (60) (issue #711)."""

import shlex
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs.persistentdict import PersistentDict
from bastproxy.libs.records.rtypes.muddata import ProcessDataToMud
from bastproxy.libs.records.rtypes.networkdata import NetworkData, NetworkDataLine
from bastproxy.plugins.client.aliases.plugin._aliases import AliasesPlugin
from bastproxy.plugins.client.loop.plugin._loop import LoopPlugin
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
        self.aliases: Any = None
        self.variables: Any = None
        self.loop: Any = None

    @property
    def sent(self) -> list[str]:
        # the colour stand-in wraps the text as ANSI(...) and the line ends in CRLF
        texts = [str(line.line).rstrip("\r\n") for line in self.connection.sent]
        return [text.removeprefix("ANSI(").removesuffix(")") for text in texts]


class _Api:
    command_split_regex = SPLIT_REGEX

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
        line = record["line"].line
        wired.dispatched.append(line)
        if line.startswith("#bp.client.loop.run"):
            parts = shlex.split(line)
            wired.loop._api_loop_run(" ".join(parts[2:]), int(parts[1]))

    commands.run_internal_command_from_event.side_effect = run_internal

    shared = {
        "plugins.core.settings:setting.get": lambda plugin_id, key: "#bp",
        "plugins.core.events:event.current.record.get": lambda: current.get("record"),
        "libs.api:caller.owner.get": lambda: "plugins.client.aliases",
        "plugins.core.commands:command.prefix.get": lambda: "#bp",
    }
    commands.api = _Api(shared)

    aliases: Any = object.__new__(AliasesPlugin)
    aliases.plugin_id = "plugins.client.aliases"
    aliases.aliases = PersistentDict("a", tmp_path / "aliases.txt", "c")
    aliases.groups = PersistentDict("a", tmp_path / "groups.txt", "c")
    aliases.state = PersistentDict("a", tmp_path / "state.txt", "c")
    aliases.session_hits = {}
    aliases._resend_depth = 0
    aliases.api = _Api(
        {
            **shared,
            "plugins.core.commands:command.line.run": lambda line, **kw: (
                CommandsPlugin._api_command_line_run(commands, line, **kw)
            ),
        }
    )
    commands.api.table["plugins.core.events:event.current.record.get"] = lambda: current.get(
        "record"
    )

    loop: Any = object.__new__(LoopPlugin)
    loop.plugin_id = "plugins.client.loop"
    loop._depth = 0
    loop._total = 0
    loop._stopped = False
    loop.api = _Api(
        {
            **shared,
            "plugins.core.commands:command.line.run": lambda line, **kw: (
                CommandsPlugin._api_command_line_run(commands, line, **kw)
            ),
        }
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
            aliases._eventcb_expand_line()
            variables._eventcb_expand_line()
            current["record"] = outer

    stand_ins.hook = hook
    wired.aliases = aliases
    wired.loop = loop
    wired.variables = variables
    return wired


def _type(line: str, client_id: str = "c1") -> None:
    ProcessDataToMud(
        NetworkData([NetworkDataLine(line, originated="client")]), client_id=client_id
    )()


@pytest.mark.usefixtures("split_regex")
def test_variables_expand_on_each_pass(plugin_stand_ins: StandIns, tmp_path: Path) -> None:
    """A variable reference is expanded on every line the loop runs."""
    wired = _wire(plugin_stand_ins, tmp_path)
    wired.variables.variables["t"] = "orc"
    assert wired.loop._api_loop_run("kill %{t} %1", 2) is True
    assert wired.sent == ["kill orc 1", "kill orc 2"]


@pytest.mark.usefixtures("split_regex")
def test_aliases_expand_on_each_pass(plugin_stand_ins: StandIns, tmp_path: Path) -> None:
    """An alias in the template is expanded with the counter."""
    wired = _wire(plugin_stand_ins, tmp_path)
    wired.aliases._api_alias_add("k", "kill %1")
    assert wired.loop._api_loop_run("k %1", 2) is True
    assert wired.sent == ["kill 1", "kill 2"]


@pytest.mark.usefixtures("split_regex")
def test_separator_keeps_order_and_history_is_empty(
    plugin_stand_ins: StandIns, tmp_path: Path
) -> None:
    """`stand|look %1` runs in order each pass, and nothing reaches the history."""
    wired = _wire(plugin_stand_ins, tmp_path)
    assert wired.loop._api_loop_run("stand|look %1", 2) is True
    assert wired.sent == ["stand", "look 1", "stand", "look 2"]
    assert wired.history == []


@pytest.mark.usefixtures("split_regex")
def test_nested_loop_through_the_input_path(plugin_stand_ins: StandIns, tmp_path: Path) -> None:
    """A nested loop line is dispatched as a command and multiplies the passes."""
    wired = _wire(plugin_stand_ins, tmp_path)
    assert wired.loop._api_loop_run("#bp.client.loop.run 2 get %%1.item %1.bag", 3) is True
    assert wired.sent == [
        "get 1.item 1.bag",
        "get 2.item 1.bag",
        "get 1.item 2.bag",
        "get 2.item 2.bag",
        "get 1.item 3.bag",
        "get 2.item 3.bag",
    ]
    assert wired.loop._total == 0


@pytest.mark.usefixtures("split_regex")
def test_loop_passes_take_the_loop_commands_place(
    plugin_stand_ins: StandIns, tmp_path: Path
) -> None:
    """`stand|#bp.client.loop.run 2 kill %1` sends `stand`, then both passes (#714)."""
    wired = _wire(plugin_stand_ins, tmp_path)
    _type("stand|#bp.client.loop.run 2 kill %1")
    assert wired.sent == ["stand", "kill 1", "kill 2"]

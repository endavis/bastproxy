# Project: bastproxy
# Filename: tests/plugins/client/aliases/test_aliases_input_path.py
#
# File Description: the aliases callback on the input path with commands and variables
#
# By: Bast
"""Typed lines go through commands (50), aliases (55) and variables (60) (issue #708)."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs.persistentdict import PersistentDict
from bastproxy.libs.records.rtypes.muddata import ProcessDataToMud
from bastproxy.libs.records.rtypes.networkdata import NetworkData, NetworkDataLine
from bastproxy.plugins.client.aliases.plugin._aliases import AliasesPlugin
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
        wired.dispatched.append(record["line"].line)

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
    wired.variables = variables
    return wired


def _type(line: str, client_id: str = "c1") -> None:
    ProcessDataToMud(
        NetworkData([NetworkDataLine(line, originated="client")]), client_id=client_id
    )()


@pytest.mark.usefixtures("split_regex")
def test_alias_with_argument(plugin_stand_ins: StandIns, tmp_path: Path) -> None:
    """`k orc` sends `kill orc`; the history holds the typed line."""
    wired = _wire(plugin_stand_ins, tmp_path)
    wired.aliases._api_alias_add("k", "kill %1")
    _type("k orc")
    assert wired.sent == ["kill orc"]
    assert wired.history == ["k orc"]


@pytest.mark.usefixtures("split_regex")
def test_alias_then_variables(plugin_stand_ins: StandIns, tmp_path: Path) -> None:
    """A variable reference in an expansion is expanded after the alias."""
    wired = _wire(plugin_stand_ins, tmp_path)
    wired.variables.variables["t"] = "orc"
    wired.aliases._api_alias_add("kt", "kill %{t}")
    _type("kt")
    assert wired.sent == ["kill orc"]


@pytest.mark.usefixtures("split_regex")
def test_alias_in_separated_input_keeps_order(plugin_stand_ins: StandIns, tmp_path: Path) -> None:
    """`look|k orc` sends `look`, then `kill orc`."""
    wired = _wire(plugin_stand_ins, tmp_path)
    wired.aliases._api_alias_add("k", "kill %1")
    _type("look|k orc")
    assert wired.sent == ["look", "kill orc"]


@pytest.mark.usefixtures("split_regex")
def test_multi_command_alias(plugin_stand_ins: StandIns, tmp_path: Path) -> None:
    """A multi-command alias sends both parts; only the typed line is in the history."""
    wired = _wire(plugin_stand_ins, tmp_path)
    wired.variables.variables["t"] = "orc"
    wired.aliases._api_alias_add("go", "stand|kill %{t}")
    _type("go")
    assert wired.sent == ["stand", "kill orc"]
    assert wired.history == ["go"]


@pytest.mark.usefixtures("split_regex")
def test_alias_to_proxy_command(plugin_stand_ins: StandIns, tmp_path: Path) -> None:
    """An alias that expands to a #bp command runs it and sends nothing to the MUD."""
    wired = _wire(plugin_stand_ins, tmp_path)
    wired.aliases._api_alias_add("al", "#bp.client.aliases.list")
    _type("al")
    assert wired.dispatched == ["#bp.client.aliases.list"]
    assert wired.sent == []
    assert wired.history == ["al"]


@pytest.mark.usefixtures("split_regex")
def test_resent_alias_keeps_its_place_in_a_separated_input(
    plugin_stand_ins: StandIns, tmp_path: Path
) -> None:
    """`say hi|port` sends `say hi`, then the lines `port` expands to (#714)."""
    wired = _wire(plugin_stand_ins, tmp_path)
    wired.aliases._api_alias_add("port", "stand|look")
    _type("say hi|port")
    assert wired.sent == ["say hi", "stand", "look"]


@pytest.mark.usefixtures("split_regex")
def test_resent_alias_in_the_middle_keeps_its_place(
    plugin_stand_ins: StandIns, tmp_path: Path
) -> None:
    """`look|go|score` sends the lines `go` expands to between `look` and `score` (#714)."""
    wired = _wire(plugin_stand_ins, tmp_path)
    wired.aliases._api_alias_add("go", "stand|kill orc")
    _type("look|go|score")
    assert wired.sent == ["look", "stand", "kill orc", "score"]

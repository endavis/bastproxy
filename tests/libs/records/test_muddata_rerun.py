"""A `!` rerun runs as client input but leaves the history list unchanged (#525)."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs.records.rtypes.muddata import ProcessDataToMud
from bastproxy.libs.records.rtypes.networkdata import NetworkData, NetworkDataLine
from bastproxy.plugins.core.commands.plugin._commands import CommandsPlugin

from .conftest import FakeConnection, StandIns


def _wire(stand_ins: StandIns, history: list[str]) -> list[tuple[str, str | None]]:
    """Drive the real history callback; `!` reruns history[0] as a nested input.

    Returns the proxy commands dispatched as (line, client_id).
    """
    dispatched: list[tuple[str, str | None]] = []
    current: dict[str, Any] = {}

    def api(name: str) -> Any:
        if name == "plugins.core.settings:setting.get":
            return lambda plugin_id, key: "#bp"
        if name == "plugins.core.events:event.current.record.get":
            return lambda: current["record"]
        raise AssertionError(name)

    stub = MagicMock()
    stub.plugin_id = "plugins.core.commands"
    stub.api = api
    stub.current_input_event = None

    def add_to_history(line: str) -> None:
        history.append(line)

    stub.add_command_to_history.side_effect = add_to_history

    def run_internal() -> None:
        record = current["record"]
        line = record["line"].line
        if line.endswith(".!"):
            # the command lookup reports show_in_history False for `!` itself
            record["showinhistory"] = False
            ProcessDataToMud(
                NetworkData(
                    NetworkDataLine(history[0], originated="client"), owner_id="run_history"
                ),
                show_in_history=False,
                client_id=record["client_id"],
            )()
        else:
            # an ordinary proxy command reports show_in_history True
            record["showinhistory"] = True
            dispatched.append((line, record["client_id"]))

    stub.run_internal_command_from_event.side_effect = run_internal

    def hook(_name: str, data_list: list[Any]) -> None:
        event_args = stand_ins.events[-1].kwargs["event_args"]
        for line in data_list:
            outer = current.get("record")
            current["record"] = {
                "line": line,
                "showinhistory": event_args["showinhistory"],
                "client_id": event_args["client_id"],
            }
            CommandsPlugin._eventcb_check_for_command(stub)
            current["record"] = outer

    stand_ins.hook = hook
    return dispatched


def _type(line: str, client_id: str = "c1") -> None:
    ProcessDataToMud(
        NetworkData([NetworkDataLine(line, originated="client")]), client_id=client_id
    )()


@pytest.mark.usefixtures("split_regex")
def test_rerun_of_proxy_command_is_dispatched_and_history_unchanged(
    plugin_stand_ins: StandIns,
) -> None:
    plugin_stand_ins.connection = FakeConnection()
    history = ["#bp.a.list", "look"]
    dispatched = _wire(plugin_stand_ins, history)
    _type("#bp.core.commands.!", client_id="c7")
    assert dispatched == [("#bp.a.list", "c7")]
    assert history == ["#bp.a.list", "look"]


@pytest.mark.usefixtures("split_regex")
def test_rerun_of_mud_line_reaches_mud_and_history_unchanged(
    plugin_stand_ins: StandIns,
) -> None:
    connection = FakeConnection()
    plugin_stand_ins.connection = connection
    history = ["look"]
    dispatched = _wire(plugin_stand_ins, history)
    _type("#bp.core.commands.!")
    assert dispatched == []
    assert any("look" in str(line.line) for line in connection.sent)
    assert history == ["look"]


@pytest.mark.usefixtures("split_regex")
def test_typed_line_is_still_recorded(plugin_stand_ins: StandIns) -> None:
    plugin_stand_ins.connection = FakeConnection()
    history: list[str] = []
    _wire(plugin_stand_ins, history)
    _type("look")
    assert history == ["look"]

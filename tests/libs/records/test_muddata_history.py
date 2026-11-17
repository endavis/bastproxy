"""Command history holds only client input, not what a command sends itself (#515)."""

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs.records.events import TO_MUD_DATA_MODIFY
from bastproxy.libs.records.rtypes.muddata import ProcessDataToMud, SendDataDirectlyToMud
from bastproxy.libs.records.rtypes.networkdata import NetworkData, NetworkDataLine
from bastproxy.plugins.core.commands.plugin._commands import CommandsPlugin

from .conftest import FakeConnection, StandIns


def _wire_history(stand_ins: StandIns, on_command: Callable[[], None]) -> list[str]:
    """Feed every modify event into the real history callback; return the history."""
    recorded: list[str] = []
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
    stub.add_command_to_history.side_effect = recorded.append
    stub.run_internal_command_from_event.side_effect = on_command

    def hook(_name: str, data_list: list[Any]) -> None:
        for line in data_list:
            current["record"] = {"line": line, "showinhistory": True}
            CommandsPlugin._eventcb_check_for_command(stub)

    stand_ins.hook = hook
    return recorded


@pytest.mark.usefixtures("split_regex")
def test_plain_client_line_is_recorded(plugin_stand_ins: StandIns) -> None:
    plugin_stand_ins.connection = FakeConnection()
    recorded = _wire_history(plugin_stand_ins, lambda: None)
    ProcessDataToMud(NetworkData([NetworkDataLine("look", originated="client")]))()
    assert recorded == ["look"]


def _run_api() -> None:
    return None


def _send_directly() -> None:
    SendDataDirectlyToMud(NetworkData("inner"))()


def _send_internal_process() -> None:
    ProcessDataToMud(NetworkData("inner"))()


@pytest.mark.usefixtures("split_regex")
@pytest.mark.parametrize(
    ("scenario", "inner_sent"),
    [(_run_api, False), (_send_directly, True), (_send_internal_process, True)],
    ids=["command-run", "send-directly", "internal-process"],
)
def test_history_holds_only_client_input(
    plugin_stand_ins: StandIns, scenario: Callable[[], None], inner_sent: bool
) -> None:
    connection = FakeConnection()
    plugin_stand_ins.connection = connection
    recorded = _wire_history(plugin_stand_ins, scenario)
    ProcessDataToMud(NetworkData([NetworkDataLine("#bp.x.y", originated="client")]))()

    assert recorded == ["#bp.x.y"]
    modifies = [c for c in plugin_stand_ins.events if c.name == TO_MUD_DATA_MODIFY]
    assert len(modifies) == 1
    if inner_sent:
        assert any("inner" in str(line.line) for line in connection.sent)

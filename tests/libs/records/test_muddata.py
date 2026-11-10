"""Tests for the to-mud record types: command splitting and the _exec_ steps (#239)."""

import pytest

from bastproxy.libs.api import API
from bastproxy.libs.records.events import TO_MUD_DATA_MODIFY, TO_MUD_DATA_READ
from bastproxy.libs.records.managers.records import RMANAGER
from bastproxy.libs.records.rtypes.muddata import ProcessDataToMud, SendDataDirectlyToMud
from bastproxy.libs.records.rtypes.networkdata import NetworkData, NetworkDataLine

from .conftest import FakeConnection, StandIns


def _mixed_message() -> NetworkData:
    return NetworkData(
        [
            NetworkDataLine("say a|say b|say c", originated="client"),
            NetworkDataLine(b"\xff\xfb", originated="client", line_type="COMMAND-TELNET"),
            NetworkDataLine("say x||y", originated="client"),
        ]
    )


@pytest.mark.usefixtures("split_regex")
def test_seperate_commands_splits_io_lines() -> None:
    message = _mixed_message()
    original = message[0]
    telnet = message[1]
    double = message[2]
    record = ProcessDataToMud(message)
    record.seperate_commands()

    assert [line.line for line in message] == ["say a", "say b", "say c", b"\xff\xfb", "say x||y"]
    assert message[3] is telnet
    assert message[4] is double
    for piece in list(message)[:3]:
        assert piece.originated == "client"
        assert piece.line_type == "IO"
        assert piece.original_line == "say a|say b|say c"
        assert piece.parents == [message]
        assert piece.parent is message
        assert piece.split_from is original
    assert original.parents == []
    assert original.parent is None
    children = RMANAGER.get_children(message)
    assert len(children) == len(message)
    assert all(any(child is line for child in children) for line in message)
    assert all(child is not original for child in children)
    assert sum("split (Split_Char)" in str(update) for update in record.updates) == 1


def test_seperate_commands_without_regex_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(API, "command_split_regex", None)
    message = NetworkData([NetworkDataLine("say a|say b", originated="client")])
    record = ProcessDataToMud(message)
    record.seperate_commands()
    assert [line.line for line in message] == ["say a|say b"]


@pytest.mark.usefixtures("split_regex")
def test_process_exec_end_to_end(plugin_stand_ins: StandIns) -> None:
    plugin_stand_ins.connection = FakeConnection()
    message = NetworkData([NetworkDataLine("say a|say b", originated="client")])
    record = ProcessDataToMud(message, show_in_history=False, client_id="c1")
    record()

    modify, read = plugin_stand_ins.events
    assert modify.name == TO_MUD_DATA_MODIFY
    assert modify.kwargs["event_args"] == {"showinhistory": False, "client_id": "c1"}
    assert modify.snapshot == ["say a", "say b"]
    assert read.name == TO_MUD_DATA_READ
    assert [line.line for line in plugin_stand_ins.connection.sent] == [
        "ANSI(say a)\r\n",
        "ANSI(say b)\r\n",
    ]
    assert read.snapshot == ["ANSI(say a)\r\n", "ANSI(say b)\r\n"]
    assert message.locked
    assert all(line.parents == [message] for line in message)


@pytest.mark.usefixtures("split_regex")
def test_process_exec_child_has_process_as_parent(plugin_stand_ins: StandIns) -> None:
    plugin_stand_ins.connection = FakeConnection()
    message = NetworkData([NetworkDataLine("hi", originated="client")])
    record = ProcessDataToMud(message)
    record()
    # SendDataDirectlyToMud re-parents the message; the child record keeps the process as parent
    child = message.parent
    assert isinstance(child, SendDataDirectlyToMud)
    assert record in child.parents


@pytest.mark.usefixtures("split_regex")
def test_process_exec_only_internal_lines_skips_modify(plugin_stand_ins: StandIns) -> None:
    plugin_stand_ins.connection = FakeConnection()
    message = NetworkData([NetworkDataLine("internal")])
    ProcessDataToMud(message)()
    assert [call.name for call in plugin_stand_ins.events] == [TO_MUD_DATA_READ]
    assert [line.line for line in plugin_stand_ins.connection.sent] == [
        "ANSI(@C#BP@w: internal)\r\n"
    ]


def test_send_directly_without_connection(plugin_stand_ins: StandIns) -> None:
    plugin_stand_ins.connection = None
    message = NetworkData([NetworkDataLine("hello", originated="client")])
    SendDataDirectlyToMud(message)()
    assert [call.name for call in plugin_stand_ins.events] == [TO_MUD_DATA_READ]
    assert message.locked

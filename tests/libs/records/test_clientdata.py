"""Tests for the to-client record types: construction, send decisions and _exec_ (#239)."""

import pytest

from bastproxy.libs.records.events import TO_CLIENT_DATA_MODIFY, TO_CLIENT_DATA_READ
from bastproxy.libs.records.rtypes.clientdata import (
    ProcessDataToClient,
    SendDataDirectlyToClient,
)
from bastproxy.libs.records.rtypes.networkdata import NetworkData, NetworkDataLine

from .conftest import StandIns


def test_process_construction_defaults_and_parent() -> None:
    message = NetworkData([NetworkDataLine("a", originated="mud")])
    record = ProcessDataToClient(message)
    assert record.message is message
    assert message.parent is record
    assert message.parents == [record]
    assert record.preamble is True
    assert record.prelogin is False
    assert record.error is False
    assert record.send_to_clients is True
    assert record.clients == []
    assert record.exclude_clients == []
    assert record.color_for_all_lines == ""
    assert record.modify_data_event_name == TO_CLIENT_DATA_MODIFY
    assert record.read_data_event_name == TO_CLIENT_DATA_READ


def test_process_add_and_exclude_client() -> None:
    record = ProcessDataToClient(NetworkData("a"))
    record.exclude_client("u1")
    assert record.exclude_clients == ["u1"]
    record.add_client("u1")
    assert record.clients == ["u1"]
    assert record.exclude_clients == []
    record.exclude_client("u1")
    assert record.clients == []
    assert record.exclude_clients == ["u1"]


# (uuid, exclude, view client, internal, in clients, logged in, prelogin, expected)
_PROCESS_ROWS = [
    ("", [], False, False, ["u1"], True, False, False),
    ("u1", ["u1"], False, False, ["u1"], True, False, False),
    ("u1", [], True, True, ["u1"], True, False, False),
    ("u1", [], True, False, ["u1"], True, False, True),
    ("u1", [], False, False, ["u2"], True, False, False),
    ("u1", [], False, False, ["u1"], False, False, False),
    ("u1", [], False, False, ["u1"], False, True, True),
]


@pytest.mark.parametrize(
    ("uuid", "exclude", "view", "internal", "clients", "logged_in", "prelogin", "expected"),
    _PROCESS_ROWS,
)
def test_process_can_send_to_client(
    plugin_stand_ins: StandIns,
    uuid: str,
    exclude: list[str],
    view: bool,
    internal: bool,
    clients: list[str],
    logged_in: bool,
    prelogin: bool,
    expected: bool,
) -> None:
    if view:
        plugin_stand_ins.view_clients.add("u1")
    if logged_in:
        plugin_stand_ins.logged_in.add("u1")
    record = ProcessDataToClient(
        NetworkData("a"), clients=clients, exclude_clients=exclude, prelogin=prelogin
    )
    assert record.can_send_to_client(uuid, internal) is expected


def _mud_message() -> NetworkData:
    return NetworkData(
        [
            NetworkDataLine("from mud", originated="mud"),
            NetworkDataLine(b"\xff\xfb", originated="mud", line_type="COMMAND-TELNET"),
            NetworkDataLine("internal"),
        ]
    )


def test_process_exec_end_to_end(plugin_stand_ins: StandIns) -> None:
    plugin_stand_ins.logged_in = {"u1"}
    plugin_stand_ins.clients = ["u1", "u2"]
    message = _mud_message()
    record = ProcessDataToClient(message)
    record()

    modify, read = plugin_stand_ins.events
    assert modify.name == TO_CLIENT_DATA_MODIFY
    assert modify.snapshot == ["from mud"]
    assert read.name == TO_CLIENT_DATA_READ
    assert plugin_stand_ins.sent_to_clients == [
        ("u1", "ANSI(from mud)\r\n"),
        ("u1", b"\xff\xfb"),
        ("u1", "ANSI(@C#BP@w: internal)\r\n"),
    ]
    assert read.snapshot == ["ANSI(from mud)\r\n", b"\xff\xfb", "ANSI(@C#BP@w: internal)\r\n"]
    assert message.locked


def test_process_exec_send_to_clients_false(plugin_stand_ins: StandIns) -> None:
    plugin_stand_ins.logged_in = {"u1"}
    plugin_stand_ins.clients = ["u1"]

    def hook(_name: str, _data: list[NetworkDataLine]) -> None:
        record.send_to_clients = False

    plugin_stand_ins.hook = hook
    record = ProcessDataToClient(_mud_message())
    record()
    assert plugin_stand_ins.sent_to_clients == []
    assert [call.name for call in plugin_stand_ins.events] == [TO_CLIENT_DATA_MODIFY]


def test_process_exec_line_send_false_is_skipped(plugin_stand_ins: StandIns) -> None:
    plugin_stand_ins.logged_in = {"u1"}
    plugin_stand_ins.clients = ["u1"]

    def hook(_name: str, data: list[NetworkDataLine]) -> None:
        data[0].send = False

    plugin_stand_ins.hook = hook
    ProcessDataToClient(_mud_message())()
    assert [line for _uuid, line in plugin_stand_ins.sent_to_clients] == [
        b"\xff\xfb",
        "ANSI(@C#BP@w: internal)\r\n",
    ]


# (uuid, exclude, in clients list, view client, line internal, logged in, line prelogin, expected)
_DIRECT_ROWS = [
    ("", [], [], False, False, True, False, False),
    ("u1", ["u1"], [], False, False, True, False, False),
    ("u1", [], [], True, True, True, False, False),
    ("u1", [], ["u1"], True, True, True, False, True),
    ("u1", [], ["u2"], False, False, True, False, False),
    ("u1", [], [], False, False, False, False, False),
    ("u1", [], [], False, False, False, True, True),
]


@pytest.mark.parametrize(
    ("uuid", "exclude", "clients", "view", "internal", "logged_in", "prelogin", "expected"),
    _DIRECT_ROWS,
)
def test_direct_can_send_to_client(
    plugin_stand_ins: StandIns,
    uuid: str,
    exclude: list[str],
    clients: list[str],
    view: bool,
    internal: bool,
    logged_in: bool,
    prelogin: bool,
    expected: bool,
) -> None:
    if view:
        plugin_stand_ins.view_clients.add("u1")
    if logged_in:
        plugin_stand_ins.logged_in.add("u1")
    line = NetworkDataLine("a", originated="internal" if internal else "mud", prelogin=prelogin)
    record = SendDataDirectlyToClient(NetworkData(line), clients=clients, exclude_clients=exclude)
    assert record.can_send_to_client(uuid, line) is expected


def test_direct_exec_explicit_clients(plugin_stand_ins: StandIns) -> None:
    plugin_stand_ins.logged_in = {"u1", "u2"}
    plugin_stand_ins.clients = ["u3"]
    message = NetworkData([NetworkDataLine("a", originated="mud")])
    SendDataDirectlyToClient(message, clients=["u1", "u2"])()
    assert [uuid for uuid, _line in plugin_stand_ins.sent_to_clients] == ["u1", "u2"]
    assert "client.list" not in plugin_stand_ins.api_calls
    assert [call.name for call in plugin_stand_ins.events] == [TO_CLIENT_DATA_READ]


def test_direct_exec_empty_clients_uses_client_list(plugin_stand_ins: StandIns) -> None:
    plugin_stand_ins.logged_in = {"u1", "u2"}
    plugin_stand_ins.clients = ["u1", "u2"]
    message = NetworkData([NetworkDataLine("a", originated="mud")])
    SendDataDirectlyToClient(message)()
    assert "client.list" in plugin_stand_ins.api_calls
    assert [uuid for uuid, _line in plugin_stand_ins.sent_to_clients] == ["u1", "u2"]


def test_direct_exec_client_that_cannot_receive(plugin_stand_ins: StandIns) -> None:
    plugin_stand_ins.logged_in = {"u1"}
    plugin_stand_ins.clients = ["u1", "u2"]
    message = NetworkData([NetworkDataLine("a", originated="mud")])
    SendDataDirectlyToClient(message)()
    assert [uuid for uuid, _line in plugin_stand_ins.sent_to_clients] == ["u1"]

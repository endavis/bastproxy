"""Client sends made while MUD data is processed go out after its lines (#746)."""

from collections.abc import Callable
from typing import Any

import pytest

from bastproxy.libs.context import client_capture
from bastproxy.libs.records.enums import UpdateFlag
from bastproxy.libs.records.events import TO_CLIENT_DATA_READ
from bastproxy.libs.records.managers.records import RMANAGER
from bastproxy.libs.records.rtypes.clientdata import (
    ProcessDataToClient,
    SendDataDirectlyToClient,
)
from bastproxy.libs.records.rtypes.networkdata import NetworkData, NetworkDataLine

from .conftest import StandIns

Hook = Callable[[str, list[Any]], None]


def _mud(*lines: str) -> NetworkData:
    return NetworkData([NetworkDataLine(text, originated="mud") for text in lines])


def _send(*lines: str, **kwargs: Any) -> SendDataDirectlyToClient:
    return SendDataDirectlyToClient(
        NetworkData([NetworkDataLine(text, originated="internal") for text in lines]), **kwargs
    )


def _on_line(stand_ins: StandIns, trigger: str, action: Callable[[Any], None]) -> None:
    def hook(_name: str, data_list: list[Any]) -> None:
        for line in data_list:
            if line.line == trigger:
                action(line)

    stand_ins.hook = hook


@pytest.fixture
def stand_ins(plugin_stand_ins: StandIns) -> StandIns:
    plugin_stand_ins.clients = ["u1", "u2"]
    plugin_stand_ins.logged_in = {"u1", "u2"}
    return plugin_stand_ins


def _texts(stand_ins: StandIns, client: str | None = None) -> list[str]:
    return [
        str(text).removesuffix("\r\n")
        for uuid, text in stand_ins.sent_to_clients
        if client is None or uuid == client
    ]


def test_send_from_middle_line_follows_the_packet(stand_ins: StandIns) -> None:
    _on_line(stand_ins, "b", lambda _line: _send("table")())
    ProcessDataToClient(_mud("a", "b", "c"))()
    texts = _texts(stand_ins, "u1")
    assert texts[:3] == ["a", "b", "c"]
    assert len(texts) == 4
    assert "table" in texts[3]


def test_several_sends_keep_order(stand_ins: StandIns) -> None:
    def action(_line: Any) -> None:
        _send("one")()
        _send("two", "three")()

    _on_line(stand_ins, "a", action)
    ProcessDataToClient(_mud("a", "b", "c"))()
    texts = _texts(stand_ins, "u1")
    assert texts[:3] == ["a", "b", "c"]
    assert ["one" in texts[3], "two" in texts[4], "three" in texts[5]] == [True] * 3


def test_held_send_keeps_its_clients(stand_ins: StandIns) -> None:
    _on_line(stand_ins, "a", lambda _line: _send("only", clients=["u2"])())
    ProcessDataToClient(_mud("a", "b"))()
    assert _texts(stand_ins, "u1") == ["a", "b"]
    u2 = _texts(stand_ins, "u2")
    assert u2[:2] == ["a", "b"]
    assert "only" in u2[2]


def test_send_to_clients_false_still_releases(stand_ins: StandIns) -> None:
    def action(line: Any) -> None:
        _send("held")()

    _on_line(stand_ins, "a", action)
    record = ProcessDataToClient(_mud("a", "b"))
    record.send_to_clients = False
    record()
    texts = _texts(stand_ins, "u1")
    assert len(texts) == 1
    assert "held" in texts[0]


def test_hidden_line_does_not_stop_held_send(stand_ins: StandIns) -> None:
    def action(line: Any) -> None:
        line.send = False
        _send("held")()

    _on_line(stand_ins, "a", action)
    ProcessDataToClient(_mud("a", "b"))()
    texts = _texts(stand_ins, "u1")
    assert texts[0] == "b"
    assert "held" in texts[1]


def test_hook_raising_still_delivers_held_send(stand_ins: StandIns) -> None:
    def action(_line: Any) -> None:
        _send("held")()
        raise RuntimeError("boom")

    _on_line(stand_ins, "a", action)
    with pytest.raises(RuntimeError, match="boom"):
        ProcessDataToClient(_mud("a", "b"))()
    texts = _texts(stand_ins, "u1")
    assert len(texts) == 1
    assert "held" in texts[0]
    assert client_capture.get() is None


def test_send_outside_mud_processing_is_immediate(stand_ins: StandIns) -> None:
    assert client_capture.get() is None
    _send("now")()
    assert len(stand_ins.sent_to_clients) == 2
    assert not stand_ins.events or stand_ins.events[0].name == TO_CLIENT_DATA_READ


def test_capture_cleared_after_process(stand_ins: StandIns) -> None:
    ProcessDataToClient(_mud("a"))()
    assert client_capture.get() is None
    before = len(stand_ins.sent_to_clients)
    _send("later")()
    assert len(stand_ins.sent_to_clients) == before + 2


def test_nested_process_follows_outer_lines(stand_ins: StandIns) -> None:
    def action(_line: Any) -> None:
        ProcessDataToClient(_mud("n1", "n2"))()
        _send("after")()

    _on_line(stand_ins, "b", action)
    ProcessDataToClient(_mud("a", "b", "c"))()
    texts = _texts(stand_ins, "u1")
    assert texts[:5] == ["a", "b", "c", "n1", "n2"]
    assert "after" in texts[5]


def test_read_event_after_held_sends(stand_ins: StandIns) -> None:
    _on_line(stand_ins, "a", lambda _line: _send("held")())
    ProcessDataToClient(_mud("a", "b"))()
    names = [call.name for call in stand_ins.events]
    # modify, the held send's read event, then the packet's read event
    assert names[0].endswith("modify")
    reads = [call for call in stand_ins.events if call.name == TO_CLIENT_DATA_READ]
    assert len(reads) == 2
    assert any("held" in str(item) for item in reads[0].snapshot)
    assert reads[1].snapshot == ["a\r\n", "b\r\n"]


def test_held_record_has_update_and_parent(stand_ins: StandIns) -> None:
    held: list[SendDataDirectlyToClient] = []
    active: list[Any] = []

    def action(_line: Any) -> None:
        active.append(RMANAGER.get_latest_record())
        send = _send("held")
        held.append(send)
        send()

    _on_line(stand_ins, "a", action)
    ProcessDataToClient(_mud("a"))()
    (send,) = held
    # Holding moves only when the send runs: its parent is the record active at creation.
    assert active[0] is not None
    assert send.parent is active[0]
    flags = [update.flag for update in send.updates]
    assert UpdateFlag.INFO in flags
    assert any("held" in str(update.entry) for update in send.updates)

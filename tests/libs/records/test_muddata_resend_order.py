"""Lines re-sent while an input is separated are sent in their place (#714)."""

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs.context import (
    capturing_resends,
    resend_anchor,
    resend_capture,
    resending_in_place_of,
)
from bastproxy.libs.records.events import TO_MUD_DATA_READ
from bastproxy.libs.records.rtypes.muddata import (
    PendingMudSends,
    ProcessDataToMud,
    SendDataDirectlyToMud,
)
from bastproxy.libs.records.rtypes.networkdata import NetworkData, NetworkDataLine
from bastproxy.plugins.core.commands.plugin._commands import CommandsPlugin

from .conftest import FakeConnection, StandIns


def _stub(stand_ins: StandIns, current: dict[str, Any]) -> MagicMock:
    def api(name: str) -> Any:
        if name == "plugins.core.events:event.current.record.get":
            return lambda: current.get("record")
        if name == "libs.api:caller.owner.get":
            return lambda: "plugins.test.caller"
        raise AssertionError(name)

    stub = MagicMock()
    stub.api = api
    return stub


def _wire(
    stand_ins: StandIns,
    handlers: dict[str, Callable[[Callable[[str], None]], None]],
    no_send: set[str] | None = None,
) -> Callable[[str], None]:
    """Hook the modify event: a line with a handler runs it, and may be marked not to send."""
    current: dict[str, Any] = {}
    stub = _stub(stand_ins, current)

    def run(line: str) -> None:
        CommandsPlugin._api_command_line_run(stub, line)

    def hook(_name: str, data_list: list[Any]) -> None:
        for line in data_list:
            outer = current.get("record")
            current["record"] = {"line": line, "client_id": "c1"}
            if no_send and line.line in no_send:
                line.send = False
            if line.line in handlers:
                handlers[line.line](run)
            current["record"] = outer

    stand_ins.hook = hook
    return run


def _type(line: str) -> None:
    ProcessDataToMud(NetworkData([NetworkDataLine(line, originated="client")]), client_id="c1")()


def _sent(connection: FakeConnection) -> list[str]:
    return [str(line.line).removeprefix("ANSI(").removesuffix(")\r\n") for line in connection.sent]


@pytest.fixture
def connection(plugin_stand_ins: StandIns) -> FakeConnection:
    plugin_stand_ins.connection = FakeConnection()
    return plugin_stand_ins.connection


@pytest.mark.usefixtures("split_regex")
def test_issue_reproduction(plugin_stand_ins: StandIns, connection: FakeConnection) -> None:
    _wire(plugin_stand_ins, {"port": lambda run: run("stand|look")}, {"port"})
    _type("say hi|port")
    assert _sent(connection) == ["say hi", "stand", "look"]


@pytest.mark.usefixtures("split_regex")
def test_middle_part(plugin_stand_ins: StandIns, connection: FakeConnection) -> None:
    _wire(plugin_stand_ins, {"port": lambda run: run("stand|look")}, {"port"})
    _type("a|port|b")
    assert _sent(connection) == ["a", "stand", "look", "b"]


@pytest.mark.usefixtures("split_regex")
def test_several_resends_keep_call_order(
    plugin_stand_ins: StandIns, connection: FakeConnection
) -> None:
    def handler(run: Callable[[str], None]) -> None:
        run("one")
        run("two")

    _wire(plugin_stand_ins, {"port": handler}, {"port"})
    _type("a|port|b")
    assert _sent(connection) == ["a", "one", "two", "b"]


@pytest.mark.usefixtures("split_regex")
def test_nested_depth(plugin_stand_ins: StandIns, connection: FakeConnection) -> None:
    _wire(
        plugin_stand_ins,
        {
            "outer": lambda run: run("p|inner"),
            "inner": lambda run: run("q|r"),
        },
        {"outer", "inner"},
    )
    _type("x|outer|y")
    assert _sent(connection) == ["x", "p", "q", "r", "y"]


@pytest.mark.usefixtures("split_regex")
def test_outer_line_is_not_dropped(plugin_stand_ins: StandIns, connection: FakeConnection) -> None:
    _wire(plugin_stand_ins, {"port": lambda run: run("stand|look")})
    _type("a|port|b")
    assert _sent(connection) == ["a", "port", "stand", "look", "b"]


@pytest.mark.usefixtures("split_regex")
def test_outside_any_process_sends_at_once(
    plugin_stand_ins: StandIns, connection: FakeConnection
) -> None:
    run = _wire(plugin_stand_ins, {})
    run("look")
    assert _sent(connection) == ["look"]
    assert resend_capture.get() is None
    assert resend_anchor.get() is None


@pytest.mark.usefixtures("split_regex")
def test_closed_capture_sends_at_once(
    plugin_stand_ins: StandIns, connection: FakeConnection
) -> None:
    closed = PendingMudSends(NetworkData([]))
    closed.close()
    with capturing_resends(closed):
        _type("look")
    assert _sent(connection) == ["look"]
    assert closed.tail() == []


@pytest.mark.usefixtures("split_regex")
@pytest.mark.parametrize("use_foreign_anchor", [False, True])
def test_unmatched_anchor_goes_after_all_lines(
    plugin_stand_ins: StandIns, connection: FakeConnection, use_foreign_anchor: bool
) -> None:
    foreign = NetworkDataLine("other", originated="client")

    def handler(run: Callable[[str], None]) -> None:
        with resending_in_place_of(foreign if use_foreign_anchor else None):
            _type("late1")
            _type("late2")

    _wire(plugin_stand_ins, {"port": handler}, {"port"})
    _type("a|port|b")
    assert _sent(connection) == ["a", "b", "late1", "late2"]


@pytest.mark.usefixtures("split_regex")
def test_no_connection_still_runs_held_records(plugin_stand_ins: StandIns) -> None:
    messages: list[NetworkData] = []
    original = SendDataDirectlyToMud.__init__

    def spy(self: SendDataDirectlyToMud, message: NetworkData, *a: Any, **kw: Any) -> None:
        messages.append(message)
        original(self, message, *a, **kw)

    plugin_stand_ins.connection = None
    _wire(plugin_stand_ins, {"port": lambda run: run("look")}, {"port"})
    SendDataDirectlyToMud.__init__ = spy  # type: ignore[method-assign]
    try:
        _type("a|port")
    finally:
        SendDataDirectlyToMud.__init__ = original  # type: ignore[method-assign]
    assert len(messages) == 2
    assert all(message.locked for message in messages)
    reads = [e for e in plugin_stand_ins.events if e.name == TO_MUD_DATA_READ]
    assert len(reads) == 2


@pytest.mark.usefixtures("split_regex")
def test_outer_read_event_holds_only_outer_lines(
    plugin_stand_ins: StandIns, connection: FakeConnection
) -> None:
    _wire(plugin_stand_ins, {"port": lambda run: run("look")}, {"port"})
    _type("a|port|b")
    reads = [e for e in plugin_stand_ins.events if e.name == TO_MUD_DATA_READ]
    assert [e.snapshot for e in reads][-1] == ["ANSI(a)\r\n", "ANSI(b)\r\n"]
    assert next(e.snapshot for e in reads) == ["ANSI(look)\r\n"]


@pytest.mark.usefixtures("split_regex")
def test_raising_hook_resets_context(plugin_stand_ins: StandIns) -> None:
    plugin_stand_ins.connection = FakeConnection()

    def boom(_name: str, _data: list[Any]) -> None:
        raise RuntimeError("boom")

    plugin_stand_ins.hook = boom
    with pytest.raises(RuntimeError):
        _type("a|b")
    assert resend_capture.get() is None
    assert resend_anchor.get() is None


def test_pending_add_matches_by_identity() -> None:
    line = NetworkDataLine("x", originated="client")
    equal = NetworkDataLine("x", originated="client")
    pending = PendingMudSends(NetworkData([line]))
    first, second, third = (MagicMock(), MagicMock(), MagicMock())
    pending.add(line, first)
    pending.add(equal, third)
    pending.add(line, second)
    assert pending.after(line) == [first, second]
    assert pending.after(equal) == []
    assert pending.tail() == [third]
    assert pending.open
    pending.close()
    assert not pending.open

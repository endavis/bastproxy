"""`plugins.core.commands:command.line.run` runs a line as if the user typed it (#564)."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs.records.rtypes.muddata import ProcessDataToMud
from bastproxy.libs.records.rtypes.networkdata import NetworkData, NetworkDataLine
from bastproxy.plugins.core.commands.plugin import _commands as commands_module
from bastproxy.plugins.core.commands.plugin._commands import CommandsPlugin
from bastproxy.plugins.core.events.libs.data._event import EventDataRecord

from .conftest import FakeConnection, StandIns

Dispatched = list[tuple[str, str | None]]


def _wire(
    stand_ins: StandIns, history: list[str], on_command: dict[str, Any] | None = None
) -> tuple[MagicMock, Dispatched]:
    """Drive the real history callback; return the stub plugin and the dispatched commands.

    `on_command` maps a proxy command line to a callable run as that command's handler.
    """
    dispatched: Dispatched = []
    current: dict[str, Any] = {}
    handlers = on_command or {}

    def api(name: str) -> Any:
        if name == "plugins.core.settings:setting.get":
            return lambda plugin_id, key: "#bp"
        if name == "plugins.core.events:event.current.record.get":
            return lambda: current.get("record")
        if name == "libs.api:caller.owner.get":
            return lambda: "plugins.test.caller"
        raise AssertionError(name)

    stub = MagicMock()
    stub.plugin_id = "plugins.core.commands"
    stub.api = api
    stub.current_input_event = None
    stub.add_command_to_history.side_effect = history.append

    def run_internal() -> None:
        record = current["record"]
        line = record["line"].line
        record["showinhistory"] = True
        dispatched.append((line, record["client_id"]))
        if line in handlers:
            handlers[line]()

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
    return stub, dispatched


def _type(line: str, client_id: str = "c1") -> None:
    ProcessDataToMud(
        NetworkData([NetworkDataLine(line, originated="client")]), client_id=client_id
    )()


def _execute(stub: MagicMock, line: str, **kwargs: Any) -> None:
    CommandsPlugin._api_command_line_run(stub, line, **kwargs)


def _sent(connection: FakeConnection) -> list[str]:
    return [str(line.line) for line in connection.sent]


@pytest.mark.usefixtures("split_regex")
def test_execute_runs_proxy_command_not_in_history(plugin_stand_ins: StandIns) -> None:
    plugin_stand_ins.connection = FakeConnection()
    history: list[str] = []
    stub, dispatched = _wire(plugin_stand_ins, history)
    _execute(stub, "#bp.a.list")
    assert dispatched == [("#bp.a.list", None)]
    assert history == []


@pytest.mark.usefixtures("split_regex")
def test_execute_sends_mud_command_not_in_history(plugin_stand_ins: StandIns) -> None:
    connection = FakeConnection()
    plugin_stand_ins.connection = connection
    history: list[str] = []
    stub, dispatched = _wire(plugin_stand_ins, history)
    _execute(stub, "look")
    assert dispatched == []
    assert any("look" in line for line in _sent(connection))
    assert history == []


@pytest.mark.usefixtures("split_regex")
def test_execute_splits_on_the_command_separator(plugin_stand_ins: StandIns) -> None:
    connection = FakeConnection()
    plugin_stand_ins.connection = connection
    stub, dispatched = _wire(plugin_stand_ins, [])
    _execute(stub, "look|#bp.a.list|score")
    assert dispatched == [("#bp.a.list", None)]
    sent = _sent(connection)
    assert any("look" in line for line in sent)
    assert any("score" in line for line in sent)


@pytest.mark.usefixtures("split_regex")
def test_execute_show_in_history_true_records_the_line(plugin_stand_ins: StandIns) -> None:
    plugin_stand_ins.connection = FakeConnection()
    history: list[str] = []
    stub, _ = _wire(plugin_stand_ins, history)
    _execute(stub, "look", show_in_history=True)
    assert history == ["look"]


@pytest.mark.usefixtures("split_regex")
def test_execute_uses_the_clients_id_while_handling_its_input(
    plugin_stand_ins: StandIns,
) -> None:
    plugin_stand_ins.connection = FakeConnection()
    holder: dict[str, Any] = {}
    stub, dispatched = _wire(
        plugin_stand_ins, [], {"#bp.a.outer": lambda: _execute(holder["stub"], "#bp.a.inner")}
    )
    holder["stub"] = stub
    _type("#bp.a.outer", client_id="c7")
    assert dispatched == [("#bp.a.outer", "c7"), ("#bp.a.inner", "c7")]


@pytest.mark.usefixtures("split_regex")
def test_execute_inside_a_running_command(plugin_stand_ins: StandIns) -> None:
    """A handler can run a nested proxy command and a MUD line; the outer line is still recorded."""
    connection = FakeConnection()
    plugin_stand_ins.connection = connection
    history: list[str] = []
    holder: dict[str, Any] = {}

    def outer() -> None:
        _execute(holder["stub"], "#bp.a.inner")
        _execute(holder["stub"], "look")

    stub, dispatched = _wire(plugin_stand_ins, history, {"#bp.a.outer": outer})
    holder["stub"] = stub
    _type("#bp.a.outer")
    assert [line for line, _ in dispatched] == ["#bp.a.outer", "#bp.a.inner"]
    assert any("look" in line for line in _sent(connection))
    assert history == ["#bp.a.outer"]


def test_execute_runs_when_the_current_event_record_has_no_client_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An event whose record lacks `client_id` (e.g. a plugin load) must not raise (#581)."""
    record = EventDataRecord(
        owner_id="test581", event_name="ev_plugin_loaded", data={"plugin_id": "plugins.test.x"}
    )
    assert "client_id" not in record
    received: list[dict[str, Any]] = []
    monkeypatch.setattr(
        commands_module,
        "execute_line",
        lambda line, **kwargs: received.append({"line": line, **kwargs}),
    )

    def api(name: str) -> Any:
        if name == "plugins.core.events:event.current.record.get":
            return lambda: record
        if name == "libs.api:caller.owner.get":
            return lambda: "plugins.test.caller"
        raise AssertionError(name)

    stub = MagicMock()
    stub.api = api
    CommandsPlugin._api_command_line_run(stub, "#bp.a.list")
    assert received == [
        {
            "line": "#bp.a.list",
            "owner_id": "plugins.test.caller",
            "client_id": None,
            "show_in_history": False,
        }
    ]


def test_line_run_sets_anchor_to_current_record_line(
    monkeypatch: pytest.MonkeyPatch, plugin_stand_ins: StandIns
) -> None:
    from bastproxy.libs.context import resend_anchor

    seen: list[Any] = []
    monkeypatch.setattr(
        commands_module, "execute_line", lambda *args, **kwargs: seen.append(resend_anchor.get())
    )
    line = NetworkDataLine("x", originated="client")
    stub, _ = _wire(plugin_stand_ins, [])
    stub.api = lambda name: {
        "plugins.core.events:event.current.record.get": lambda: {"line": line},
        "libs.api:caller.owner.get": lambda: "o",
    }[name]
    _execute(stub, "look")
    stub.api = lambda name: {
        "plugins.core.events:event.current.record.get": lambda: {"client_id": "c"},
        "libs.api:caller.owner.get": lambda: "o",
    }[name]
    _execute(stub, "look")
    stub.api = lambda name: {
        "plugins.core.events:event.current.record.get": lambda: None,
        "libs.api:caller.owner.get": lambda: "o",
    }[name]
    _execute(stub, "look")
    assert seen == [line, None, None]
    assert resend_anchor.get() is None

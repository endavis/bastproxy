"""Tests for mudcmds type cleanup on plugin unload and type.add (#122)."""

from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins.core.mudcmds.plugin._mudcmds import MUDCmdsPlugin, QueuedCommand

PID = "plugins.test.a"
OTHER = "plugins.test.b"


def _stub() -> MagicMock:
    """Build a stub mudcmds plugin with real containers and a routing api."""
    stub = MagicMock()
    stub.plugin_id = "plugins.core.mudcmds"
    stub.cmds = {}
    stub.current_command = None
    stub.queue = []
    stub.timing_uid = None
    calls: list[str] = []
    stub.calls = calls

    def api(name: str) -> Any:
        calls.append(name)
        if name == "plugins.core.mudcmds:type.remove":
            return lambda t: MUDCmdsPlugin._api_type_remove(stub, t)
        if name == "plugins.core.events:event.current.record.get":
            return lambda: {"plugin_id": PID}
        if name == "plugins.core.mudcmds:type.remove.for.plugin":
            return lambda p: MUDCmdsPlugin._api_type_remove_for_plugin(stub, p)
        if name == "libs.api:caller.owner.get":
            return lambda **k: PID
        return lambda *a, **k: None

    stub.api = api
    return stub


def test_unload_removes_owned_types() -> None:
    """Unloading the owner removes its types, keeps others, raises nothing."""
    stub = _stub()
    MUDCmdsPlugin._api_type_add(stub, "t1", "cmd1", "^a$", owner=PID, plugin=True)
    MUDCmdsPlugin._api_type_add(stub, "t2", "cmd2", "^b$", owner=PID, plugin=True)
    MUDCmdsPlugin._api_type_add(stub, "t3", "cmd3", "^c$", owner=OTHER, plugin=True)

    MUDCmdsPlugin._eventcb_plugin_unloaded(stub)

    assert list(stub.cmds) == ["t3"]


def test_type_add_without_current_command() -> None:
    """type.add works when no command is current."""
    stub = _stub()

    MUDCmdsPlugin._api_type_add(stub, "t1", "cmd1", "^a$")

    assert stub.cmds["t1"].owner == PID


def test_timing_uses_registered_api() -> None:
    """start/finish use libs.timing:timing.start/finish with the returned uid."""
    stub = _stub()
    seen: list[tuple[str, Any]] = []

    def api(name: str) -> Any:
        def call(*a: Any, **k: Any) -> Any:
            seen.append((name, a))
            return "uid1" if name == "libs.timing:timing.start" else None

        return call

    stub.api = api
    MUDCmdsPlugin._api_command_start(stub, "t1")
    stub.current_command = QueuedCommand(cmd="c", ctype="t1", plugin=PID)
    stub._finish_timing = lambda: MUDCmdsPlugin._finish_timing(stub)
    stub.sendnext = lambda: None
    MUDCmdsPlugin._api_command_finish(stub, "t1")

    assert ("libs.timing:timing.start", ("cmd_t1",)) in seen
    assert ("libs.timing:timing.finish", ("uid1",)) in seen


def _stub_recording_events() -> tuple[MagicMock, list[tuple[str, tuple[Any, ...]]]]:
    """Build a stub whose event.add calls are recorded."""
    stub = _stub()
    events: list[tuple[str, tuple[Any, ...]]] = []
    base_api = stub.api

    def api(name: str) -> Any:
        if name == "plugins.core.events:event.add":

            def add(*a: Any, **k: Any) -> None:
                events.append((name, a))

            return add
        return base_api(name)

    stub.api = api
    return stub, events


def test_type_add_owner_kwarg_is_stored_and_used_for_events() -> None:
    """owner= alone is stored and passed to both event.add calls (#437)."""
    stub, events = _stub_recording_events()

    MUDCmdsPlugin._api_type_add(stub, "t1", "cmd1", "^a$", owner=OTHER)

    assert stub.cmds["t1"].owner == OTHER
    assert [a for _, a in events] == [("cmd_t1_send", OTHER), ("cmd_t1_completed", OTHER)]


def test_type_add_plugin_kwarg_alone_does_not_raise() -> None:
    """plugin= without owner= is ignored and the caller owner is stored (#437)."""
    stub = _stub()

    MUDCmdsPlugin._api_type_add(stub, "t1", "cmd1", "^a$", plugin=True)

    assert stub.cmds["t1"].owner == PID


def test_type_add_no_kwargs_uses_caller_owner() -> None:
    """With no kwargs the caller owner is stored and used for events (#437)."""
    stub, events = _stub_recording_events()

    MUDCmdsPlugin._api_type_add(stub, "t1", "cmd1", "^a$")

    assert stub.cmds["t1"].owner == PID
    assert [a[1] for _, a in events] == [PID, PID]

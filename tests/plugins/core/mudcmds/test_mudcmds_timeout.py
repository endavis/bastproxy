"""Tests for timing out a queued mud command that never finishes (#734)."""

import logging
from functools import partial
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from bastproxy.plugins.core.mudcmds.plugin import _mudcmds
from bastproxy.plugins.core.mudcmds.plugin._mudcmds import MUDCmdsPlugin, QueuedCommand

from .test_mudcmds_records import PID, _add, _stub

TIMER = "plugins.core.mudcmds_command_timeout"


class Calls:
    """Records timer and event calls made through a stub's api."""

    def __init__(self) -> None:
        self.timers_added: list[tuple[Any, ...]] = []
        self.timers_removed: list[str] = []
        self.events: list[tuple[str, Any]] = []
        self.finished_timing: list[str] = []
        self.timer_exists = True


def _wire(stub: MagicMock, setting: int = 5) -> Calls:
    """Wrap a records-test stub so timers, settings and events are observable."""
    calls = Calls()
    inner = stub.api

    def api(name: str) -> Any:
        if name == "plugins.core.timers:timer.add":

            def add(*args: Any, **kwargs: Any) -> None:
                calls.timers_added.append((*args, kwargs))

            return add
        if name == "plugins.core.timers:timer.exists":
            return lambda n: calls.timer_exists
        if name == "plugins.core.timers:timer.remove":
            return lambda n: calls.timers_removed.append(n)
        if name == "plugins.core.settings:setting.get":
            return lambda pid, n: setting
        if name == "plugins.core.events:event.raise":
            return lambda ev, args=None: calls.events.append((ev, args))
        if name == "libs.timing:timing.finish":
            return lambda uid: calls.finished_timing.append(uid)
        return inner(name)

    stub.api = api
    stub._timeout_timer_name = TIMER
    stub._timeout_seconds = lambda c: MUDCmdsPlugin._timeout_seconds(stub, c)
    stub._start_timeout = lambda c: MUDCmdsPlugin._start_timeout(stub, c)
    stub._cancel_timeout = lambda: MUDCmdsPlugin._cancel_timeout(stub)
    stub._command_timed_out = lambda c: MUDCmdsPlugin._command_timed_out(stub, c)
    return calls


def _q(ctype: str, cmd: str) -> QueuedCommand:
    return QueuedCommand(cmd=cmd, ctype=ctype, plugin=PID)


def _event_names(calls: Calls) -> list[str]:
    return [e for e, _ in calls.events]


def test_sending_adds_one_time_timer_with_setting_seconds() -> None:
    stub, _ = _stub()
    calls = _wire(stub, setting=7)
    _add(stub)
    with patch.object(_mudcmds, "SendDataDirectlyToMud"):
        MUDCmdsPlugin._api_command_queue(stub, "t1")
    name, callback, seconds, kwargs = calls.timers_added[0]
    assert name == TIMER
    assert seconds == 7
    assert kwargs == {"onetime": True, "plugin_id": "plugins.core.mudcmds"}
    assert isinstance(callback, partial)
    assert callback.args == (stub.current_command,)


def test_timeout_finishes_command_and_sends_next(caplog: pytest.LogCaptureFixture) -> None:
    stub, _ = _stub()
    calls = _wire(stub)
    after = MagicMock()
    _add(stub, "t1", "one", afterf=after)
    _add(stub, "t2", "two")
    cur = _q("t1", "one")
    stub.current_command = cur
    stub.timing_uid = "uid1"
    stub.queue = [_q("t2", "two")]
    with (
        patch.object(_mudcmds, "SendDataDirectlyToMud") as send,
        caplog.at_level(logging.WARNING),
    ):
        MUDCmdsPlugin._command_timed_out(stub, cur)
    after.assert_not_called()
    assert calls.finished_timing == ["uid1"]
    assert stub.timing_uid is None
    assert _event_names(calls) == ["cmd_t1_timeout", "cmd_t2_send"]
    assert calls.events[0][1] == {"cmd": "one", "seconds": 5}
    assert stub.current_command == _q("t2", "two")
    send.assert_called_once()
    assert len(calls.timers_added) == 1  # the next command is timed
    text = caplog.text
    assert "'one'" in text
    assert "t1" in text
    assert PID in text


def test_timeout_with_empty_queue_leaves_none() -> None:
    stub, _ = _stub()
    calls = _wire(stub)
    _add(stub)
    cur = _q("t1", "look")
    stub.current_command = cur
    MUDCmdsPlugin._command_timed_out(stub, cur)
    assert stub.current_command is None
    assert "cmd_t1_completed" not in _event_names(calls)


def test_stale_timer_changes_nothing() -> None:
    stub, _ = _stub()
    calls = _wire(stub)
    _add(stub)
    old = _q("t1", "look")
    cur = _q("t1", "look")
    stub.current_command = cur
    stub.queue = [_q("t1", "other")]
    MUDCmdsPlugin._command_timed_out(stub, old)
    assert stub.current_command is cur
    assert calls.events == []
    assert len(stub.queue) == 1


def test_stale_timer_after_idle_changes_nothing() -> None:
    stub, _ = _stub()
    calls = _wire(stub)
    _add(stub)
    MUDCmdsPlugin._command_timed_out(stub, _q("t1", "look"))
    assert stub.current_command is None
    assert calls.events == []


def test_normal_finish_cancels_timer_and_runs_afterf() -> None:
    stub, _ = _stub()
    calls = _wire(stub)
    after = MagicMock()
    _add(stub, afterf=after)
    stub.current_command = _q("t1", "look")
    MUDCmdsPlugin._api_command_finish(stub, "t1")
    assert calls.timers_removed == [TIMER]
    after.assert_called_once_with()
    assert _event_names(calls) == ["cmd_t1_completed"]
    assert "cmd_t1_timeout" not in _event_names(calls)


def test_finish_skips_remove_when_timer_gone() -> None:
    stub, _ = _stub()
    calls = _wire(stub)
    calls.timer_exists = False
    _add(stub)
    stub.current_command = _q("t1", "look")
    MUDCmdsPlugin._api_command_finish(stub, "t1")
    assert calls.timers_removed == []


def test_fixqueue_cancels_timer() -> None:
    stub, _ = _stub()
    calls = _wire(stub)
    _add(stub)
    stub.current_command = _q("t1", "look")
    MUDCmdsPlugin._command_fixqueue(stub)
    assert calls.timers_removed == [TIMER]
    assert stub.current_command is None


def test_type_remove_of_current_type_cancels_timer() -> None:
    stub, _ = _stub()
    calls = _wire(stub)
    _add(stub)
    stub.current_command = _q("t1", "look")
    MUDCmdsPlugin._api_type_remove(stub, "t1")
    assert calls.timers_removed == [TIMER]


def test_type_remove_of_other_type_keeps_timer() -> None:
    stub, _ = _stub()
    calls = _wire(stub)
    _add(stub, "t1")
    _add(stub, "t2", "other")
    stub.current_command = _q("t2", "other")
    MUDCmdsPlugin._api_type_remove(stub, "t1")
    assert calls.timers_removed == []


def test_per_type_override_is_used() -> None:
    stub, _ = _stub()
    calls = _wire(stub, setting=5)
    _add(stub, "t1", "one", timeout=2)
    _add(stub, "t2", "two")
    assert stub.cmds["t1"].timeout == 2
    assert stub.cmds["t2"].timeout is None
    with patch.object(_mudcmds, "SendDataDirectlyToMud"):
        MUDCmdsPlugin._api_command_queue(stub, "t1")
        MUDCmdsPlugin._api_command_finish(stub, "t1")
        MUDCmdsPlugin._api_command_queue(stub, "t2")
    assert [t[2] for t in calls.timers_added] == [2, 5]


@pytest.mark.parametrize("bad", [0, -1, True, 1.5, "5"])
def test_invalid_override_rejected(bad: Any, caplog: pytest.LogCaptureFixture) -> None:
    stub, _ = _stub()
    _wire(stub)
    with caplog.at_level(logging.ERROR):
        _add(stub, "t1", "one", timeout=bad)
    assert "t1" not in stub.cmds
    assert "invalid timeout" in caplog.text


def test_timeout_event_arg_descriptions() -> None:
    stub, _ = _stub()
    added: dict[str, Any] = {}
    inner = stub.api

    def api(name: str) -> Any:
        if name == "plugins.core.events:event.add":
            return lambda ev, owner, **kw: added.update({ev: kw})
        return inner(name)

    stub.api = api
    _add(stub)
    assert set(added["cmd_t1_timeout"]["arg_descriptions"]) == {"cmd", "seconds"}


def test_setting_registered_with_default_and_validator() -> None:
    stub = MagicMock()
    stub.plugin_id = "plugins.core.mudcmds"
    added: list[tuple[Any, dict[str, Any]]] = []
    stub.api = lambda name: lambda *a, **k: added.append((a, k))
    MUDCmdsPlugin._phook_initialize(stub)
    args, kwargs = added[0]
    assert args[:4] == ("plugins.core.mudcmds", "command_timeout", 5, int)
    validator = kwargs["validator"]
    assert validator(0) != ""
    assert validator(1) == ""

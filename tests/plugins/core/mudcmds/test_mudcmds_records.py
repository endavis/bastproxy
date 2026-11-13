"""Tests for the MudCmdType and QueuedCommand records and their readers (#419)."""

import dataclasses
import re
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from bastproxy.plugins.core.commands import CommandResult
from bastproxy.plugins.core.mudcmds.plugin import _mudcmds
from bastproxy.plugins.core.mudcmds.plugin._mudcmds import (
    MUDCmdsPlugin,
    MudCmdType,
    QueuedCommand,
)

PID = "plugins.test.a"


def test_mudcmdtype_fields_defaults_and_slots() -> None:
    """MudCmdType has the documented fields, None callbacks and slots."""
    fields = [f.name for f in dataclasses.fields(MudCmdType)]
    assert fields == ["cmd", "regex", "cregex", "ctype", "owner", "beforef", "afterf"]
    rec = MudCmdType(cmd="c", regex="^a$", cregex=re.compile("^a$"), ctype="t", owner=PID)
    assert rec.beforef is None
    assert rec.afterf is None
    assert not hasattr(rec, "__dict__")
    with pytest.raises(AttributeError):
        rec.bogus = 1  # type: ignore[attr-defined]


def test_queuedcommand_fields_and_slots() -> None:
    """QueuedCommand has cmd/ctype/plugin and slots."""
    assert [f.name for f in dataclasses.fields(QueuedCommand)] == ["cmd", "ctype", "plugin"]
    rec = QueuedCommand(cmd="c", ctype="t", plugin=PID)
    assert not hasattr(rec, "__dict__")
    with pytest.raises(AttributeError):
        rec.bogus = 1  # type: ignore[attr-defined]


def _stub() -> tuple[MagicMock, list[str]]:
    """Build a stub plugin with real containers; return it and the raised events."""
    stub = MagicMock()
    stub.plugin_id = "plugins.core.mudcmds"
    stub.cmds = {}
    stub.queue = []
    stub.current_command = None
    stub.timing_uid = None
    raised: list[str] = []

    def api(name: str) -> Any:
        if name == "plugins.core.events:event.raise":
            return lambda ev: raised.append(ev)
        if name == "libs.api:caller.owner.get":
            return lambda **k: PID
        return lambda *a, **k: None

    stub.api = api
    stub.sendnext = lambda: MUDCmdsPlugin.sendnext(stub)
    stub.checkinqueue = lambda c: MUDCmdsPlugin.checkinqueue(stub, c)
    stub._finish_timing = lambda: MUDCmdsPlugin._finish_timing(stub)
    return stub, raised


def _add(stub: MagicMock, ctype: str = "t1", cmd: str = "look", **kw: Any) -> None:
    MUDCmdsPlugin._api_type_add(stub, ctype, cmd, "^x$", **kw)


def test_type_add_stores_record() -> None:
    """type.add stores a MudCmdType with compiled regex and callbacks."""
    stub, _ = _stub()
    before = MagicMock()
    after = MagicMock()
    _add(stub, beforef=before, afterf=after)
    rec = stub.cmds["t1"]
    assert isinstance(rec, MudCmdType)
    assert rec.cmd == "look"
    assert rec.regex == "^x$"
    assert rec.cregex == re.compile("^x$")
    assert rec.ctype == "t1"
    assert rec.owner == PID
    assert rec.beforef is before
    assert rec.afterf is after


def test_queue_appends_and_sends_when_idle() -> None:
    """command.queue appends a QueuedCommand and sends it when idle."""
    stub, raised = _stub()
    _add(stub)
    with patch.object(_mudcmds, "SendDataDirectlyToMud") as send:
        MUDCmdsPlugin._api_command_queue(stub, "t1", "north")
    assert stub.queue == []
    assert stub.current_command == QueuedCommand(cmd="look north", ctype="t1", plugin=PID)
    assert raised == ["cmd_t1_send"]
    send.assert_called_once()
    send.return_value.assert_called_once_with()


def test_queue_while_busy_only_appends() -> None:
    """With a current command, queue appends without sending."""
    stub, _ = _stub()
    _add(stub)
    stub.current_command = QueuedCommand(cmd="other", ctype="t9", plugin=PID)
    with patch.object(_mudcmds, "SendDataDirectlyToMud") as send:
        MUDCmdsPlugin._api_command_queue(stub, "t1")
    assert stub.queue == [QueuedCommand(cmd="look", ctype="t1", plugin=PID)]
    send.assert_not_called()


def test_duplicate_not_queued_twice() -> None:
    """A command already in the queue is not queued again."""
    stub, _ = _stub()
    _add(stub)
    stub.current_command = QueuedCommand(cmd="other", ctype="t9", plugin=PID)
    with patch.object(_mudcmds, "SendDataDirectlyToMud"):
        MUDCmdsPlugin._api_command_queue(stub, "t1")
        MUDCmdsPlugin._api_command_queue(stub, "t1")
    assert len(stub.queue) == 1


def test_duplicate_of_current_command_not_queued() -> None:
    """A command equal to current_command.cmd is not queued."""
    stub, _ = _stub()
    _add(stub)
    stub.current_command = QueuedCommand(cmd="look", ctype="t1", plugin=PID)
    with patch.object(_mudcmds, "SendDataDirectlyToMud") as send:
        MUDCmdsPlugin._api_command_queue(stub, "t1")
    assert stub.queue == []
    send.assert_not_called()


def test_finish_runs_afterf_raises_event_and_sends_next() -> None:
    """command.finish runs afterf, raises completed, resets and sends the next."""
    stub, raised = _stub()
    after = MagicMock()
    _add(stub, afterf=after)
    _add(stub, ctype="t2", cmd="south")
    stub.current_command = QueuedCommand(cmd="look", ctype="t1", plugin=PID)
    stub.queue = [QueuedCommand(cmd="south", ctype="t2", plugin=PID)]
    with patch.object(_mudcmds, "SendDataDirectlyToMud"):
        MUDCmdsPlugin._api_command_finish(stub, "t1")
    after.assert_called_once_with()
    assert raised == ["cmd_t1_completed", "cmd_t2_send"]
    assert stub.current_command == QueuedCommand(cmd="south", ctype="t2", plugin=PID)
    assert stub.queue == []


def test_finish_without_next_resets_to_none() -> None:
    """command.finish with an empty queue leaves current_command None."""
    stub, _ = _stub()
    _add(stub)
    stub.current_command = QueuedCommand(cmd="look", ctype="t1", plugin=PID)
    MUDCmdsPlugin._api_command_finish(stub, "t1")
    assert stub.current_command is None


def test_finish_with_other_ctype_does_nothing() -> None:
    """command.finish for a different ctype changes nothing."""
    stub, raised = _stub()
    after = MagicMock()
    _add(stub, afterf=after)
    cur = QueuedCommand(cmd="look", ctype="t1", plugin=PID)
    stub.current_command = cur
    MUDCmdsPlugin._api_command_finish(stub, "t2")
    after.assert_not_called()
    assert raised == []
    assert stub.current_command is cur


def test_finish_with_no_current_command_does_nothing() -> None:
    """command.finish when idle returns quietly."""
    stub, raised = _stub()
    MUDCmdsPlugin._api_command_finish(stub, "t1")
    assert raised == []


def test_sendnext_runs_beforef() -> None:
    """sendnext calls beforef before sending."""
    stub, _ = _stub()
    order: list[str] = []
    _add(stub, beforef=lambda: order.append("before"))
    stub.queue = [QueuedCommand(cmd="look", ctype="t1", plugin=PID)]
    with patch.object(_mudcmds, "SendDataDirectlyToMud") as send:
        send.return_value.side_effect = lambda: order.append("send")
        MUDCmdsPlugin.sendnext(stub)
    assert order == ["before", "send"]
    assert stub.current_command == QueuedCommand(cmd="look", ctype="t1", plugin=PID)


def test_sendnext_noop_when_busy_or_empty() -> None:
    """sendnext does nothing with an empty queue or a current command."""
    stub, raised = _stub()
    MUDCmdsPlugin.sendnext(stub)
    stub.queue = [QueuedCommand(cmd="a", ctype="t1", plugin=PID)]
    stub.current_command = QueuedCommand(cmd="b", ctype="t1", plugin=PID)
    MUDCmdsPlugin.sendnext(stub)
    assert raised == []
    assert len(stub.queue) == 1


def test_command_start_mismatch_skips_timing() -> None:
    """command.start for a non-current type does not start timing."""
    stub, _ = _stub()
    stub.current_command = QueuedCommand(cmd="look", ctype="t1", plugin=PID)
    MUDCmdsPlugin._api_command_start(stub, "t2")
    assert stub.timing_uid is None


def test_remove_for_plugin_uses_owner_attribute() -> None:
    """type.remove.for.plugin matches on the record owner."""
    stub, _ = _stub()
    _add(stub, ctype="t1", owner=PID)
    _add(stub, ctype="t2", owner="plugins.test.b")
    stub.api = lambda name: lambda t: MUDCmdsPlugin._api_type_remove(stub, t)
    MUDCmdsPlugin._api_type_remove_for_plugin(stub, PID)
    assert list(stub.cmds) == ["t2"]


def test_fixqueue_resets_to_none() -> None:
    """The fixqueue command resets current_command to None."""
    stub, _ = _stub()
    stub.current_command = QueuedCommand(cmd="look", ctype="t1", plugin=PID)
    result = MUDCmdsPlugin._command_fixqueue(stub)
    assert result == CommandResult(True, ["finished the currentcmd"])
    assert stub.current_command is None


def test_fixqueue_sends_next() -> None:
    """The fixqueue command sends the next queued command after resetting."""
    stub, raised = _stub()
    _add(stub, ctype="t2", cmd="south")
    stub.current_command = QueuedCommand(cmd="look", ctype="t1", plugin=PID)
    stub.queue = [QueuedCommand(cmd="south", ctype="t2", plugin=PID)]
    with patch.object(_mudcmds, "SendDataDirectlyToMud"):
        MUDCmdsPlugin._command_fixqueue(stub)
    assert stub.current_command == QueuedCommand(cmd="south", ctype="t2", plugin=PID)
    assert raised == ["cmd_t2_send"]


def test_fixqueue_when_idle_is_noop() -> None:
    """fixqueue with no current command leaves it None."""
    stub, _ = _stub()
    MUDCmdsPlugin._command_fixqueue(stub)
    assert stub.current_command is None

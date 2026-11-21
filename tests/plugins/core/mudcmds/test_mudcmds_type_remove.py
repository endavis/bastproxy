"""Tests for type.remove dropping a type's commands and the mudcmds input checks (#671)."""

import dataclasses
import logging
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from bastproxy.plugins.core.mudcmds.plugin import _mudcmds
from bastproxy.plugins.core.mudcmds.plugin._mudcmds import (
    MUDCmdsPlugin,
    MudCmdType,
    QueuedCommand,
)

from .test_mudcmds_records import PID, _add, _stub


def _queued(ctype: str, cmd: str) -> QueuedCommand:
    return QueuedCommand(cmd=cmd, ctype=ctype, plugin=PID)


def _with_calls(stub: MagicMock) -> list[str]:
    """Wrap stub.api to also record every api name called; type.remove is real."""
    inner = stub.api
    seen: list[str] = []

    def api(name: str) -> Any:
        seen.append(name)
        if name == "plugins.core.mudcmds:type.remove":
            return lambda t: MUDCmdsPlugin._api_type_remove(stub, t)
        return inner(name)

    stub.api = api
    return seen


def test_removing_current_type_sends_next_and_drops_its_queue() -> None:
    stub, raised = _stub()
    _add(stub, "t1", "one")
    _add(stub, "t2", "two")
    stub.current_command = _queued("t1", "one")
    stub.queue = [_queued("t1", "one2"), _queued("t2", "two")]
    with patch.object(_mudcmds, "SendDataDirectlyToMud") as send:
        MUDCmdsPlugin._api_type_remove(stub, "t1")
    assert stub.current_command.ctype == "t2"
    assert stub.queue == []
    assert raised == ["cmd_t2_send"]
    assert "cmd_t1_completed" not in raised
    send.assert_called_once()


def test_other_types_keep_their_order_and_current_command() -> None:
    stub, raised = _stub()
    _add(stub, "t1", "one")
    _add(stub, "t2", "two")
    current = _queued("t2", "cur")
    stub.current_command = current
    stub.queue = [_queued("t2", "a"), _queued("t1", "x"), _queued("t2", "b")]
    with patch.object(_mudcmds, "SendDataDirectlyToMud") as send:
        MUDCmdsPlugin._api_type_remove(stub, "t1")
    assert stub.current_command is current
    assert [q.cmd for q in stub.queue] == ["a", "b"]
    assert raised == []
    send.assert_not_called()


def test_clearing_current_finishes_timing_without_afterf() -> None:
    stub, _ = _stub()
    afterf = MagicMock()
    _add(stub, "t1", "one", afterf=afterf)
    seen = _with_calls(stub)
    stub.current_command = _queued("t1", "one")
    stub.timing_uid = "uid1"
    with patch.object(_mudcmds, "SendDataDirectlyToMud"):
        MUDCmdsPlugin._api_type_remove(stub, "t1")
    assert "libs.timing:timing.finish" in seen
    assert stub.timing_uid is None
    assert stub.current_command is None
    afterf.assert_not_called()


def test_idle_remove_sends_nothing() -> None:
    stub, raised = _stub()
    _add(stub, "t1", "one")
    with patch.object(_mudcmds, "SendDataDirectlyToMud") as send:
        MUDCmdsPlugin._api_type_remove(stub, "t1")
    assert "t1" not in stub.cmds
    assert raised == []
    send.assert_not_called()


def test_remove_for_plugin_clears_current_and_sends_next() -> None:
    stub, raised = _stub()
    _add(stub, "t1", "one", owner=PID)
    _add(stub, "t2", "two", owner="plugins.test.b")
    _with_calls(stub)
    stub.current_command = _queued("t1", "one")
    stub.queue = [_queued("t2", "two")]
    with patch.object(_mudcmds, "SendDataDirectlyToMud"):
        MUDCmdsPlugin._api_type_remove_for_plugin(stub, PID)
    assert stub.current_command.ctype == "t2"
    assert raised == ["cmd_t2_send"]


def test_queue_unknown_type_logs_error(caplog: pytest.LogCaptureFixture) -> None:
    stub, raised = _stub()
    with caplog.at_level(logging.ERROR), patch.object(_mudcmds, "SendDataDirectlyToMud") as send:
        MUDCmdsPlugin._api_command_queue(stub, "nosuch")
    assert any(r.levelno == logging.ERROR for r in caplog.records)
    assert stub.queue == []
    assert raised == []
    send.assert_not_called()


def test_add_invalid_regex_logs_error_and_adds_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    stub, raised = _stub()
    seen = _with_calls(stub)
    with caplog.at_level(logging.ERROR):
        MUDCmdsPlugin._api_type_add(stub, "t4", "y", "(")
    assert any(r.levelno == logging.ERROR for r in caplog.records)
    assert stub.cmds == {}
    assert "plugins.core.events:event.add" not in seen
    assert raised == []


def test_mudcmdtype_has_no_cregex() -> None:
    assert "cregex" not in [f.name for f in dataclasses.fields(MudCmdType)]

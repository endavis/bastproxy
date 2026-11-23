"""Tests for hiding a queued command's output (#738)."""

import logging
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from bastproxy.plugins.core.mudcmds.plugin import _mudcmds
from bastproxy.plugins.core.mudcmds.plugin._mudcmds import MUDCmdsPlugin

from .test_mudcmds_records import PID, _add, _stub
from .test_mudcmds_timeout import _wire


@dataclass
class FakeLine:
    """A line with the attributes the hide callback reads."""

    noansi: str
    is_prompt: bool = False
    send: bool = True
    internal: bool = False


def _hide_stub(**kw: Any) -> MagicMock:
    """A wired stub with type t1 (regex ^Name) added, hiding output."""
    stub, _ = _stub()
    _wire(stub)
    inner = stub.api
    holder: dict[str, Any] = {}

    def api(name: str) -> Any:
        if name == "plugins.core.events:event.current.record.get":
            return lambda: {"line": holder["line"]}
        return inner(name)

    stub.api = api
    stub._holder = holder
    MUDCmdsPlugin._api_type_add(stub, "t1", "look", "^Name", hide_output=True, **kw)
    return stub


def _queue(stub: MagicMock, ctype: str = "t1") -> None:
    with patch.object(_mudcmds, "SendDataDirectlyToMud"):
        MUDCmdsPlugin._api_command_queue(stub, ctype)


def _feed(stub: MagicMock, text: str, prompt: bool = False, internal: bool = False) -> FakeLine:
    line = FakeLine(text, is_prompt=prompt, internal=internal)
    stub._holder["line"] = line
    MUDCmdsPlugin._eventcb_hide_line(stub)
    return line


def _finish(stub: MagicMock, ctype: str = "t1") -> None:
    with patch.object(_mudcmds, "SendDataDirectlyToMud"):
        MUDCmdsPlugin._api_command_finish(stub, ctype)


def test_defaults_stored_and_unset_type_passes_lines() -> None:
    stub, _ = _stub()
    _add(stub)
    rec = stub.cmds["t1"]
    assert (rec.hide_output, rec.hide_start, rec.hide_end, rec.hide_max) == (False, None, None, 500)
    _wire(stub)
    stub.api = (
        lambda inner: (
            lambda n: (lambda: {"line": stub._line}) if n.endswith("record.get") else inner(n)
        )
    )(stub.api)
    _queue(stub)
    assert stub._hide_armed is None
    stub._line = FakeLine("^x$")
    MUDCmdsPlugin._eventcb_hide_line(stub)
    assert stub._line.send is True


@pytest.mark.parametrize(
    "kw",
    [
        {"hide_output": "yes"},
        {"hide_output": 1},
        {"hide_start": "("},
        {"hide_end": "("},
        {"hide_end": 5},
        {"hide_max": True},
        {"hide_max": "5"},
        {"hide_max": 0},
    ],
)
def test_invalid_args_add_nothing(kw: dict[str, Any], caplog: pytest.LogCaptureFixture) -> None:
    stub, _ = _stub()
    with caplog.at_level(logging.ERROR):
        _add(stub, **kw)
    assert stub.cmds == {}
    assert caplog.records


def test_start_opens_window_and_unrelated_lines_shown() -> None:
    stub = _hide_stub(hide_end="^End")
    _queue(stub)
    assert _feed(stub, "Bob tells you hi").send is True
    assert _feed(stub, "Name : x").send is False
    assert _feed(stub, "middle").send is False
    assert _feed(stub, "End").send is False
    assert _feed(stub, "after").send is True


def test_hide_start_overrides_regex() -> None:
    stub = _hide_stub(hide_start="^Begin", hide_end="^End")
    _queue(stub)
    assert _feed(stub, "Name : x").send is True
    assert _feed(stub, "Begin").send is False
    assert _feed(stub, "End").send is False


def test_prompt_close_after_finish() -> None:
    stub = _hide_stub()
    stub._prompts_seen = True
    _queue(stub)
    assert _feed(stub, "Name : x").send is False
    assert _feed(stub, "<prompt>", prompt=True).send is False  # before finish: stays open
    assert _feed(stub, "more").send is False
    _finish(stub)
    assert stub._hide_open is not None
    assert _feed(stub, "<prompt>", prompt=True).send is False
    assert _feed(stub, "next").send is True


def test_finish_on_prompt_line_closes_window() -> None:
    stub = _hide_stub()
    _queue(stub)
    assert _feed(stub, "Name : x").send is False
    _feed(stub, "<prompt>", prompt=True)
    _finish(stub)  # called while the prompt is still being processed
    assert stub._hide_open is None
    assert _feed(stub, "tell").send is True


def test_finish_on_non_prompt_line_waits_for_prompt() -> None:
    stub = _hide_stub()
    stub._prompts_seen = True
    _queue(stub)
    assert _feed(stub, "Name : x").send is False
    _finish(stub)
    assert stub._hide_open is not None
    assert _feed(stub, "<prompt>", prompt=True).send is False
    assert _feed(stub, "tell").send is True


def test_prompt_hidden_before_finish_on_later_line_waits() -> None:
    stub = _hide_stub()
    _queue(stub)
    assert _feed(stub, "Name : x").send is False
    assert _feed(stub, "<prompt>", prompt=True).send is False
    assert _feed(stub, "more").send is False
    _finish(stub)
    assert stub._hide_open is not None
    assert _feed(stub, "<prompt>", prompt=True).send is False
    assert _feed(stub, "tell").send is True


def test_no_prompt_marking_closes_at_finish() -> None:
    stub = _hide_stub()
    _queue(stub)
    assert _feed(stub, "Name : x").send is False
    _finish(stub)
    assert stub._hide_open is None
    assert _feed(stub, "next").send is True


def test_cap_shows_line_and_warns(caplog: pytest.LogCaptureFixture) -> None:
    stub = _hide_stub(hide_max=3)
    _queue(stub)
    sent = [_feed(stub, t).send for t in ("Name", "b", "c")]
    assert sent == [False, False, False]
    with caplog.at_level(logging.WARNING):
        assert _feed(stub, "d").send is True
    assert any("t1" in r.getMessage() for r in caplog.records)
    assert stub._hide_open is None
    assert _feed(stub, "e").send is True


def _opened(stub: MagicMock) -> None:
    _queue(stub)
    assert _feed(stub, "Name").send is False


def test_teardown_disconnect() -> None:
    stub = _hide_stub()
    stub._prompts_seen = True
    _opened(stub)
    MUDCmdsPlugin._eventcb_hide_disconnect(stub)
    assert stub._prompts_seen is False
    assert _feed(stub, "x").send is True


def test_teardown_timeout() -> None:
    stub = _hide_stub()
    _opened(stub)
    MUDCmdsPlugin._command_timed_out(stub, stub.current_command)
    assert _feed(stub, "x").send is True


def test_teardown_type_remove() -> None:
    stub = _hide_stub()
    _opened(stub)
    MUDCmdsPlugin._api_type_remove(stub, "t1")
    assert _feed(stub, "x").send is True


def test_teardown_remove_for_plugin() -> None:
    stub = _hide_stub()
    stub.api = (
        lambda inner: lambda n: stub._api_remove if n.endswith(":type.remove") else inner(n)
    )(stub.api)
    stub._api_remove = lambda c: MUDCmdsPlugin._api_type_remove(stub, c)
    _opened(stub)
    MUDCmdsPlugin._api_type_remove_for_plugin(stub, PID)
    assert _feed(stub, "x").send is True


def test_typed_command_never_hidden() -> None:
    stub = _hide_stub()
    assert stub.current_command is None
    assert _feed(stub, "Name : x").send is True


def test_internal_lines_not_hidden_or_counted() -> None:
    stub = _hide_stub(hide_max=2)
    _queue(stub)
    assert _feed(stub, "Name", internal=True).send is True
    assert stub._hide_open is None
    assert _feed(stub, "Name").send is False
    assert _feed(stub, "x", internal=True).send is True
    window: Any = stub._hide_open
    assert window.count == 1


def test_next_command_waits_for_old_window() -> None:
    stub = _hide_stub()
    stub._prompts_seen = True
    _opened(stub)
    _finish(stub)  # old window waits for a prompt
    old = stub._hide_open
    assert old is not None
    _queue(stub)  # sends the next command, arming a new window
    assert stub._hide_armed is not None
    assert _feed(stub, "Name again").send is False
    assert stub._hide_open is old
    assert _feed(stub, "<prompt>", prompt=True).send is False
    assert stub._hide_open is None
    assert stub._hide_armed is not None
    assert _feed(stub, "Name second").send is False
    assert stub._hide_open is not None

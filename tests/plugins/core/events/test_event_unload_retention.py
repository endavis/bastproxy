"""Regression tests for #127: an unloaded plugin must not be kept alive by its event."""

# Standard Library
import gc
import logging
import weakref
from collections.abc import Callable, Iterator
from typing import Any

# 3rd Party
import pytest

# Project
from bastproxy.libs.api import API
from bastproxy.plugins.core.events.plugin._event import Event

OWNER_ID = "zz127.owner"
OTHER_ID = "zz127.other"


class _Owner:
    """A plugin-like object with a callback."""

    def __init__(self, plugin_id: str, fail: bool = False) -> None:
        self.plugin_id = plugin_id
        self.fail = fail
        self.seen: list[Any] = []
        self.event: Event | None = None

    def cb(self) -> None:
        if self.event is not None:
            self.seen.append(self.event.current_callback)
        if self.fail:
            raise RuntimeError("boom")


@pytest.fixture
def events() -> Iterator[dict[str, Event]]:
    """Register stand-in APIs routed to the events under test."""
    registry: dict[str, Event] = {}
    api = API("test127")
    api.add("plugins.core.settings", "setting.get", lambda *_a, **_k: False, description="stand-in")
    api.add(
        "plugins.core.events",
        "event.unregister",
        lambda name, func: registry[name].unregister(func),
        description="stand-in",
    )
    try:
        yield registry
    finally:
        for full_name in (
            "plugins.core.settings:setting.get",
            "plugins.core.events:event.unregister",
        ):
            API._class_api.pop(full_name, None)


@pytest.fixture
def no_log_capture(monkeypatch: pytest.MonkeyPatch) -> Callable[[], None]:
    """Keep pytest's log handlers from retaining ``exc_info`` tracebacks."""

    def _drop() -> None:
        root = logging.getLogger()
        kept = [h for h in root.handlers if type(h).__name__ != "LogCaptureHandler"]
        monkeypatch.setattr(root, "handlers", kept)

    return _drop


def _setup(
    events: dict[str, Event], name: str, fail: bool = False, other_last: bool = False
) -> tuple[Event, "weakref.ReferenceType[_Owner]"]:
    event = Event(name, created_by="test127")
    events[name] = event
    owner = _Owner(OWNER_ID, fail=fail)
    owner.event = event
    event.register(owner.cb, owner.plugin_id, 50)
    if other_last:
        other = _Owner(OTHER_ID)
        event.register(other.cb, other.plugin_id, 60)
    event.raise_event({"x": 1}, "test127")
    return event, weakref.ref(owner)


def test_owner_freed_after_unload_with_history(events: dict[str, Event]) -> None:
    event, ref = _setup(events, "ev_test127_main")
    event.removeowner(OWNER_ID)
    gc.collect()
    assert ref() is None
    assert len(event.raised_events) == 1


def test_current_and_active_cleared_after_raise(events: dict[str, Event]) -> None:
    event, _ref = _setup(events, "ev_test127_cleared")
    assert event.current_callback is None
    assert event.active_event is None


def test_raising_callback_owner_freed(
    events: dict[str, Event], no_log_capture: Callable[[], None]
) -> None:
    no_log_capture()
    event, ref = _setup(events, "ev_test127_raises", fail=True)
    assert event.current_callback is None
    event.removeowner(OWNER_ID)
    gc.collect()
    assert ref() is None


def test_removeowner_clears_own_current_callback(events: dict[str, Event]) -> None:
    event = Event("ev_test127_rm", created_by="test127")
    events[event.name] = event
    owner = _Owner(OWNER_ID)
    other = _Owner(OTHER_ID)
    event.register(owner.cb, owner.plugin_id, 50)
    event.register(other.cb, other.plugin_id, 60)
    own_cb, other_cb = (
        next(iter(event.priority_dictionary[50])),
        next(iter(event.priority_dictionary[60])),
    )
    event.current_callback = other_cb
    event.removeowner(OWNER_ID)
    assert event.current_callback is other_cb
    event.current_callback = own_cb
    event.removeowner(OTHER_ID)
    assert event.current_callback is own_cb
    event.removeowner(OWNER_ID)
    assert event.current_callback is None


def test_current_callback_visible_while_running(events: dict[str, Event]) -> None:
    event = Event("ev_test127_running", created_by="test127")
    events[event.name] = event
    owner = _Owner(OWNER_ID)
    owner.event = event
    event.register(owner.cb, owner.plugin_id, 50)
    event.raise_event({"x": 1}, "test127")
    assert len(owner.seen) == 1
    assert owner.seen[0] is not None
    assert owner.seen[0].owner_id == OWNER_ID


def test_inspection_after_unload(events: dict[str, Event]) -> None:
    event, _ref = _setup(events, "ev_test127_inspect", other_last=True)
    assert event.count() == 2
    event.removeowner(OWNER_ID)
    assert event.getownerregistrations(OWNER_ID) == []
    assert event.count() == 1
    assert event.raised_count == 1


def test_raise_event_returns_recorded_event(events: dict[str, Event]) -> None:
    event = Event("ev_test127_ret", created_by="test127")
    events[event.name] = event
    result = event.raise_event({"x": 1}, "test127")
    assert result is not None
    assert event.raised_events[result.uuid] is result

"""Regression tests for #153: the per-event raised_events history is bounded."""

# Standard Library
from collections.abc import Iterator
from typing import Any
from unittest.mock import ANY, MagicMock

# 3rd Party
import pytest

# Project
from bastproxy.libs.api import API
from bastproxy.plugins.core.events.plugin._event import Event
from bastproxy.plugins.core.events.plugin._events import EventsPlugin


@pytest.fixture(autouse=True)
def restore_cap() -> Iterator[None]:
    """Restore the class-level cap after each test."""
    saved = Event.MAX_RAISED_EVENTS
    api = API("test153")
    api.add("plugins.core.settings", "setting.get", lambda *_a, **_k: False, description="stand-in")
    try:
        yield
    finally:
        Event.MAX_RAISED_EVENTS = saved
        API._class_api.pop("plugins.core.settings:setting.get", None)


def _event(name: str = "ev_test153_main") -> Event:
    return Event(name, created_by="test153")


def test_history_bounded_to_cap() -> None:
    event = _event()
    for i in range(50):
        event.raise_event({"x": i}, "test153")
    assert len(event.raised_events) == Event.MAX_RAISED_EVENTS


def test_oldest_evicted() -> None:
    event = _event()
    uuids = []
    for i in range(50):
        record = event.raise_event({"x": i}, "test153")
        assert record is not None
        uuids.append(record.uuid)
    cap = Event.MAX_RAISED_EVENTS
    assert list(event.raised_events) == uuids[-cap:]
    assert uuids[0] not in event.raised_events


def test_return_value_is_the_raise_record() -> None:
    event = _event()
    first = event.raise_event({"x": 1}, "test153")
    assert first is not None
    assert first.event_data["x"] == 1
    assert event.raised_events[first.uuid] is first
    second = event.raise_event({"x": 2}, "test153")
    assert second is not None
    assert second.event_data["x"] == 2


def test_raised_count_counts_all_raises() -> None:
    event = _event()
    for i in range(50):
        event.raise_event({"x": i}, "test153")
    assert event.raised_count == 50


def test_cap_zero_keeps_nothing() -> None:
    Event.MAX_RAISED_EVENTS = 0
    event = _event()
    result = event.raise_event({"x": 1}, "test153")
    assert result is not None
    assert len(event.raised_events) == 0
    assert event.raised_count == 1


def test_lowered_cap_applies_on_next_raise() -> None:
    event = _event()
    for i in range(10):
        event.raise_event({"x": i}, "test153")
    Event.MAX_RAISED_EVENTS = 3
    last = event.raise_event({"x": 10}, "test153")
    assert last is not None
    assert len(event.raised_events) == 3
    assert list(event.raised_events)[-1] == last.uuid


def test_nested_reraise_does_not_lose_outer_record() -> None:
    Event.MAX_RAISED_EVENTS = 2
    event = _event()
    depth = {"in": False}

    def cb() -> None:
        if depth["in"]:
            return
        depth["in"] = True
        for i in range(Event.MAX_RAISED_EVENTS + 2):
            event.raise_event({"inner": i}, "test153")

    event.register(cb, "test153.owner", 50)
    outer = event.raise_event({"x": "outer"}, "test153")
    assert outer is not None
    assert outer.event_data["x"] == "outer"
    assert len(event.raised_events) <= 2


def _stub(settings_value: Any = None, record: Any = None) -> MagicMock:
    stub = MagicMock()
    stub.plugin_id = "plugins.core.events"
    stub._apply_raised_history_size = lambda v: EventsPlugin._apply_raised_history_size(stub, v)
    calls: dict[str, MagicMock] = {"add": MagicMock()}

    def api(name: str) -> Any:
        if name == "plugins.core.settings:setting.add":
            return calls["add"]
        if name == "plugins.core.settings:setting.get":
            return lambda *_a, **_k: settings_value
        if name == "plugins.core.events:event.current.record.get":
            return lambda: record
        return MagicMock()

    stub.api = api
    stub.add_mock = calls["add"]
    return stub


def test_initialize_adds_setting_and_applies_it() -> None:
    stub = _stub(settings_value=4)
    EventsPlugin._phook_initialize(stub)
    stub.add_mock.assert_any_call(
        "plugins.core.events",
        "raised_history_size",
        10,
        int,
        "number of recent raises each event keeps in its raised_events history, 0 keeps none; older raises stay in the records manager",
        validator=ANY,
    )
    assert Event.MAX_RAISED_EVENTS == 4


def test_modified_handler_applies_new_value() -> None:
    stub = _stub(record={"newvalue": 7})
    EventsPlugin._eventcb_raised_history_size_modified(stub)
    assert Event.MAX_RAISED_EVENTS == 7
    stub = _stub(record={"newvalue": 0})
    EventsPlugin._eventcb_raised_history_size_modified(stub)
    assert Event.MAX_RAISED_EVENTS == 0


def test_negative_value_clamps_to_zero() -> None:
    stub = _stub(record={"newvalue": -5})
    EventsPlugin._eventcb_raised_history_size_modified(stub)
    assert Event.MAX_RAISED_EVENTS == 0


def test_none_leaves_cap_unchanged() -> None:
    Event.MAX_RAISED_EVENTS = 6
    EventsPlugin._apply_raised_history_size(_stub(), None)
    assert Event.MAX_RAISED_EVENTS == 6

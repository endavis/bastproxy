"""Regression tests for #283: the raise command must not create unknown events."""

# Standard Library
from collections.abc import Callable
from typing import Any

# Project
from bastproxy.plugins.core.events.plugin._event import Event
from bastproxy.plugins.core.events.plugin._events import EventsPlugin

PLUGIN_ID = "plugins.core.events"


class _FakeEvents:
    """Stand-in for EventsPlugin: real event.get/exists/raise command, stubbed api routing."""

    def __init__(self, event_name: str) -> None:
        self.plugin_id = PLUGIN_ID
        self.events: dict[str, Event] = {}
        self.raised: list[str] = []
        self._event_name = event_name

    def api(self, name: str) -> Callable[..., Any]:
        if name == "plugins.core.commands:command.current.args.get":
            return lambda: {"event": self._event_name}
        if name == f"{PLUGIN_ID}:event.get":
            return lambda event_name: EventsPlugin._api_event_get(self, event_name)
        if name == f"{PLUGIN_ID}:event.exists":
            return lambda event_name: EventsPlugin._api_event_exists(self, event_name)
        if name == f"{PLUGIN_ID}:event.raise":
            return lambda event_name: self.raised.append(event_name)
        raise AssertionError(name)


def _run(fake: _FakeEvents) -> list[str]:
    _ok, message = EventsPlugin._command_raise(fake)
    return list(message)


def test_unknown_event_is_not_created() -> None:
    fake = _FakeEvents("ev_test283_unknown")
    message = _run(fake)
    assert message == ["event does not exist: ev_test283_unknown"]
    assert "ev_test283_unknown" not in fake.events
    assert len(fake.events) == 0
    assert fake.raised == []


def test_empty_name_is_not_created() -> None:
    fake = _FakeEvents("")
    message = _run(fake)
    assert message == ["event does not exist: "]
    assert len(fake.events) == 0
    assert fake.raised == []


def test_known_event_is_raised() -> None:
    fake = _FakeEvents("ev_test283_known")
    fake.events["ev_test283_known"] = Event("ev_test283_known", created_by="test283")
    message = _run(fake)
    assert message == ["raised event: ev_test283_known"]
    assert fake.raised == ["ev_test283_known"]
    assert len(fake.events) == 1


def test_event_get_still_creates() -> None:
    fake = _FakeEvents("x")
    event = EventsPlugin._api_event_get(fake, "ev_test283_get")
    assert fake.events["ev_test283_get"] is event

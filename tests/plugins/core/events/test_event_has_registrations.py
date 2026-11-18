"""Tests for the event.has.registrations API (#565): it never creates an event."""

from typing import Any

import pytest

from bastproxy.plugins.core.events.plugin import _event
from bastproxy.plugins.core.events.plugin._event import Event
from bastproxy.plugins.core.events.plugin._events import EventsPlugin


class _FakeEvents:
    """Stand-in for EventsPlugin holding a real events dict."""

    def __init__(self) -> None:
        self.events: dict[str, Event] = {}


@pytest.fixture(autouse=True)
def quiet_log(monkeypatch: pytest.MonkeyPatch) -> None:
    """Silence the log_to calls Event.register makes."""

    def fake_log_to(*_a: Any, **_k: Any) -> None:
        return None

    monkeypatch.setattr(_event, "log_to", fake_log_to)


def _has(fake: _FakeEvents, name: str) -> bool:
    return bool(EventsPlugin._api_event_has_registrations(fake, name))


def _callback(**_kwargs: Any) -> None:
    return None


def test_unknown_event_is_false_and_not_created() -> None:
    fake = _FakeEvents()
    assert _has(fake, "ev_test565_unknown") is False
    assert fake.events == {}


def test_existing_event_without_registrations_is_false() -> None:
    fake = _FakeEvents()
    fake.events["ev_test565"] = Event("ev_test565", "test")
    assert _has(fake, "ev_test565") is False


def test_registered_then_unregistered() -> None:
    fake = _FakeEvents()
    event = Event("ev_test565", "test")
    fake.events["ev_test565"] = event
    event.register(_callback, "owner", 50)
    assert _has(fake, "ev_test565") is True
    event.unregister(_callback)
    assert _has(fake, "ev_test565") is False

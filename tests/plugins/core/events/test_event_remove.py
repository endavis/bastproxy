"""Tests for the event.remove API (#670)."""

from typing import Any

import pytest

from bastproxy.libs.context import raised_event
from bastproxy.plugins.core.events.plugin import _event
from bastproxy.plugins.core.events.plugin._event import Event
from bastproxy.plugins.core.events.plugin._events import EventsPlugin


class _FakeEvents:
    """Stand-in for EventsPlugin holding a real events dict."""

    plugin_id = "plugins.core.events"

    def __init__(self) -> None:
        self.events: dict[str, Event] = {}


@pytest.fixture(autouse=True)
def quiet_log(monkeypatch: pytest.MonkeyPatch) -> None:
    """Silence the log_to calls Event.register makes."""

    def fake_log_to(*_a: Any, **_k: Any) -> None:
        return None

    monkeypatch.setattr(_event, "log_to", fake_log_to)


def _remove(fake: _FakeEvents, name: str, force: bool = False) -> bool:
    return bool(EventsPlugin._api_event_remove(fake, name, force=force))


def _callback(**_kwargs: Any) -> None:
    return None


def test_unknown_event_is_false_and_creates_nothing() -> None:
    fake = _FakeEvents()
    assert _remove(fake, "ev_test670_unknown") is False
    assert fake.events == {}


def test_empty_event_is_removed() -> None:
    fake = _FakeEvents()
    fake.events["ev_test670"] = Event("ev_test670", "test")
    assert _remove(fake, "ev_test670") is True
    assert "ev_test670" not in fake.events


def test_registered_event_needs_force() -> None:
    fake = _FakeEvents()
    event = Event("ev_test670", "test")
    fake.events["ev_test670"] = event
    event.register(_callback, "owner", 50)
    assert _remove(fake, "ev_test670") is False
    assert "ev_test670" in fake.events
    assert _remove(fake, "ev_test670", force=True) is True
    assert "ev_test670" not in fake.events


def test_event_being_raised_is_refused() -> None:
    fake = _FakeEvents()
    fake.events["ev_test670"] = Event("ev_test670", "test")
    with raised_event("ev_test670"):
        assert _remove(fake, "ev_test670", force=True) is False
    assert "ev_test670" in fake.events

"""Regression tests for #278: the priority of @RegisterToEvent is honoured."""

# Standard Library
from collections.abc import Callable
from typing import Any

# Project
from bastproxy.plugins.core.events import RegisterToEvent
from bastproxy.plugins.core.events.plugin._event import Event
from bastproxy.plugins.core.events.plugin._events import EventsPlugin


class _StubEvents:
    """Just enough of EventsPlugin to run the real register and register-by-func APIs."""

    plugin_id = "plugins.core.events"

    def __init__(self) -> None:
        self.event = Event("ev_test278", created_by="test278")
        self.api_map: dict[str, Callable[..., Any]] = {
            "plugins.core.events:event.register": lambda *a, **k: EventsPlugin._api_event_register(
                self, *a, **k
            ),
            "libs.api:function.owner.get": lambda _func: "plugins.test278",
            "plugins.core.events:event.is.registered": lambda *_a: False,
            "plugins.core.events:event.get": lambda _name: self.event,
        }

    def api(self, name: str) -> Callable[..., Any]:
        return self.api_map[name]


class _Owner:
    @RegisterToEvent(event_name="ev_test278", priority=1)
    def _eventcb_first(self) -> None:
        """Decorated at priority 1."""

    @RegisterToEvent(event_name="ev_test278")
    def _eventcb_default(self) -> None:
        """Decorated with the default priority."""


def _stored_priorities(event: Event) -> dict[str, int]:
    return {
        cb.func.__name__: prio
        for prio, callbacks in event.priority_dictionary.items()
        for cb in callbacks
    }


def test_decorated_callback_is_stored_at_its_priority() -> None:
    stub = _StubEvents()
    owner = _Owner()
    EventsPlugin._api_event_register_by_func(stub, owner._eventcb_first)
    EventsPlugin._api_event_register_by_func(stub, owner._eventcb_default)
    assert _stored_priorities(stub.event) == {"_eventcb_first": 1, "_eventcb_default": 50}


def test_events_plugin_loaded_callback_is_decorated_at_priority_1() -> None:
    registration = EventsPlugin._eventcb_plugin_initialized.event_registration
    assert registration == [{"event_name": "ev_plugin_loaded", "priority": 1}]

"""Tests for the context-variable event stack and record registration (#248)."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs.api import API
from bastproxy.libs.context import event_stack
from bastproxy.libs.net.protocols import PROTOCOL_EVENTS
from bastproxy.libs.records.events import RECORD_EVENTS
from bastproxy.plugins.core.events.plugin._event import Event
from bastproxy.plugins.core.events.plugin._events import EventsPlugin


def _plugin() -> MagicMock:
    plugin = MagicMock()
    plugin.plugin_id = "plugins.core.events"
    plugin.global_raised_count = 0
    plugin.events = {}
    plugin.all_event_stack = MagicMock()

    def get(name: str) -> Event:
        event: Event = plugin.events.setdefault(name, Event(name, created_by="test248"))
        return event

    plugin.get_event = get
    plugin.api = lambda name: {
        "plugins.core.events:event.get": get,
        "libs.api:caller.owner.get": lambda **_k: "test248",
    }[name]
    plugin._api_event_current_name_get = lambda: EventsPlugin._api_event_current_name_get(plugin)
    return plugin


@pytest.fixture(autouse=True)
def _history_setting() -> Any:
    api = API("test248")
    api.add("plugins.core.settings", "setting.get", lambda *_a, **_k: False, description="stand-in")
    yield
    API._class_api.pop("plugins.core.settings:setting.get", None)


def test_stack_lists_active_events_in_order() -> None:
    plugin = _plugin()
    seen: dict[str, Any] = {}

    def inner_cb() -> None:
        seen["inner"] = EventsPlugin._api_event_stack_get(plugin)
        seen["name"] = EventsPlugin._api_event_current_name_get(plugin)

    def outer_cb() -> None:
        EventsPlugin._api_event_raise(plugin, "ev_inner", calledfrom="t")

    plugin.get_event("ev_inner").register(inner_cb, "t.owner", 50)
    plugin.get_event("ev_outer").register(outer_cb, "t.owner", 50)
    EventsPlugin._api_event_raise(plugin, "ev_outer", calledfrom="t")
    assert seen == {"inner": ["ev_outer", "ev_inner"], "name": "ev_inner"}
    assert event_stack.get() == ()
    assert EventsPlugin._api_event_current_name_get(plugin) is None


def test_stack_is_restored_when_a_callback_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    plugin = _plugin()
    event = plugin.get_event("ev_boom")

    def boom(*_a: Any, **_k: Any) -> None:
        assert event_stack.get() == ("ev_boom",)
        raise RuntimeError

    monkeypatch.setattr(event, "raise_event", boom)
    with pytest.raises(RuntimeError):
        EventsPlugin._api_event_raise(plugin, "ev_boom", calledfrom="t")
    assert event_stack.get() == ()


def test_initialize_registers_the_record_events() -> None:
    added: list[tuple[Any, ...]] = []

    class _Api:
        def __call__(self, name: str) -> Any:
            if name == "plugins.core.events:event.add":
                return lambda *a, **k: added.append((a, k))
            return MagicMock()

    plugin = MagicMock()
    plugin.plugin_id = "plugins.core.events"
    plugin.api = _Api()
    EventsPlugin._phook_initialize(plugin)
    specs = (*RECORD_EVENTS, *PROTOCOL_EVENTS)
    assert len(added) == len(specs)
    for (args, kwargs), spec in zip(added, specs, strict=True):
        assert args == (spec.name, spec.created_by)
        assert kwargs == {
            "description": spec.description,
            "arg_descriptions": spec.arg_descriptions,
        }

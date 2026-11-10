"""Tests for EventsPlugin registration, unregistration and discovery (#282)."""

# Standard Library
import logging
from collections.abc import Callable, Iterator
from typing import Any

# 3rd Party
import pytest

# Project
from bastproxy.libs.api import API
from bastproxy.plugins.core.events import RegisterToEvent
from bastproxy.plugins.core.events.plugin._event import Event
from bastproxy.plugins.core.events.plugin._events import EventsPlugin

OWNER_ID = "plugins.test282.owner"
OTHER_ID = "plugins.test282.other"


class _Owner:
    """A plugin-like object with decorated and undecorated callbacks."""

    def __init__(self, plugin_id: str = OWNER_ID) -> None:
        self.plugin_id = plugin_id

    @RegisterToEvent(event_name="ev_{plugin_id}_first", priority=10)
    def _eventcb_first(self) -> None:
        """Decorated, formatted event name."""

    @RegisterToEvent(event_name="ev_test282_a")
    @RegisterToEvent(event_name="ev_test282_b", priority=20)
    def _eventcb_two(self) -> None:
        """Decorated for two events."""

    def _eventcb_undecorated(self) -> None:
        """Right prefix but no decorator."""

    @RegisterToEvent(event_name="ev_test282_c")
    def not_prefixed(self) -> None:
        """Decorated but wrong prefix."""

    def plain(self) -> None:
        """Neither."""


class _Holder:
    """An object that holds a decorated owner as an attribute."""

    def __init__(self) -> None:
        self.child = _Owner()


class _Stub:
    """Just enough of EventsPlugin to run its real methods."""

    plugin_id = "plugins.core.events"

    def __init__(self) -> None:
        self.events: dict[str, Event] = {}
        self.current_record: dict[str, Any] | None = None
        self.instances: dict[str, Any] = {}
        self.api_map: dict[str, Callable[..., Any]] = {}
        for name, method in (
            ("event.register", EventsPlugin._api_event_register),
            ("event.register.by.func", EventsPlugin._api_event_register_by_func),
            ("event.unregister", EventsPlugin._api_event_unregister),
            ("event.unregister.for.owner", EventsPlugin._api_event_unregister_for_owner),
            ("event.is.registered", EventsPlugin._api_event_is_registered),
            ("event.get", EventsPlugin._api_event_get),
        ):
            self.api_map[f"plugins.core.events:{name}"] = self._bind(method)
        self.api_map["libs.api:function.owner.get"] = API("test282")._api_function_owner_get
        self.api_map["plugins.core.events:event.current.record.get"] = lambda: self.current_record
        self.api_map["libs.plugins.loader:plugin.instance.get"] = self.instances.__getitem__

    def _bind(self, method: Callable[..., Any]) -> Callable[..., Any]:
        return lambda *a, **k: method(self, *a, **k)

    def api(self, name: str) -> Callable[..., Any]:
        return self.api_map[name]

    def get_event_registration_functions_in_object(self, base: object, recurse: bool = True) -> Any:
        return EventsPlugin.get_event_registration_functions_in_object(self, base, recurse)  # type: ignore[arg-type]

    def get_ignored_event_registration_functions_in_object(
        self, base: object, recurse: bool = True
    ) -> Any:
        return EventsPlugin.get_ignored_event_registration_functions_in_object(
            self,  # type: ignore[arg-type]
            base,
            recurse,
        )

    def _register_events_for_plugin(self, plugin_id: str) -> None:
        EventsPlugin._register_events_for_plugin(self, plugin_id)  # type: ignore[arg-type]


@pytest.fixture
def stub() -> Iterator[_Stub]:
    """A stub events plugin whose events call back into its own unregister api."""
    s = _Stub()
    api = API("test282")
    api.add(
        "plugins.core.events",
        "event.unregister",
        lambda name, func: s.events[name].unregister(func),
        description="stand-in",
    )
    try:
        yield s
    finally:
        API._class_api.pop("plugins.core.events:event.unregister", None)


def _names(event: Event) -> list[tuple[int, str]]:
    return sorted(
        (p, cb.func.__name__) for p, cbs in event.priority_dictionary.items() for cb in cbs
    )


def test_register_stores_callback_with_owner_and_priority(stub: _Stub) -> None:
    owner = _Owner()
    stub.api("plugins.core.events:event.register")("ev_test282", owner._eventcb_first, prio=7)
    event = stub.events["ev_test282"]
    assert _names(event) == [(7, "_eventcb_first")]
    assert event.getownerregistrations(OWNER_ID) == [
        {"function_name": "_eventcb_first", "priority": 7}
    ]


def test_register_default_priority_is_50(stub: _Stub) -> None:
    stub.api("plugins.core.events:event.register")("ev_test282", _Owner()._eventcb_first)
    assert _names(stub.events["ev_test282"]) == [(50, "_eventcb_first")]


def test_register_without_owner_logs_and_registers_nothing(
    stub: _Stub, caplog: pytest.LogCaptureFixture
) -> None:
    stub.api_map["libs.api:function.owner.get"] = lambda _f: ""
    with caplog.at_level(logging.ERROR):
        stub.api("plugins.core.events:event.register")("ev_test282", _Owner()._eventcb_first)
    assert "could not find owner" in caplog.text
    assert "ev_test282" not in stub.events


def test_register_again_with_new_priority_moves_callback(stub: _Stub) -> None:
    owner = _Owner()
    register = stub.api("plugins.core.events:event.register")
    register("ev_test282", owner._eventcb_first, prio=10)
    register("ev_test282", owner._eventcb_first, prio=30)
    assert _names(stub.events["ev_test282"]) == [(30, "_eventcb_first")]


def test_unregister_removes_callback_and_isregistered_is_false(stub: _Stub) -> None:
    owner = _Owner()
    stub.api("plugins.core.events:event.register")("ev_test282", owner._eventcb_first)
    event = stub.events["ev_test282"]
    assert event.isregistered(owner._eventcb_first) is True
    stub.api("plugins.core.events:event.unregister")("ev_test282", owner._eventcb_first)
    assert event.isregistered(owner._eventcb_first) is False
    assert event.count() == 0


def test_unregister_unknown_event_logs_and_does_not_raise(
    stub: _Stub, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR):
        stub.api("plugins.core.events:event.unregister")(
            "ev_test282_missing", _Owner()._eventcb_first
        )
    assert "could not find event ev_test282_missing" in caplog.text
    assert "ev_test282_missing" not in stub.events


def test_event_unregister_unknown_function_returns_false_and_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    event = Event("ev_test282_unknown", created_by="test282")
    event.register(_Owner()._eventcb_first, OWNER_ID)
    with caplog.at_level(logging.ERROR):
        assert event.unregister(_Owner(OTHER_ID).plain) is False
    assert "could not find function plain" in caplog.text
    assert event.count() == 1


def test_event_unregister_known_function_returns_true() -> None:
    event = Event("ev_test282_known", created_by="test282")
    owner = _Owner()
    event.register(owner._eventcb_first, OWNER_ID)
    assert event.unregister(owner._eventcb_first) is True
    assert event.isregistered(owner._eventcb_first) is False
    assert event.isempty() is True


def test_unregister_for_owner_removes_only_that_owner(stub: _Stub) -> None:
    mine, other = _Owner(), _Owner(OTHER_ID)
    register = stub.api("plugins.core.events:event.register")
    register("ev_test282_a", mine._eventcb_first)
    register("ev_test282_b", mine._eventcb_two, prio=5)
    register("ev_test282_a", other._eventcb_first)
    stub.api("plugins.core.events:event.unregister.for.owner")(OWNER_ID)
    assert _names(stub.events["ev_test282_a"]) == [(50, "_eventcb_first")]
    assert stub.events["ev_test282_a"].getownerregistrations(OTHER_ID) != []
    assert stub.events["ev_test282_a"].getownerregistrations(OWNER_ID) == []
    assert stub.events["ev_test282_b"].count() == 0


def test_unregister_for_unknown_owner_does_not_raise(stub: _Stub) -> None:
    stub.api("plugins.core.events:event.register")("ev_test282_a", _Owner()._eventcb_first)
    stub.api("plugins.core.events:event.unregister.for.owner")("plugins.nobody")
    assert stub.events["ev_test282_a"].count() == 1


def test_unregister_for_owner_with_no_events_does_not_raise(stub: _Stub) -> None:
    stub.api("plugins.core.events:event.unregister.for.owner")(OWNER_ID)
    assert stub.events == {}


def test_register_by_func_registers_every_decorator_and_formats_name(stub: _Stub) -> None:
    owner = _Owner()
    EventsPlugin._api_event_register_by_func(stub, owner._eventcb_first)
    EventsPlugin._api_event_register_by_func(stub, owner._eventcb_two)
    assert _names(stub.events[f"ev_{OWNER_ID}_first"]) == [(10, "_eventcb_first")]
    assert _names(stub.events["ev_test282_a"]) == [(50, "_eventcb_two")]
    assert _names(stub.events["ev_test282_b"]) == [(20, "_eventcb_two")]


def test_get_event_registration_functions_finds_only_decorated_eventcbs() -> None:
    found = EventsPlugin.get_event_registration_functions_in_object(
        _Stub(),  # type: ignore[arg-type]
        _Owner(),
    )
    assert sorted(f.__name__ for f in found) == ["_eventcb_first", "_eventcb_two"]


def test_get_event_registration_functions_recurse_flag() -> None:
    holder = _Holder()
    stub = _Stub()
    recursed = EventsPlugin.get_event_registration_functions_in_object(stub, holder)  # type: ignore[arg-type]
    flat = EventsPlugin.get_event_registration_functions_in_object(stub, holder, recurse=False)  # type: ignore[arg-type]
    assert sorted(f.__name__ for f in recursed) == ["_eventcb_first", "_eventcb_two"]
    assert flat == []


def test_register_events_for_plugin_registers_discovered_callbacks(stub: _Stub) -> None:
    stub.instances[OWNER_ID] = _Owner()
    stub._register_events_for_plugin(OWNER_ID)
    assert set(stub.events) == {f"ev_{OWNER_ID}_first", "ev_test282_a", "ev_test282_b"}
    assert stub.events["ev_test282_b"].count() == 1


def test_register_events_for_plugin_warns_on_decorated_method_without_prefix(
    stub: _Stub, caplog: pytest.LogCaptureFixture
) -> None:
    stub.instances[OWNER_ID] = _Owner()
    with caplog.at_level(logging.WARNING):
        stub._register_events_for_plugin(OWNER_ID)
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    for text in (OWNER_ID, "not_prefixed", "ev_test282_c", "_eventcb_"):
        assert text in warnings[0]
    assert "ev_test282_c" not in stub.events


def test_register_events_for_plugin_prefixed_method_registers_without_warning(
    stub: _Stub, caplog: pytest.LogCaptureFixture
) -> None:
    class Prefixed:
        plugin_id = "plugins.test284.prefixed"

        @RegisterToEvent(event_name="ev_test284_ok")
        def _eventcb_ok(self) -> None:
            """Prefixed and decorated."""

    stub.instances[Prefixed.plugin_id] = Prefixed()
    with caplog.at_level(logging.WARNING):
        stub._register_events_for_plugin(Prefixed.plugin_id)
    assert "ev_test284_ok" in stub.events
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []


def test_register_events_for_plugin_without_callbacks_registers_nothing(stub: _Stub) -> None:
    class Bare:
        plugin_id = "plugins.bare"

    stub.instances["plugins.bare"] = Bare()
    stub._register_events_for_plugin("plugins.bare")
    assert stub.events == {}


def test_plugin_unloaded_removes_that_plugins_registrations(stub: _Stub) -> None:
    mine, other = _Owner(), _Owner(OTHER_ID)
    register = stub.api("plugins.core.events:event.register")
    register("ev_test282_a", mine._eventcb_first)
    register("ev_test282_a", other._eventcb_first)
    stub.current_record = {"plugin_id": OWNER_ID}
    EventsPlugin._eventcb_plugin_unloaded(stub)
    event = stub.events["ev_test282_a"]
    assert event.getownerregistrations(OWNER_ID) == []
    assert event.getownerregistrations(OTHER_ID) != []


def test_plugin_unloaded_without_record_does_nothing(stub: _Stub) -> None:
    stub.api("plugins.core.events:event.register")("ev_test282_a", _Owner()._eventcb_first)
    stub.current_record = None
    EventsPlugin._eventcb_plugin_unloaded(stub)
    assert stub.events["ev_test282_a"].count() == 1

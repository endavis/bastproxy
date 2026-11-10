"""Regression tests for #281: a nested raise of the same event keeps the outer raise intact."""

# Standard Library
from collections.abc import Iterator
from typing import Any

# 3rd Party
import pytest

# Project
from bastproxy.libs.api import API
from bastproxy.plugins.core.events.libs.process._raisedevent import ProcessRaisedEvent
from bastproxy.plugins.core.events.plugin._event import Event


@pytest.fixture(autouse=True)
def settings_stub() -> Iterator[None]:
    """Stand in for the settings plugin api the raise path calls."""
    api = API("test281")
    api.add("plugins.core.settings", "setting.get", lambda *_a, **_k: False, description="stand-in")
    try:
        yield
    finally:
        API._class_api.pop("plugins.core.settings:setting.get", None)


def test_nested_raise_does_not_rerun_outer_callbacks() -> None:
    event = Event("ev_test281_repro", created_by="test281")
    calls: list[str] = []
    state: dict[str, Any] = {"nested": False}

    def cb() -> None:
        calls.append("cb")
        if not state["nested"]:
            state["nested"] = True
            event.raise_event({}, "test281")

    def other() -> None:
        calls.append("other")

    event.register(cb, "plugins.test281", prio=40)
    event.register(other, "plugins.test281", prio=50)
    event.raise_event({}, "test281")
    # outer: cb (raises inner: cb, other), then other
    assert calls == ["cb", "cb", "other", "other"]


def test_active_event_and_current_callback_restored_after_nested_raise() -> None:
    event = Event("ev_test281_state", created_by="test281")
    seen: dict[str, Any] = {}
    state: dict[str, Any] = {"nested": False}

    def cb() -> None:
        if state["nested"]:
            seen["inner_active"] = event.get_active_event()
            return
        state["nested"] = True
        seen["outer_active"] = event.get_active_event()
        seen["outer_callback"] = event.current_callback
        event.raise_event({}, "test281")
        seen["active_after"] = event.get_active_event()
        seen["callback_after"] = event.current_callback

    event.register(cb, "plugins.test281", prio=50)
    event.raise_event({}, "test281")
    assert isinstance(seen["outer_active"], ProcessRaisedEvent)
    assert seen["inner_active"] is not seen["outer_active"]
    assert seen["active_after"] is seen["outer_active"]
    assert seen["outer_callback"] is not None
    assert seen["callback_after"] is seen["outer_callback"]


def test_inner_raise_runs_all_its_callbacks() -> None:
    event = Event("ev_test281_inner", created_by="test281")
    inner_calls: list[str] = []
    state: dict[str, Any] = {"depth": 0}

    def first() -> None:
        state["depth"] += 1
        if state["depth"] == 1:
            event.raise_event({}, "test281")
        else:
            inner_calls.append("first")

    def second() -> None:
        if state["depth"] > 1:
            inner_calls.append("second")

    def third() -> None:
        if state["depth"] > 1:
            inner_calls.append("third")

    event.register(first, "plugins.test281", prio=10)
    event.register(second, "plugins.test281", prio=20)
    event.register(third, "plugins.test281", prio=30)
    event.raise_event({}, "test281")
    # inner raise: first, second, third; the outer raise then still runs its own second, third
    assert inner_calls == ["first", "second", "third", "second", "third"]


def test_nested_raise_with_data_list() -> None:
    event = Event("ev_test281_list", created_by="test281")
    seen: list[tuple[str, str]] = []
    state: dict[str, Any] = {"nested": False}

    def current() -> str:
        active = event.get_active_event()
        assert active is not None
        return str(active.event_data["line"])

    def first() -> None:
        seen.append(("first", current()))
        if not state["nested"]:
            state["nested"] = True
            event.raise_event({}, "test281", data_list=["x", "y"], key_name="line")

    def second() -> None:
        seen.append(("second", current()))

    event.register(first, "plugins.test281", prio=40)
    event.register(second, "plugins.test281", prio=50)
    event.raise_event({}, "test281", data_list=["a", "b"], key_name="line")
    assert seen == [
        ("first", "a"),
        ("first", "x"),
        ("second", "x"),
        ("first", "y"),
        ("second", "y"),
        ("second", "a"),
        ("first", "b"),
        ("second", "b"),
    ]


def test_everything_clean_after_outer_raise() -> None:
    event = Event("ev_test281_clean", created_by="test281")
    state: dict[str, Any] = {"nested": False}

    def cb() -> None:
        if not state["nested"]:
            state["nested"] = True
            event.raise_event({}, "test281")

    event.register(cb, "plugins.test281", prio=50)
    event.raise_event({}, "test281")
    assert event.get_active_event() is None
    assert event.current_callback is None

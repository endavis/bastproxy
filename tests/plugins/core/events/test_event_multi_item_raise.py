"""Regression tests for #252: every item of a data_list raise runs every callback."""

# Standard Library
from collections.abc import Iterator

# 3rd Party
import pytest

# Project
from bastproxy.libs.api import API
from bastproxy.plugins.core.events.plugin._event import Event


@pytest.fixture(autouse=True)
def settings_stub() -> Iterator[None]:
    """Stand in for the settings plugin api the raise path calls."""
    api = API("test252")
    api.add("plugins.core.settings", "setting.get", lambda *_a, **_k: False, description="stand-in")
    try:
        yield
    finally:
        API._class_api.pop("plugins.core.settings:setting.get", None)


def _raise(event: Event, items: list[str]) -> None:
    event.raise_event({}, "test252", data_list=items, key_name="line")


def test_single_callback_runs_for_every_item() -> None:
    event = Event("ev_test252_one", created_by="test252")
    seen: list[str] = []

    def cb() -> None:
        seen.append(event.raised_events[next(reversed(event.raised_events))].event_data["line"])

    event.register(cb, "plugins.test252", prio=50)
    _raise(event, ["a", "b", "c"])
    assert seen == ["a", "b", "c"]
    assert event.current_callback is None


def test_two_callbacks_run_once_per_item_in_priority_order() -> None:
    event = Event("ev_test252_two", created_by="test252")
    seen: list[tuple[str, str]] = []

    def current() -> str:
        return str(event.raised_events[next(reversed(event.raised_events))].event_data["line"])

    def first() -> None:
        seen.append(("first", current()))

    def second() -> None:
        seen.append(("second", current()))

    event.register(second, "plugins.test252", prio=60)
    event.register(first, "plugins.test252", prio=40)
    _raise(event, ["a", "b", "c"])
    assert seen == [
        ("first", "a"),
        ("second", "a"),
        ("first", "b"),
        ("second", "b"),
        ("first", "c"),
        ("second", "c"),
    ]
    assert event.current_callback is None

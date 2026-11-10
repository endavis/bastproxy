"""Regression tests for #280: priority 0 is honoured, not coerced to 50."""

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
    api = API("test280")
    api.add("plugins.core.settings", "setting.get", lambda *_a, **_k: False, description="stand-in")
    try:
        yield
    finally:
        API._class_api.pop("plugins.core.settings:setting.get", None)


def _noop() -> None:
    return None


def _other() -> None:
    return None


def test_prio_zero_is_stored_at_zero() -> None:
    event = Event("ev_test280_store", created_by="test280")
    event.register(_noop, "plugins.test280", prio=0)
    event.register(_other, "plugins.test280", prio=99)
    assert sorted(event.priority_dictionary) == [0, 99]


def test_priorities_run_lowest_first_including_zero() -> None:
    event = Event("ev_test280_order", created_by="test280")
    order: list[str] = []

    def p99() -> None:
        order.append("p99")

    def p50() -> None:
        order.append("p50")

    def p1() -> None:
        order.append("p1")

    def p0() -> None:
        order.append("p0")

    event.register(p99, "plugins.test280", prio=99)
    event.register(p50, "plugins.test280", prio=50)
    event.register(p1, "plugins.test280", prio=1)
    event.register(p0, "plugins.test280", prio=0)
    event.raise_event({"a": 1}, "test280")
    assert order == ["p0", "p1", "p50", "p99"]


def test_prio_none_is_stored_at_50() -> None:
    event = Event("ev_test280_none", created_by="test280")
    event.register(_noop, "plugins.test280", prio=None)
    assert list(event.priority_dictionary) == [50]


def test_default_prio_is_stored_at_50() -> None:
    event = Event("ev_test280_default", created_by="test280")
    event.register(_noop, "plugins.test280")
    assert list(event.priority_dictionary) == [50]

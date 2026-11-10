"""Regression tests for #275: a callback registered mid-raise at an already-visited priority runs."""

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
    api = API("test275")
    api.add("plugins.core.settings", "setting.get", lambda *_a, **_k: False, description="stand-in")
    try:
        yield
    finally:
        API._class_api.pop("plugins.core.settings:setting.get", None)


def test_chain_of_late_registrations_all_run_in_the_same_raise() -> None:
    event = Event("ev_test275_chain", created_by="test275")
    order: list[str] = []

    def cb5() -> None:
        order.append("cb5")

    def cb10() -> None:
        order.append("cb10")
        event.register(cb5, "plugins.test275", prio=5)

    def cb50() -> None:
        order.append("cb50")
        event.register(cb10, "plugins.test275", prio=10)

    def cb99() -> None:
        order.append("cb99")

    event.register(cb50, "plugins.test275", prio=50)
    event.register(cb99, "plugins.test275", prio=99)
    event.raise_event({"a": 1}, "test275")
    assert order == ["cb50", "cb99", "cb10", "cb5"]

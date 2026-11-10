"""Regression tests for #279: registering the same callback twice must not duplicate it."""

# Standard Library
from collections.abc import Callable
from typing import Any

# Project
from bastproxy.plugins._baseplugin import BasePlugin
from bastproxy.plugins.core.events.plugin._event import Event


def _cb() -> None:
    """Callback used for registration."""


def _other_cb() -> None:
    """A different callback."""


def test_register_twice_same_owner_is_rejected() -> None:
    event = Event("ev_test279_dup", created_by="test279")
    assert event.register(_cb, "plugins.test279") is True
    assert event.register(_cb, "plugins.test279") is False
    assert event.count() == 1


def test_register_same_func_different_owner_is_distinct() -> None:
    event = Event("ev_test279_owner", created_by="test279")
    assert event.register(_cb, "plugins.a") is True
    assert event.register(_cb, "plugins.b") is True
    assert event.count() == 2


def test_register_same_func_different_priority_is_distinct() -> None:
    event = Event("ev_test279_prio", created_by="test279")
    assert event.register(_cb, "plugins.a", prio=10) is True
    assert event.register(_cb, "plugins.a", prio=20) is True
    assert event.count() == 2


def test_isregistered() -> None:
    event = Event("ev_test279_isreg", created_by="test279")
    assert event.isregistered(_cb) is False
    event.register(_cb, "plugins.test279")
    assert event.isregistered(_cb) is True
    assert event.isregistered(_other_cb) is False


def test_baseplugin_disconnect_does_not_grow_registrations() -> None:
    event = Event("ev_libs.api_character_active", created_by="test279")

    def register(_event_name: str, func: Callable[..., Any]) -> None:
        # mirrors the events plugin's event.register api
        if event.isregistered(func):
            event.unregister(func)
        event.register(func, "plugins.test279")

    class FakePlugin:
        plugin_id = "plugins.test279"

        def api(self, name: str) -> Callable[..., Any]:
            assert name == "plugins.core.events:event.register"
            return register

        _eventcb_baseplugin_after_character_is_active = (
            BasePlugin._eventcb_baseplugin_after_character_is_active
        )

    fake: Any = FakePlugin()
    for _ in range(3):
        BasePlugin._eventcb_baseplugin_disconnect(fake)
    assert event.count() == 1

"""Tests for BasePlugin plugin.stats.get and its event declarations (#466)."""

import logging
from collections.abc import Callable, Iterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs.api import API
from bastproxy.plugins._baseplugin import BasePlugin
from bastproxy.plugins.core.events.plugin import _event
from bastproxy.plugins.core.events.plugin._event import Event
from bastproxy.plugins.core.timers.plugin._timers import TimersPlugin

RAISE_API = "plugins.core.events:event.raise"
PID = "plugins.test.stub"


@pytest.fixture(autouse=True)
def settings_stub() -> Iterator[None]:
    """Stand in for the settings plugin api the raise path calls."""
    api = API("test466")
    api.add("plugins.core.settings", "setting.get", lambda *_a, **_k: False, description="stand-in")
    try:
        yield
    finally:
        API._class_api.pop("plugins.core.settings:setting.get", None)


class _Stub(BasePlugin):
    """A BasePlugin that skips __init__."""

    def __init__(self, apis: dict[str, Callable[..., Any]], plugin_id: str = PID) -> None:
        self.plugin_id = plugin_id
        self.api = MagicMock(side_effect=lambda name: apis.get(name, MagicMock()))


class _Bus:
    """A fake event.raise that runs per-event callbacks on a record."""

    def __init__(self) -> None:
        self.callbacks: dict[str, list[Callable[[dict[str, Any]], None]]] = {}
        self.raised: list[tuple[str, set[str]]] = []

    def raise_event(self, name: str, event_args: dict[str, Any]) -> SimpleNamespace:
        self.raised.append((name, set(event_args)))
        record = dict(event_args)
        for callback in self.callbacks.get(name, []):
            callback(record)
        return SimpleNamespace(event_data=record)


def test_stats_get_raises_both_events_and_returns_sections() -> None:
    bus = _Bus()
    bus.callbacks[f"ev_{PID}_stats"] = [
        lambda rec: rec["stats"].__setitem__("Own", {"showorder": ["A"], "A": 1})
    ]
    bus.callbacks["ev_plugin_stats"] = [
        lambda rec: rec["stats"].__setitem__("Other", {"showorder": ["B"], "B": 2})
    ]
    stub: Any = _Stub({RAISE_API: bus.raise_event})

    stats = stub._api_plugin_stats_get()

    assert bus.raised == [
        (f"ev_{PID}_stats", {"plugin_id", "stats"}),
        ("ev_plugin_stats", {"plugin_id", "stats"}),
    ]
    assert set(stats) == {"Own", "Other"}


def test_stats_get_without_event_results_returns_empty() -> None:
    stub: Any = _Stub({RAISE_API: lambda *_a, **_k: None})
    assert stub._api_plugin_stats_get() == {}


def test_base_initialize_declares_stats_event() -> None:
    declared: dict[str, dict[str, Any]] = {}

    def event_add(name: str, _owner: str, **kwargs: Any) -> None:
        declared[name] = kwargs["arg_descriptions"]

    stub: Any = _Stub({"plugins.core.events:event.add": event_add})
    stub._phook_base_initialize()

    assert set(declared[f"ev_{PID}_stats"]) == {"plugin_id", "stats"}


def _timers_stub(plugin_id: str) -> MagicMock:
    stub = MagicMock()
    stub.plugin_id = plugin_id
    stub.timer_lookup = {
        "t1": SimpleNamespace(name="t1", owner_id="plugins.test.owner", enabled=True),
        "t2": SimpleNamespace(name="t2", owner_id="plugins.test.other", enabled=False),
    }
    stub.timer_events = {1: ["t1"]}
    stub.overall_fire_count = 3
    return stub


def test_timers_readers_feed_stats_get() -> None:
    bus = _Bus()
    holder: dict[str, Any] = {}
    timers = _timers_stub("plugins.core.timers")
    timers.api = lambda name: (
        (lambda: holder["record"])
        if name == "plugins.core.events:event.current.record.get"
        else MagicMock()
    )

    def with_record(method: Callable[..., Any]) -> Callable[[dict[str, Any]], None]:
        def run(record: dict[str, Any]) -> None:
            holder["record"] = record
            method(timers)

        return run

    bus.callbacks["ev_plugins.core.timers_stats"] = [
        with_record(TimersPlugin._eventcb_timers_ev_plugins_stats)
    ]
    bus.callbacks["ev_plugin_stats"] = [
        with_record(TimersPlugin._eventcb_event_get_stats_for_plugin)
    ]

    timers_stats = _Stub(
        {RAISE_API: bus.raise_event}, "plugins.core.timers"
    )._api_plugin_stats_get()
    assert "Overall Timer Stats" in timers_stats
    assert "plugins.core.timers Timer Stats" not in timers_stats

    owner_stats = _Stub({RAISE_API: bus.raise_event}, "plugins.test.owner")._api_plugin_stats_get()
    assert "plugins.test.owner Timer Stats" in owner_stats
    assert "Overall Timer Stats" not in owner_stats


def test_stats_raises_do_not_trigger_undeclared_key_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []
    monkeypatch.setattr(_event, "log_to", lambda _s, level, *_a, **_k: calls.append(level))
    declared = {"plugin_id": "The plugin id", "stats": "sections"}
    events = {
        name: Event(name, created_by=PID, arg_descriptions=declared)
        for name in (f"ev_{PID}_stats", "ev_plugin_stats")
    }

    def raise_event(name: str, event_args: dict[str, Any]) -> Any:
        return events[name].raise_event(event_args, PID)

    stub: Any = _Stub({RAISE_API: raise_event})
    stub._api_plugin_stats_get()

    assert logging.WARNING not in calls

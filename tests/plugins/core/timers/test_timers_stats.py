"""Tests for the timers plugin's stats sections and their TypedDicts (#419)."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins.core.timers.plugin._timers import (
    OverallTimerStats,
    PluginTimerStats,
    TimersPlugin,
)

PID = "plugins.test.a"


def _stub(record: dict[str, Any] | None) -> MagicMock:
    """Build a stub timers plugin whose current event record is ``record``."""
    stub = MagicMock()
    stub.timer_lookup = {
        "t1": SimpleNamespace(name="t1", owner_id=PID, enabled=True),
        "t2": SimpleNamespace(name="t2", owner_id="plugins.test.b", enabled=False),
        "t3": SimpleNamespace(name="t3", owner_id=PID, enabled=True),
    }
    stub.timer_events = {1: ["t1"]}
    stub.overall_fire_count = 7

    def api(name: str) -> Any:
        if name == "plugins.core.events:event.current.record.get":
            return lambda: record
        return MagicMock()

    stub.api = api
    return stub


def test_overall_stats_counts_timers() -> None:
    record: dict[str, Any] = {"stats": {}}

    TimersPlugin._eventcb_timers_ev_plugins_stats(_stub(record))

    stats = record["stats"]["Overall Timer Stats"]
    assert stats["Total"] == 3
    assert stats["Enabled"] == 2
    assert stats["Disabled"] == 1
    assert stats["Fired"] == 7
    assert stats["Memory Usage"] > 0
    assert stats["showorder"] == ["Total", "Enabled", "Disabled", "Fired", "Memory Usage"]


def test_overall_stats_keys_match_typeddict() -> None:
    record: dict[str, Any] = {"stats": {}}

    TimersPlugin._eventcb_timers_ev_plugins_stats(_stub(record))

    assert set(record["stats"]["Overall Timer Stats"]) == set(OverallTimerStats.__required_keys__)


def test_overall_stats_without_record_does_nothing() -> None:
    TimersPlugin._eventcb_timers_ev_plugins_stats(_stub(None))


def test_plugin_stats_lists_owned_timers() -> None:
    record: dict[str, Any] = {"stats": {}, "plugin_id": PID}

    TimersPlugin._eventcb_event_get_stats_for_plugin(_stub(record))

    stats = record["stats"][f"{PID} Timer Stats"]
    assert stats["Total Timers Owned"] == 2
    assert stats["Timers Owned"].split() == ["t1", "t3"]
    assert stats["showorder"] == ["Total Timers Owned", "Timers Owned"]
    assert set(stats) == set(PluginTimerStats.__required_keys__)


def test_plugin_stats_skips_plugin_without_timers() -> None:
    record: dict[str, Any] = {"stats": {}, "plugin_id": "plugins.test.none"}

    TimersPlugin._eventcb_event_get_stats_for_plugin(_stub(record))

    assert record["stats"] == {}

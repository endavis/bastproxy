"""Tests for timer scheduling from the previous due time and last fire tracking (#629)."""

import datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.plugins.core.timers.plugin._timers import Timer, TimersPlugin

BASE = datetime.datetime(2030, 1, 1, 12, 0, 0, tzinfo=datetime.UTC)
MODULE_DT = "bastproxy.plugins.core.timers.plugin._timers.datetime.datetime"


def _freeze(monkeypatch: pytest.MonkeyPatch, now: datetime.datetime) -> None:
    class _FakeDatetime(datetime.datetime):
        @classmethod
        def now(cls, tz: Any = None) -> Any:
            return now

    monkeypatch.setattr(MODULE_DT, _FakeDatetime)


def _timer(monkeypatch: pytest.MonkeyPatch, **kwargs: Any) -> Timer:
    _freeze(monkeypatch, BASE)
    return Timer("t", lambda: None, kwargs.pop("seconds", 10), "plugins.test.a", **kwargs)


def test_interval_next_fire_is_previous_due_plus_seconds_without_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timer = _timer(monkeypatch)
    assert timer.next_fire_datetime == BASE + datetime.timedelta(seconds=10)
    late = BASE + datetime.timedelta(seconds=13)  # execute ran 3 seconds late
    assert timer.get_next_fire(late) == BASE + datetime.timedelta(seconds=20)


def test_missed_fires_are_skipped_past_now(monkeypatch: pytest.MonkeyPatch) -> None:
    timer = _timer(monkeypatch)
    now = BASE + datetime.timedelta(seconds=47)
    assert timer.get_next_fire(now) == BASE + datetime.timedelta(seconds=50)
    # exactly on a slot still moves strictly past now
    assert timer.get_next_fire(BASE + datetime.timedelta(seconds=50)) == BASE + datetime.timedelta(
        seconds=60
    )


def test_time_timer_fires_same_time_next_day(monkeypatch: pytest.MonkeyPatch) -> None:
    timer = _timer(monkeypatch, time="0300", seconds=60)
    assert timer.next_fire_datetime == datetime.datetime(2030, 1, 2, 3, 0, tzinfo=datetime.UTC)
    fired_at = datetime.datetime(2030, 1, 2, 3, 0, 2, tzinfo=datetime.UTC)
    assert timer.get_next_fire(fired_at) == datetime.datetime(2030, 1, 3, 3, 0, tzinfo=datetime.UTC)


def _stub() -> Any:
    stub = MagicMock()
    stub.plugin_id = "plugins.core.timers"
    stub.timer_events = {}
    stub.timer_lookup = {}
    stub.overall_fire_count = 0
    stub._add_timer_internal = lambda t: TimersPlugin._add_timer_internal(stub, t)
    return stub


def _fire(monkeypatch: pytest.MonkeyPatch, timer: Timer, now: datetime.datetime) -> Any:
    stub = _stub()
    stub._add_timer_internal(timer)
    slot = int(timer.next_fire_datetime.timestamp())
    _freeze(monkeypatch, now)
    TimersPlugin.execute_timer(stub, slot, timer)
    return stub


def test_fire_records_last_fired_and_reschedules_from_due(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timer = _timer(monkeypatch)
    due = timer.next_fire_datetime
    now = due + datetime.timedelta(seconds=3)
    stub = _fire(monkeypatch, timer, now)
    assert timer.last_fired_datetime == now
    assert timer.next_fire_datetime == due + datetime.timedelta(seconds=10)
    assert int(timer.next_fire_datetime.timestamp()) in stub.timer_events


def test_disabled_timer_reschedules_without_recording_last_fire(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timer = _timer(monkeypatch, enabled=False)
    due = timer.next_fire_datetime
    _fire(monkeypatch, timer, due + datetime.timedelta(seconds=1))
    assert timer.last_fired_datetime is None
    assert timer.next_fire_datetime == due + datetime.timedelta(seconds=10)


def test_detail_shows_last_fire(monkeypatch: pytest.MonkeyPatch) -> None:
    timer = _timer(monkeypatch)
    now = timer.next_fire_datetime + datetime.timedelta(seconds=1)
    _fire(monkeypatch, timer, now)
    stub = MagicMock()
    stub.timer_lookup = {"t": timer}
    stub.api = lambda _n: lambda: {"timers": ["t"]}
    result = TimersPlugin._command_detail(stub)
    assert any(line.startswith("Last Fire") for line in result.message)

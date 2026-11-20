"""Tests for timers that remove themselves while firing, and task survival (#627)."""

import asyncio
import datetime
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.plugins.core.timers.plugin._timers import TimersPlugin

FIRE = datetime.datetime(2030, 1, 1, tzinfo=datetime.UTC)
SLOT = int(FIRE.timestamp())


def _timer(name: str, onetime: bool, func: Callable[[Any], None] | None = None) -> Any:
    timer = SimpleNamespace(
        name=name,
        owner_id="plugins.test.a",
        enabled=True,
        onetime=onetime,
        log=False,
        next_fire_datetime=FIRE,
    )
    timer.get_next_fire = lambda: FIRE + datetime.timedelta(seconds=5)
    timer.execute = (lambda: func(timer)) if func else (lambda: None)
    return timer


def _stub() -> Any:
    stub = MagicMock()
    stub.plugin_id = "plugins.core.timers"
    stub.timer_events = {}
    stub.timer_lookup = {}
    stub.overall_fire_count = 0
    stub._add_timer_internal = lambda t: TimersPlugin._add_timer_internal(stub, t)
    stub._remove_timer_internal = lambda t: TimersPlugin._remove_timer_internal(stub, t)
    stub.execute_timer = lambda t, tm: TimersPlugin.execute_timer(stub, t, tm)
    stub.api = lambda _name: (
        lambda timer_name: stub._remove_timer_internal(stub.timer_lookup[timer_name])
    )
    return stub


def _remove_self(stub: Any) -> Callable[[Any], None]:
    return lambda timer: stub.api("timer.remove")(timer.name)


@pytest.mark.parametrize("onetime", [False, True])
def test_timer_removing_itself_stays_removed(onetime: bool) -> None:
    stub = _stub()
    timer = _timer("t", onetime)
    timer.execute = lambda: _remove_self(stub)(timer)
    stub._add_timer_internal(timer)

    TimersPlugin.execute_timer(stub, SLOT, timer)

    assert "t" not in stub.timer_lookup
    assert stub.timer_events == {}


def test_repeating_timer_still_reschedules() -> None:
    stub = _stub()
    timer = _timer("t", False)
    stub._add_timer_internal(timer)

    TimersPlugin.execute_timer(stub, SLOT, timer)

    assert stub.timer_lookup["t"] is timer
    assert SLOT + 5 in stub.timer_events


class _StopLoopError(Exception):
    pass


def test_check_for_timers_survives_an_error_in_one_timer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub = _stub()
    bad = _timer("bad", True)
    good = _timer("good", True)
    stub._add_timer_internal(bad)
    stub._add_timer_internal(good)
    fired: list[str] = []
    good.execute = lambda: fired.append("good")
    real = stub.execute_timer

    def execute(slot: int, timer: Any) -> None:
        if timer is bad:
            raise RuntimeError("boom")
        real(slot, timer)

    stub.execute_timer = execute
    stub.time_last_checked = FIRE - datetime.timedelta(seconds=1)

    class _FakeDatetime(datetime.datetime):
        @classmethod
        def now(cls, tz: Any = None) -> Any:
            return FIRE

    monkeypatch.setattr(
        "bastproxy.plugins.core.timers.plugin._timers.datetime.datetime", _FakeDatetime
    )

    async def stop(_delay: float) -> None:
        raise _StopLoopError

    monkeypatch.setattr(asyncio, "sleep", stop)

    with pytest.raises(_StopLoopError):
        asyncio.run(TimersPlugin.check_for_timers_to_fire(stub))

    assert fired == ["good"]

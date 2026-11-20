"""Tests for ``timer.add`` interval validation (#630)."""

import math
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.plugins.core.timers.plugin._timers import Timer, TimersPlugin

PID = "plugins.test.a"


def _stub() -> MagicMock:
    stub = MagicMock()
    stub.plugin_id = "plugins.core.timers"
    stub.timer_lookup = {}

    def api(name: str) -> Any:
        if name == "libs.api:caller.owner.get":
            return lambda **_kw: PID
        if name == "libs.plugins.loader:plugin.id.is.valid":
            return lambda _plugin_id: True
        return MagicMock()

    stub.api = api
    return stub


@pytest.mark.parametrize("bad", [None, "5", True, False, 0, 0.5, -1, math.nan, math.inf, -math.inf])
def test_add_refuses_invalid_interval(bad: Any) -> None:
    stub = _stub()

    result = TimersPlugin._api_timer_add(stub, "t", lambda: None, bad)

    assert result is None
    assert "t" not in stub.timer_lookup
    stub._add_timer_internal.assert_not_called()


@pytest.mark.parametrize("good", [1, 2.5, 5.0])
def test_add_accepts_valid_interval(good: float) -> None:
    stub = _stub()

    timer = TimersPlugin._api_timer_add(stub, "t", lambda: None, good)

    assert timer is not None
    assert timer.seconds == good
    assert "t" in str(timer)
    stub._add_timer_internal.assert_called_once_with(timer)


@pytest.mark.parametrize("seconds", [60, 5.0, 2.5])
def test_timer_str_works_for_int_and_float(seconds: float) -> None:
    timer = Timer("f", lambda: None, seconds, "plugins.x")

    assert "Timer f" in str(timer)

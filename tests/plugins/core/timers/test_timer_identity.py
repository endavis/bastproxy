"""Regression tests for #279: timers stay distinct even with the same func, owner and name."""

# Project
from bastproxy.plugins.core.timers.plugin._timers import Timer


def _func() -> None:
    """Timer function."""


def _make() -> Timer:
    return Timer("same", _func, 60, "plugins.test279")


def test_timers_with_same_func_owner_name_are_distinct() -> None:
    t1, t2 = _make(), _make()
    assert t1 != t2
    assert t1 == t1
    assert hash(t1) != hash(t2)


def test_list_remove_removes_only_one_timer() -> None:
    t1, t2 = _make(), _make()
    timers = [t1, t2]
    assert t2 in timers
    timers.remove(t1)
    assert timers == [t2]
    assert timers[0] is t2


def test_timer_still_equals_plain_function() -> None:
    assert _make() == _func

"""Tests for PromptQueue (#544)."""

# Project
from bastproxy.plugins.core.triggers.plugin._prompt import PROMPT_MAX_WAIT, PromptQueue


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_empty_queue_is_falsy() -> None:
    queue = PromptQueue()
    assert not queue
    assert len(queue) == 0


def test_take_all_returns_arrival_order_and_empties() -> None:
    queue = PromptQueue()
    queue.add("a", {"n": 1})
    queue.add("b", {"n": 2})
    assert queue
    assert len(queue) == 2
    assert queue.take_all() == [("a", {"n": 1}), ("b", {"n": 2})]
    assert not queue
    assert queue.take_all() == []


def test_take_expired_keeps_fresh_entries() -> None:
    clock = Clock()
    queue = PromptQueue(clock=clock)
    queue.add("old", {})
    clock.now += PROMPT_MAX_WAIT - 0.5
    queue.add("new", {})
    assert queue.take_expired() == []
    clock.now += 0.5
    assert queue.take_expired() == [("old", {})]
    assert len(queue) == 1
    clock.now += PROMPT_MAX_WAIT
    assert queue.take_expired() == [("new", {})]
    assert not queue


def test_custom_max_wait() -> None:
    clock = Clock()
    queue = PromptQueue(max_wait=0.5, clock=clock)
    queue.add("x", {})
    clock.now += 0.5
    assert queue.take_expired() == [("x", {})]


def test_clear_drops_everything() -> None:
    queue = PromptQueue()
    queue.add("a", {})
    queue.clear()
    assert not queue

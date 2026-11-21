"""Tests for SimpleQueue.get_last_x edge cases (#679)."""

from bastproxy.libs.queue import SimpleQueue as Queue


def _filled() -> Queue:
    q: Queue = Queue()
    for item in ("a", "b", "c"):
        q.enqueue(item)
    return q


def test_zero_returns_empty() -> None:
    assert _filled().get_last_x(0) == []


def test_oversize_returns_all() -> None:
    assert _filled().get_last_x(10) == ["a", "b", "c"]


def test_exact_size_returns_all() -> None:
    assert _filled().get_last_x(3) == ["a", "b", "c"]


def test_empty_queue() -> None:
    q: Queue = Queue()
    assert q.get_last_x(0) == []
    assert q.get_last_x(5) == []

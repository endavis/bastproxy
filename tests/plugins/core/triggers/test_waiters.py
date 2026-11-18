"""Unit tests for the line waiters (#548)."""

# Standard Library
import asyncio
import logging
from typing import Any

# Third Party
import pytest

# Project
from bastproxy.plugins.core.triggers.plugin import _waiters
from bastproxy.plugins.core.triggers.plugin._waiters import LineWaiter, WaiterRegistry


@pytest.fixture
def logged(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    calls: list[tuple[Any, ...]] = []
    monkeypatch.setattr(_waiters, "log_to", lambda *a, **k: calls.append(a))
    return calls


class Sender:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []
        self.registry: WaiterRegistry | None = None
        self.open_when_sent: int | None = None

    def __call__(self, command: str, owner_id: str) -> None:
        self.sent.append((command, owner_id))
        if self.registry is not None:
            self.open_when_sent = len(self.registry)


@pytest.fixture
def sender() -> Sender:
    s = Sender()
    return s


@pytest.fixture
def registry(sender: Sender) -> WaiterRegistry:
    reg = WaiterRegistry(sender)
    sender.registry = reg
    return reg


def errors(calls: list[tuple[Any, ...]]) -> list[tuple[Any, ...]]:
    return [c for c in calls if c[1] == logging.ERROR]


async def test_match(registry: WaiterRegistry) -> None:
    w = registry.add("o")
    task = asyncio.create_task(w.wait_for(r"^Level: (?P<level>\d+)", 1))
    await asyncio.sleep(0)
    registry.feed("junk", False)
    registry.feed("Level: 12", False)
    result = await task
    assert result is not None
    assert result.text == "Level: 12"
    assert result.matches == {"level": "12"}
    assert result.match is not None


async def test_match_consumes_up_to_match_and_prompt_follows(registry: WaiterRegistry) -> None:
    w = registry.add("o")
    registry.feed("a", False)
    registry.feed("hit", False)
    registry.feed("HP>", True)
    first = await w.wait_for("hit", 0.05)
    assert first is not None
    prompt = await w.wait_for_prompt(0.05)
    assert prompt is not None
    assert prompt.text == "HP>"
    assert prompt.match is None
    assert prompt.matches == {}


async def test_queued_line_found(registry: WaiterRegistry) -> None:
    w = registry.add("o")
    registry.feed("early", False)
    assert (await w.wait_for("early", 0.05)) is not None


async def test_timeout_clears_pending_and_once_leaves_registry_empty(
    registry: WaiterRegistry,
) -> None:
    result = await registry.once("o", lambda w: w.wait_for("never", 0.01))
    assert result is None
    assert len(registry) == 0


async def test_pending_cleared_after_timeout(registry: WaiterRegistry) -> None:
    w = registry.add("o")
    assert await w.wait_for("never", 0.01) is None
    assert w._pending is None


async def test_cancellation(registry: WaiterRegistry) -> None:
    task = asyncio.create_task(registry.once("o", lambda w: w.wait_for("never", 5)))
    await asyncio.sleep(0.01)
    assert len(registry) == 1
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(registry) == 0


async def test_concurrent_waiters(registry: WaiterRegistry) -> None:
    a = registry.add("a")
    b = registry.add("b")
    c = registry.add("c")
    ta = asyncio.create_task(a.wait_for("x", 1))
    tb = asyncio.create_task(b.wait_for("x", 1))
    tc = asyncio.create_task(c.wait_for("y", 0.05))
    await asyncio.sleep(0)
    registry.feed("x", False)
    assert (await ta) is not None
    assert (await tb) is not None
    assert (await tc) is None


async def test_wait_for_prompt_ignores_non_prompt(registry: WaiterRegistry) -> None:
    w = registry.add("o")
    task = asyncio.create_task(w.wait_for_prompt(1))
    await asyncio.sleep(0)
    registry.feed("text", False)
    registry.feed("P>", True)
    result = await task
    assert result is not None
    assert result.is_prompt


async def test_send_and_wait(registry: WaiterRegistry, sender: Sender) -> None:
    w = registry.add("o")
    registry.remove(w)  # prove send registers nothing itself; re-add below
    w = registry.add("o")
    task = asyncio.create_task(w.send_and_wait("score", "ok", 1))
    await asyncio.sleep(0)
    assert sender.sent == [("score", "o")]
    assert sender.open_when_sent == 1
    registry.feed("ok", False)
    assert (await task) is not None


async def test_close_while_waiting(registry: WaiterRegistry, logged: list[tuple[Any, ...]]) -> None:
    w = registry.add("o")
    task = asyncio.create_task(w.wait_for("x", 5))
    await asyncio.sleep(0)
    w.close()
    w.close()
    assert (await task) is None
    assert await w.wait_for("x", 0.01) is None
    assert errors(logged)
    assert len(registry) == 0


async def test_second_wait_returns_none(
    registry: WaiterRegistry, logged: list[tuple[Any, ...]]
) -> None:
    w = registry.add("o")
    first = asyncio.create_task(w.wait_for("x", 1))
    await asyncio.sleep(0)
    assert await w.wait_for("y", 0.01) is None
    assert errors(logged)
    registry.feed("x", False)
    assert (await first) is not None


async def test_invalid_regex_and_timeout(
    registry: WaiterRegistry, logged: list[tuple[Any, ...]]
) -> None:
    w = registry.add("o")
    assert await w.wait_for("(", 0.01) is None
    assert await w.wait_for("x", 0) is None
    assert await w.wait_for_prompt(-1) is None
    assert len(errors(logged)) == 3
    assert w._pending is None


def test_queue_bound(registry: WaiterRegistry) -> None:
    w = registry.add("o", max_lines=3)
    for i in range(5):
        registry.feed(str(i), False)
    assert [s.text for s in w._queue] == ["2", "3", "4"]


def test_close_for_owner(registry: WaiterRegistry) -> None:
    a1 = registry.add("a")
    a2 = registry.add("a")
    b = registry.add("b")
    assert registry.close_for_owner("a") == 2
    assert a1.closed and a2.closed and not b.closed
    assert len(registry) == 1


def test_raising_waiter_logged(
    registry: WaiterRegistry, logged: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch
) -> None:
    bad = registry.add("bad")
    good = registry.add("good")

    def boom(*_a: Any) -> None:
        raise RuntimeError("x")

    monkeypatch.setattr(bad, "feed", boom)
    registry.feed("line", False)
    assert errors(logged)
    assert [s.text for s in good._queue] == ["line"]


def test_context_manager(registry: WaiterRegistry) -> None:
    with registry.add("o") as w:
        assert isinstance(w, LineWaiter)
        assert len(registry) == 1
    assert len(registry) == 0

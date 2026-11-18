"""Plugin-level tests for the waiter APIs and callbacks (#548)."""

# Standard Library
import asyncio
from typing import Any

# Project
from bastproxy.plugins.core.triggers.plugin import _triggers

from .conftest import OWNER, Harness


def make_recorder(monkeypatch: Any) -> list[str]:
    sent: list[str] = []

    class Recorder:
        def __init__(self, data: Any) -> None:
            self.data = data

        def __call__(self) -> None:
            sent.append(str(self.data[0]))

    monkeypatch.setattr(_triggers, "SendDataDirectlyToMud", Recorder)
    return sent


def feed_waiters(h: Harness, text: str, *, internal: bool = False, prompt: bool = False) -> None:
    from bastproxy.libs.records.enums import Originated
    from bastproxy.libs.records.rtypes.networkdata import NetworkDataLine

    h.line = NetworkDataLine(text, originated=Originated.INTERNAL if internal else Originated.MUD)
    h.line.is_prompt = prompt
    h.current_record = {"line": h.line}
    h._eventcb_feed_waiters()


async def test_feed_mud_lines_and_ignore_internal(harness: Harness) -> None:
    waiter = harness.api("plugins.core.triggers:waiter.add")()
    feed_waiters(harness, "internal", internal=True)
    feed_waiters(harness, "mud")
    assert [s.text for s in waiter._queue] == ["mud"]


def test_no_waiter_does_nothing(harness: Harness) -> None:
    feed_waiters(harness, "mud")
    assert harness.api("plugins.core.triggers:waiter.count")() == 0


def test_add_resolves_owner(harness: Harness) -> None:
    waiter = harness.api("plugins.core.triggers:waiter.add")()
    assert waiter.owner_id == OWNER
    harness.owner = None
    assert harness.api("plugins.core.triggers:waiter.add")() is None
    assert harness.errors()


async def test_one_shot_apis_register_nothing_until_awaited(
    harness: Harness, monkeypatch: Any
) -> None:
    make_recorder(monkeypatch)
    api = harness.api
    coros = [
        api("plugins.core.triggers:line.get.next")("x", 0.01),
        api("plugins.core.triggers:prompt.get.next")(0.01),
        api("plugins.core.triggers:line.get.after.send")("cmd", "x", 0.01),
    ]
    assert api("plugins.core.triggers:waiter.count")() == 0
    for coro in coros:
        assert await coro is None
        assert api("plugins.core.triggers:waiter.count")() == 0


async def test_line_get_next_matches_and_cancel(harness: Harness) -> None:
    task = asyncio.create_task(harness.api("plugins.core.triggers:line.get.next")("hi", 1))
    await asyncio.sleep(0)
    assert harness.api("plugins.core.triggers:waiter.count")() == 1
    feed_waiters(harness, "hi there")
    result = await task
    assert result is not None and result.text == "hi there"
    assert harness.api("plugins.core.triggers:waiter.count")() == 0

    task = asyncio.create_task(harness.api("plugins.core.triggers:line.get.next")("hi", 5))
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert harness.api("plugins.core.triggers:waiter.count")() == 0


async def test_send_and_wait_sends_command(harness: Harness, monkeypatch: Any) -> None:
    sent = make_recorder(monkeypatch)
    task = asyncio.create_task(
        harness.api("plugins.core.triggers:line.get.after.send")("score", "Level", 1)
    )
    await asyncio.sleep(0)
    assert sent == ["score"]
    feed_waiters(harness, "Level: 3")
    assert (await task) is not None


async def test_unload_closes_owner_waiters(harness: Harness) -> None:
    task = asyncio.create_task(harness.api("plugins.core.triggers:line.get.next")("x", 5))
    await asyncio.sleep(0)
    harness.current_record = {"plugin_id": OWNER}
    harness._eventcb_close_waiters_on_unload()
    assert await task is None
    assert harness.api("plugins.core.triggers:waiter.count")() == 0


def test_waiters_receive_lines_while_triggers_disabled(harness: Harness) -> None:
    harness.__dict__["_matching_enabled"] = False
    waiter = harness.api("plugins.core.triggers:waiter.add")()
    feed_waiters(harness, "mud")
    assert [s.text for s in waiter._queue] == ["mud"]


def test_trigger_matching_unchanged_with_waiter(harness: Harness) -> None:
    harness.add("t", r"^hello")
    harness.listen("t")
    baseline = harness.send("hello world")
    harness.api("plugins.core.triggers:waiter.add")()
    assert harness.send("hello world") == baseline
    assert any("t" in name for name in baseline)

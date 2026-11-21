"""Tests for the signal handler and TaskItem.result (#677)."""

import asyncio
import logging
import signal

import pytest

from bastproxy.libs import asynch


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[signal.Signals]:
    """Patch shutdown with a recorder and reset the run-once flag."""
    recorded: list[signal.Signals] = []

    async def fake(sig: signal.Signals, loop: asyncio.AbstractEventLoop) -> None:
        recorded.append(sig)

    monkeypatch.setattr(asynch, "shutdown", fake)
    monkeypatch.setattr(asynch, "_SHUTDOWN_STARTED", False)
    return recorded


async def test_repeated_signal_runs_shutdown_once(
    calls: list[signal.Signals], caplog: pytest.LogCaptureFixture
) -> None:
    loop = asyncio.get_running_loop()
    with caplog.at_level(logging.WARNING):
        first = asynch._signal_handler(signal.SIGINT, loop)
        second = asynch._signal_handler(signal.SIGINT, loop)
        assert first is not None
        assert first.task is not None
        await first.task
    assert second is None
    assert calls == [signal.SIGINT]
    assert "already in progress" in caplog.text
    assert "cannot reuse" not in caplog.text


async def test_each_call_builds_fresh_coroutine(
    calls: list[signal.Signals], monkeypatch: pytest.MonkeyPatch
) -> None:
    loop = asyncio.get_running_loop()
    first = asynch._signal_handler(signal.SIGINT, loop)
    monkeypatch.setattr(asynch, "_SHUTDOWN_STARTED", False)
    second = asynch._signal_handler(signal.SIGTERM, loop)
    assert first is not None
    assert second is not None
    assert first.task is not None
    assert second.task is not None
    await asyncio.gather(first.task, second.task)
    assert calls == [signal.SIGINT, signal.SIGTERM]


async def test_result_none_before_create() -> None:
    async def val() -> int:
        return 3

    item = asynch.TaskItem(val(), "r")
    assert item.result is None
    item.coroutine.close()


async def test_result_lifecycle() -> None:
    event = asyncio.Event()

    async def val() -> int:
        await event.wait()
        return 3

    item = asynch.TaskItem(val(), "r")
    task = item.create()
    await asyncio.sleep(0)
    assert item.result is None
    event.set()
    await task
    assert item.result == 3


async def test_result_reraises_task_exception(caplog: pytest.LogCaptureFixture) -> None:
    async def fail() -> None:
        raise ValueError("bad")

    item = asynch.TaskItem(fail(), "r")
    task = item.create()
    with caplog.at_level(logging.ERROR), pytest.raises(ValueError):
        await task
    with pytest.raises(ValueError):
        _ = item.result

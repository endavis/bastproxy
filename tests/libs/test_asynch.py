"""Tests for TaskItem validation and the QueueManager task checker (#676)."""

import asyncio
import logging

import pytest

from bastproxy.libs import asynch


def _manager() -> asynch.QueueManager:
    """Build a QueueManager without registering APIs."""
    qm = object.__new__(asynch.QueueManager)
    qm.task_queue = asyncio.Queue()
    return qm


async def _noop() -> int:
    return 1


def test_taskitem_rejects_non_callable() -> None:
    with pytest.raises(TypeError):
        asynch.TaskItem(5, "x")  # type: ignore[arg-type]


def test_taskitem_rejects_callable_not_returning_coroutine() -> None:
    with pytest.raises(TypeError):
        asynch.TaskItem(lambda: 5, "x")


async def test_taskitem_accepts_coroutine_and_async_function() -> None:
    item = asynch.TaskItem(_noop(), "a")
    item2 = asynch.TaskItem(_noop, "b")
    assert asyncio.iscoroutine(item.coroutine)
    assert asyncio.iscoroutine(item2.coroutine)
    item.coroutine.close()
    item2.coroutine.close()


@pytest.mark.parametrize("bad", [lambda: 5, 5])
def test_api_task_add_refuses_bad_input(bad: object, caplog: pytest.LogCaptureFixture) -> None:
    qm = _manager()
    with caplog.at_level(logging.ERROR):
        assert qm._api_task_add(bad, "bad") is None  # type: ignore[arg-type]
    assert qm.task_queue.empty()
    assert "could not add task" in caplog.text


async def test_checker_survives_failing_create(caplog: pytest.LogCaptureFixture) -> None:
    qm = _manager()
    done = asyncio.Event()

    async def good() -> None:
        done.set()

    assert qm._api_task_add(lambda: 5, "bad") is None
    bad_item = asynch.TaskItem(_noop(), "boom")

    def boom(*_args: object, **_kwargs: object) -> asyncio.Task:
        raise RuntimeError("boom")

    bad_item.create = boom  # type: ignore[method-assign]
    qm.task_queue.put_nowait(bad_item)
    good_item = qm._api_task_add(good, "good")
    assert good_item is not None

    checker = asyncio.create_task(qm.task_check_for_new_tasks())
    try:
        with caplog.at_level(logging.ERROR):
            await asyncio.wait_for(done.wait(), 2)
        assert not checker.done()
        assert "could not create task" in caplog.text
    finally:
        checker.cancel()
        bad_item.coroutine.close()

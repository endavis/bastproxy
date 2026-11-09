"""Tests for the context variables behind the active record, event stack and command args (#248)."""

import asyncio

import pytest

from bastproxy.libs.asynch import TaskItem
from bastproxy.libs.context import (
    active_record,
    active_records,
    command_args,
    event_stack,
    fresh_context,
    get_command_args,
    raised_event,
    running_command,
)


def test_defaults() -> None:
    assert active_records.get() == ()
    assert event_stack.get() == ()
    assert command_args.get() is None
    assert get_command_args() == {}


def test_active_record_nests_and_restores() -> None:
    with active_record("outer"):
        assert active_records.get() == ("outer",)
        with active_record("inner"):
            assert active_records.get() == ("outer", "inner")
        assert active_records.get() == ("outer",)
    assert active_records.get() == ()


def test_raised_event_restores_on_exception() -> None:
    with pytest.raises(RuntimeError), raised_event("ev_a"):
        assert event_stack.get() == ("ev_a",)
        raise RuntimeError
    assert event_stack.get() == ()


def test_active_record_restores_on_exception() -> None:
    with pytest.raises(RuntimeError), active_record("r"):
        raise RuntimeError
    assert active_records.get() == ()


def test_nested_running_command_restores_the_outer_args() -> None:
    with running_command({"a": 1}):
        with running_command({"b": 2}):
            assert get_command_args() == {"b": 2}
        assert get_command_args() == {"a": 1}
    assert get_command_args() == {}


def test_running_command_restores_on_exception() -> None:
    with pytest.raises(RuntimeError), running_command({"a": 1}):
        raise RuntimeError
    assert command_args.get() is None


def test_fresh_context_resets_the_variables_only_inside_it() -> None:
    with active_record("r"), raised_event("ev"), running_command({"a": 1}):
        ctx = fresh_context()
        assert ctx.run(active_records.get) == ()
        assert ctx.run(event_stack.get) == ()
        assert ctx.run(command_args.get) is None
        assert active_records.get() == ("r",)
        assert event_stack.get() == ("ev",)


async def test_task_created_by_taskitem_sees_no_context() -> None:
    seen: dict[str, object] = {}

    async def probe() -> None:
        seen["records"] = active_records.get()
        seen["events"] = event_stack.get()
        seen["args"] = command_args.get()

    item = TaskItem(probe(), name="test248")
    with active_record("r"), raised_event("ev"), running_command({"a": 1}):
        task = item.create(loop=asyncio.get_running_loop())
    await task
    assert seen == {"records": (), "events": (), "args": None}

"""Tests for Listeners.check_listeners_available (#309)."""

import asyncio
import logging
from collections.abc import Callable
from typing import Any

import pytest

from bastproxy.libs.net import listeners as listeners_mod
from bastproxy.libs.net.listeners import Listeners


class FakeTask:
    """Stand-in for TaskItem with the same done/result properties."""

    def __init__(self, error: Exception | None = None) -> None:
        self.done = True
        self._error = error

    @property
    def result(self) -> None:
        if self._error:
            raise self._error


def _make(monkeypatch: pytest.MonkeyPatch) -> Listeners:
    async def no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr(listeners_mod.asyncio, "sleep", no_sleep)
    obj = Listeners()
    settings = {"ipv4": True, "ipv6": True}

    def fake_api(_name: str) -> Callable[..., Any]:
        return lambda _plugin, key: settings.get(key, "x")

    obj.api = fake_api  # type: ignore[assignment]
    return obj


async def test_failed_ipv4_task_logs_and_leaves_flag_false(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    obj = _make(monkeypatch)
    obj.ipv4_task = FakeTask(OSError("address in use"))  # type: ignore[assignment]
    obj.ipv6_task = FakeTask()  # type: ignore[assignment]
    with caplog.at_level(logging.ERROR, logger="mudproxy"):
        await asyncio.wait_for(obj.check_listeners_available(), 5)

    assert obj.ipv4_start is False
    assert obj.ipv6_start is True
    failures = [r for r in caplog.records if "IPv4 listener task failed" in r.getMessage()]
    assert len(failures) == 1
    assert failures[0].exc_info is not None
    assert "address in use" in str(failures[0].exc_info[1])
    assert not any("IPv6 listener task failed" in r.getMessage() for r in caplog.records)


async def test_failed_ipv6_task_logs_and_leaves_flag_false(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    obj = _make(monkeypatch)
    obj.ipv4_task = FakeTask()  # type: ignore[assignment]
    obj.ipv6_task = FakeTask(OSError("no ipv6"))  # type: ignore[assignment]
    with caplog.at_level(logging.ERROR, logger="mudproxy"):
        await asyncio.wait_for(obj.check_listeners_available(), 5)

    assert obj.ipv4_start is True
    assert obj.ipv6_start is False
    assert any("IPv6 listener task failed" in r.getMessage() for r in caplog.records)


async def test_successful_tasks_set_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    obj = _make(monkeypatch)
    obj.ipv4_task = FakeTask()  # type: ignore[assignment]
    obj.ipv6_task = FakeTask()  # type: ignore[assignment]
    await asyncio.wait_for(obj.check_listeners_available(), 5)

    assert obj.ipv4_start is True
    assert obj.ipv6_start is True

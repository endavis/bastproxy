"""debug.async.tasks shows readable stacks and public task state (#688)."""

import importlib
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

# the package is named "async", a keyword, so it cannot be imported with a plain import
_async: Any = importlib.import_module("bastproxy.plugins.debug.async.plugin._async")


def _frame(filename: str, lineno: int, name: str) -> SimpleNamespace:
    return SimpleNamespace(
        f_lineno=lineno, f_code=SimpleNamespace(co_filename=filename, co_name=name)
    )


class _FakeTask:
    def __init__(
        self, *, done: bool = False, cancelled: bool = False, stack: list[Any] | None = None
    ) -> None:
        self._done = done
        self._cancelled = cancelled
        self._stack = stack or []

    def get_name(self) -> str:
        return "task-1"

    def done(self) -> bool:
        return self._done or self._cancelled

    def cancelled(self) -> bool:
        return self._cancelled

    def get_coro(self) -> Any:
        return SimpleNamespace(__qualname__="mycoro")

    def get_stack(self) -> list[Any]:
        return self._stack


def _run(monkeypatch: pytest.MonkeyPatch, task: _FakeTask) -> list[str]:
    monkeypatch.setattr(_async.asyncio, "all_tasks", lambda: [task])
    stub = MagicMock()

    def api(name: str) -> Callable[..., Any]:
        if name == "plugins.core.commands:output.line.length.get":
            return lambda: 10
        if name == "plugins.core.settings:setting.get":
            return lambda *_: "@x"
        raise AssertionError(name)

    stub.api = api
    result = _async.AsyncPlugin._command_tasks(stub)
    assert result.success is True
    return list(result.message)


@pytest.mark.parametrize(
    ("kwargs", "state"),
    [
        ({}, "pending"),
        ({"done": True}, "done"),
        ({"cancelled": True}, "cancelled"),
    ],
)
def test_state(monkeypatch: pytest.MonkeyPatch, kwargs: dict[str, bool], state: str) -> None:
    task = _FakeTask(done=kwargs.get("done", False), cancelled=kwargs.get("cancelled", False))
    assert _async._task_state(task) == state
    assert f"        {'State':<20} : {state}" in _run(monkeypatch, task)


def test_stack_one_line_per_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    task = _FakeTask(stack=[_frame("a.py", 10, "fn"), _frame("b.py", 20, "gn")])
    lines = _run(monkeypatch, task)
    idx = lines.index(f"        {'Stack':<20} :")
    assert lines[idx + 1 : idx + 3] == ["            a.py:10 fn", "            b.py:20 gn"]
    assert not any("<frame at" in line or "[" in line for line in lines)


def test_empty_stack(monkeypatch: pytest.MonkeyPatch) -> None:
    lines = _run(monkeypatch, _FakeTask())
    assert f"        {'Stack':<20} : none" in lines

"""Tests for the sendwait demo command (#548)."""

# Standard Library
from typing import Any

# Third Party
import pytest

# Project
from bastproxy.plugins.core.triggers.plugin._waiters import WaitResult
from bastproxy.plugins.test.triggers.plugin import _triggerex
from bastproxy.plugins.test.triggers.plugin._triggerex import TriggerExPlugin


class StubWaiter:
    def __init__(self, result: Any, prompt: Any) -> None:
        self.result = result
        self.prompt = prompt
        self.closed = False

    def __enter__(self) -> "StubWaiter":
        return self

    def __exit__(self, *_a: Any) -> None:
        self.closed = True

    async def send_and_wait(
        self,
        command: str,
        pattern: str,
        timeout: float,  # noqa: ASYNC109  # per-call timeout is the helper API; asyncio.timeout is used inside
    ) -> Any:
        return self.result

    async def wait_for_prompt(self, timeout: float) -> Any:  # noqa: ASYNC109  # per-call timeout is the helper API; asyncio.timeout is used inside
        return self.prompt


class Fake:
    plugin_id = "plugins.test.triggers"

    def __init__(self, waiter: StubWaiter, args: dict[str, Any] | None = None) -> None:
        self.waiter = waiter
        self.args = args or {}
        self.tasks: list[tuple[Any, str]] = []

    def _sendwait(self, *args: Any) -> Any:
        return TriggerExPlugin._sendwait(self, *args)  # type: ignore[arg-type]

    def api(self, name: str) -> Any:
        table: dict[str, Any] = {
            "plugins.core.commands:command.current.args.get": lambda: self.args,
            "libs.asynch:task.add": lambda coro, n: self.tasks.append((coro, n)),
            "plugins.core.triggers:waiter.add": lambda: self.waiter,
            "plugins.core.triggers:waiter.count": lambda: 0,
        }
        return table[name]


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    out: list[Any] = []
    monkeypatch.setattr(
        _triggerex,
        "SendDataDirectlyToClient",
        lambda data: lambda: out.append([str(x.line) for x in data]),
    )
    return out


def test_command_schedules_one_task() -> None:
    fake = Fake(
        StubWaiter(None, None),
        {"command": ["score", "all"], "pattern": "x", "timeout": 2.0, "prompt": False},
    )
    result = TriggerExPlugin._command_sendwait(fake)
    assert result.success
    assert len(fake.tasks) == 1
    assert fake.tasks[0][1].endswith(":sendwait")
    assert "score all" in result.message[0]
    fake.tasks[0][0].close()


async def test_match_and_prompt(client: list[Any]) -> None:
    import regex as re

    m = re.match(r"(?P<a>\d+)", "12")
    fake = Fake(StubWaiter(WaitResult("12", False, m), WaitResult("P>", True)))
    await TriggerExPlugin._sendwait(fake, "c", "x", 1.0, True)  # type: ignore[arg-type]
    text = "\n".join(client[0])
    assert "matched: 12" in text and "'a': '12'" in text and "P>" in text
    assert "open waiters: 0" in text
    assert fake.waiter.closed


async def test_timeout(client: list[Any]) -> None:
    fake = Fake(StubWaiter(None, None))
    await TriggerExPlugin._sendwait(fake, "c", "x", 1.0, False)  # type: ignore[arg-type]
    assert "timed out" in "\n".join(client[0])

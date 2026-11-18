"""Send a command, then wait for the MUD output that answers it (#548).

A ``LineWaiter`` keeps its own bounded queue of MUD lines. A wait consumes the
queued lines (oldest first) up to and including its match, then waits for new
ones. Every waiter sees every line, so two plugins never take each other's
matches. Errors are logged and the wait resolves to ``None``; nothing raises.
"""

# Standard Library
import asyncio
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar

# 3rd Party
import regex as re

# Project
from bastproxy.libs.logger import log_to

DEFAULT_TIMEOUT = 10.0
DEFAULT_MAX_LINES = 1000
_SOURCE = "plugins.core.triggers"

_T = TypeVar("_T")


@dataclass(frozen=True, slots=True)
class WaitResult:
    """The line a wait resolved on."""

    text: str
    is_prompt: bool
    match: "re.Match[str] | None" = None

    @property
    def matches(self) -> dict[str, str | None]:
        """The named groups of the match, empty for a prompt wait."""
        return dict(self.match.groupdict()) if self.match else {}


@dataclass(frozen=True, slots=True)
class _Seen:
    """One queued MUD line."""

    text: str
    is_prompt: bool


_Matcher = Callable[[_Seen], "WaitResult | None"]


class LineWaiter:
    """A bounded queue of MUD lines with awaitable matching."""

    def __init__(
        self,
        owner_id: str,
        registry: "WaiterRegistry | None" = None,
        max_lines: int = DEFAULT_MAX_LINES,
    ) -> None:
        self.owner_id = owner_id
        self.closed = False
        self._registry = registry
        self._queue: deque[_Seen] = deque(maxlen=max_lines)
        self._pending: tuple[_Matcher, asyncio.Future[WaitResult | None]] | None = None

    def __enter__(self) -> "LineWaiter":
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def feed(self, text: str, is_prompt: bool) -> None:
        """Offer one MUD line: to the pending wait, otherwise to the queue."""
        if self.closed:
            return
        seen = _Seen(text, is_prompt)
        if self._pending is None:
            self._queue.append(seen)
            return
        matcher, future = self._pending
        if future.done():
            self._queue.append(seen)
            return
        if (result := matcher(seen)) is not None:
            future.set_result(result)

    def close(self) -> None:
        """Close the waiter; idempotent. A pending wait resolves to ``None``."""
        if self.closed:
            return
        self.closed = True
        self._queue.clear()
        if self._registry is not None:
            self._registry.remove(self)
        if self._pending is not None:
            future = self._pending[1]
            if not future.done():
                future.set_result(None)

    def send(self, command: str) -> None:
        """Send a command to the MUD on behalf of this waiter's owner."""
        if self._registry is not None:
            self._registry.send(command, self.owner_id)

    async def _wait(
        self,
        matcher: _Matcher,
        timeout: float,  # noqa: ASYNC109  # per-call timeout is the helper API; asyncio.timeout is used inside
    ) -> WaitResult | None:
        """Drain the queue through ``matcher``, then wait for new lines."""
        if self.closed:
            log_to([_SOURCE, self.owner_id], logging.ERROR, "wait on a closed waiter")
            return None
        if self._pending is not None:
            log_to(
                [_SOURCE, self.owner_id],
                logging.ERROR,
                "a wait is already pending on this waiter",
            )
            return None
        if timeout <= 0:
            log_to(
                [_SOURCE, self.owner_id], logging.ERROR, "timeout must be positive, got %s", timeout
            )
            return None
        while self._queue:
            if (result := matcher(self._queue.popleft())) is not None:
                return result
        future: asyncio.Future[WaitResult | None] = asyncio.get_running_loop().create_future()
        self._pending = (matcher, future)
        try:
            async with asyncio.timeout(timeout):
                return await future
        except TimeoutError:
            return None
        finally:
            self._pending = None
            if not future.done():
                future.cancel()

    async def wait_for(
        self,
        pattern: str,
        timeout: float = DEFAULT_TIMEOUT,  # noqa: ASYNC109  # per-call timeout is the helper API; asyncio.timeout is used inside
    ) -> WaitResult | None:
        """Wait for the next line that ``pattern`` matches (``.match()``)."""
        try:
            compiled = re.compile(pattern)
        except re.error as err:
            log_to(
                [_SOURCE, self.owner_id], logging.ERROR, "invalid wait pattern %r: %s", pattern, err
            )
            return None

        def matcher(seen: _Seen) -> WaitResult | None:
            if match := compiled.match(seen.text):
                return WaitResult(seen.text, seen.is_prompt, match)
            return None

        return await self._wait(matcher, timeout)

    async def wait_for_prompt(
        self,
        timeout: float = DEFAULT_TIMEOUT,  # noqa: ASYNC109  # per-call timeout is the helper API; asyncio.timeout is used inside
    ) -> WaitResult | None:
        """Wait for the next prompt line (needs GA or EOR from the MUD)."""

        def matcher(seen: _Seen) -> WaitResult | None:
            return WaitResult(seen.text, True) if seen.is_prompt else None

        return await self._wait(matcher, timeout)

    async def send_and_wait(
        self,
        command: str,
        pattern: str,
        timeout: float = DEFAULT_TIMEOUT,  # noqa: ASYNC109  # per-call timeout is the helper API; asyncio.timeout is used inside
    ) -> WaitResult | None:
        """Send ``command``, then wait for a line matching ``pattern``."""
        self.send(command)
        return await self.wait_for(pattern, timeout)


class WaiterRegistry:
    """The open waiters, and the sender they use."""

    def __init__(self, sender: Callable[[str, str], None]) -> None:
        self._sender = sender
        self._waiters: list[LineWaiter] = []

    def __len__(self) -> int:
        return len(self._waiters)

    def __bool__(self) -> bool:
        return bool(self._waiters)

    def send(self, command: str, owner_id: str) -> None:
        """Send a command to the MUD."""
        self._sender(command, owner_id)

    def add(self, owner_id: str, max_lines: int = DEFAULT_MAX_LINES) -> LineWaiter:
        """Open a waiter; it queues lines at once."""
        waiter = LineWaiter(owner_id, self, max_lines)
        self._waiters.append(waiter)
        return waiter

    def remove(self, waiter: LineWaiter) -> None:
        """Forget a waiter."""
        if waiter in self._waiters:
            self._waiters.remove(waiter)

    def feed(self, text: str, is_prompt: bool) -> None:
        """Offer a line to every open waiter; one that raises does not stop the rest."""
        for waiter in list(self._waiters):
            try:
                waiter.feed(text, is_prompt)
            except Exception:  # pylint: disable=broad-except
                log_to(
                    [_SOURCE, waiter.owner_id],
                    logging.ERROR,
                    "feeding a waiter failed",
                    exc_info=True,
                )

    def close_for_owner(self, owner_id: str) -> int:
        """Close every waiter of an owner; return how many were closed."""
        owned = [w for w in self._waiters if w.owner_id == owner_id]
        for waiter in owned:
            waiter.close()
        return len(owned)

    async def once(self, owner_id: str, action: Callable[[LineWaiter], Awaitable[_T]]) -> _T:
        """Run ``action`` with a fresh waiter that is closed afterwards."""
        with self.add(owner_id) as waiter:
            return await action(waiter)


__all__: list[Any] = [
    "DEFAULT_MAX_LINES",
    "DEFAULT_TIMEOUT",
    "LineWaiter",
    "WaitResult",
    "WaiterRegistry",
]

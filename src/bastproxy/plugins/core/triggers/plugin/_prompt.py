"""A queue of trigger events held until the next prompt arrives (#544)."""

# Standard Library
import time
from collections import deque
from collections.abc import Callable
from typing import Any

# Seconds a queued event may wait for a prompt before it is raised without one
PROMPT_MAX_WAIT = 2.0


class PromptQueue:
    """Hold ``(item, args)`` entries in arrival order until a prompt flushes them.

    An entry older than ``max_wait`` seconds is returned by ``take_expired``, so a
    prompt that never comes does not hold an event for good. Expiry is lazy: the
    owner calls ``take_expired`` when the next line arrives.
    """

    def __init__(
        self,
        max_wait: float = PROMPT_MAX_WAIT,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._entries: deque[tuple[Any, dict[str, Any], float]] = deque()
        self._max_wait = max_wait
        self._clock = clock

    def add(self, item: Any, args: dict[str, Any]) -> None:
        """Queue an event for ``item`` with its callback ``args``."""
        self._entries.append((item, args, self._clock()))

    def take_all(self) -> list[tuple[Any, dict[str, Any]]]:
        """Remove and return every entry in arrival order."""
        entries = [(item, args) for item, args, _added in self._entries]
        self._entries.clear()
        return entries

    def take_expired(self) -> list[tuple[Any, dict[str, Any]]]:
        """Remove and return the entries that have waited ``max_wait`` or longer."""
        now = self._clock()
        expired: list[tuple[Any, dict[str, Any]]] = []
        while self._entries and now - self._entries[0][2] >= self._max_wait:
            item, args, _added = self._entries.popleft()
            expired.append((item, args))
        return expired

    def clear(self) -> None:
        """Drop every entry."""
        self._entries.clear()

    def __len__(self) -> int:
        """Return the number of queued entries."""
        return len(self._entries)

    def __bool__(self) -> bool:
        """Return whether anything is queued."""
        return bool(self._entries)

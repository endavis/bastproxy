"""A bounded record of lines the proxy sent to the MUD, used to skip their echoes (#545)."""

# Standard Library
import time
from collections import deque
from collections.abc import Callable

ECHO_MAX_ENTRIES = 20
ECHO_MAX_AGE = 15.0


class EchoRecord:
    """Remember sent lines so the MUD's echo of one can be recognised once.

    The record holds at most ``max_entries`` lines, each for at most ``max_age``
    seconds, so a line the MUD never echoes does not linger.
    """

    def __init__(
        self,
        max_entries: int = ECHO_MAX_ENTRIES,
        max_age: float = ECHO_MAX_AGE,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._entries: deque[tuple[str, float]] = deque(maxlen=max_entries)
        self._max_age = max_age
        self._clock = clock

    def add(self, text: str) -> None:
        """Record a sent line. An empty line is ignored."""
        if text == "":
            return
        self._entries.append((text, self._clock()))

    def _drop_expired(self) -> None:
        """Remove entries that have reached ``max_age`` (oldest are first)."""
        now = self._clock()
        while self._entries and now - self._entries[0][1] >= self._max_age:
            self._entries.popleft()

    def consume(self, text: str) -> bool:
        """Remove the first entry equal to ``text``; return whether there was one."""
        self._drop_expired()
        for index, (entry, _added) in enumerate(self._entries):
            if entry == text:
                del self._entries[index]
                return True
        return False

    def __len__(self) -> int:
        """Return the number of recorded lines."""
        return len(self._entries)

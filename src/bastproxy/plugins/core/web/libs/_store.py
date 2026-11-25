# Project: bastproxy
# Filename: plugins/core/web/libs/_store.py
#
# File Description: in-memory stores for the web plugin
#
# By: Bast
"""The in-memory page store."""

# Standard Library
import secrets
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

# keep module identity across a reload of the plugin (the store is carried over)
CANRELOAD = False


@dataclass(frozen=True)
class Page:
    """One stored page, already rendered to html."""

    owner: str
    title: str
    body: bytes
    expires: float


class PageStore:
    """Pages behind unguessable tokens, capped and expiring, oldest dropped first."""

    def __init__(
        self, cap: int = 50, ttl: float = 3600, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.cap = cap
        self.ttl = ttl
        self._clock = clock
        self._pages: OrderedDict[str, Page] = OrderedDict()

    def _prune(self) -> None:
        now = self._clock()
        for token in [t for t, page in self._pages.items() if page.expires <= now]:
            del self._pages[token]

    def add(self, owner: str, title: str, body: bytes) -> str:
        """Store a page and return its token."""
        self._prune()
        token = secrets.token_urlsafe(32)
        self._pages[token] = Page(owner, title, body, self._clock() + self.ttl)
        while len(self._pages) > self.cap:
            self._pages.popitem(last=False)
        return token

    def get(self, token: str) -> Page | None:
        """Return the page for a token, or None when unknown or expired."""
        self._prune()
        return self._pages.get(token)

    def count(self) -> int:
        """Return the number of live pages."""
        self._prune()
        return len(self._pages)

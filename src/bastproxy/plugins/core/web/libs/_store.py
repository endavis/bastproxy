# Project: bastproxy
# Filename: plugins/core/web/libs/_store.py
#
# File Description: in-memory stores for the web plugin
#
# By: Bast
"""The in-memory stores: pages, login tokens, sessions and routes."""

# Standard Library
import re
import secrets
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

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


class LoginTokens:
    """Single-use login tokens that expire, oldest dropped first."""

    def __init__(
        self, ttl: float = 300, cap: int = 20, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.ttl = ttl
        self.cap = cap
        self._clock = clock
        self._tokens: OrderedDict[str, float] = OrderedDict()

    def _prune(self) -> None:
        now = self._clock()
        for token in [t for t, expires in self._tokens.items() if expires <= now]:
            del self._tokens[token]

    def issue(self) -> str:
        """Create a token."""
        self._prune()
        token = secrets.token_urlsafe(32)
        self._tokens[token] = self._clock() + self.ttl
        while len(self._tokens) > self.cap:
            self._tokens.popitem(last=False)
        return token

    def consume(self, token: str) -> bool:
        """Use a token: True once for a live token, False for an unknown, used or expired one."""
        self._prune()
        return self._tokens.pop(token, None) is not None


class SessionStore:
    """Login sessions, in memory only, capped, oldest dropped first."""

    def __init__(self, cap: int = 20, clock: Callable[[], float] = time.monotonic) -> None:
        self.cap = cap
        self._clock = clock
        self._sessions: OrderedDict[str, float] = OrderedDict()

    def _prune(self) -> None:
        now = self._clock()
        for sid in [s for s, expires in self._sessions.items() if expires <= now]:
            del self._sessions[sid]

    def create(self, lifetime_s: float) -> str:
        """Start a session that lasts ``lifetime_s`` seconds and return its id."""
        self._prune()
        sid = secrets.token_urlsafe(32)
        self._sessions[sid] = self._clock() + lifetime_s
        while len(self._sessions) > self.cap:
            self._sessions.popitem(last=False)
        return sid

    def is_valid(self, sid: str | None) -> bool:
        """True when the id belongs to a live session."""
        self._prune()
        return sid is not None and sid in self._sessions

    def clear(self) -> int:
        """End every session and return how many there were."""
        self._prune()
        count = len(self._sessions)
        self._sessions.clear()
        return count

    def count(self) -> int:
        """Return the number of live sessions."""
        self._prune()
        return len(self._sessions)


SUBPATH_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*(/[a-z0-9][a-z0-9_-]*)*$")
RESERVED_SEGMENTS = frozenset({"p", "login", "static"})


@dataclass(frozen=True)
class Route:
    """One page a plugin serves under its own prefix."""

    owner: str
    path: str
    subpath: str
    handler: Callable[..., Any]
    title: str


class RouteTable:
    """The routes of all plugins, keyed by the url path."""

    def __init__(self) -> None:
        self._routes: dict[str, Route] = {}

    @staticmethod
    def prefix_for(owner: str) -> str:
        """The url prefix of a plugin id: ``plugins.aardwolf.mapper`` gives ``aardwolf/mapper``."""
        return owner.removeprefix("plugins.").replace(".", "/")

    def add(self, owner: str, subpath: str, handler: Callable[..., Any], title: str) -> str:
        """Add a route and return its path.

        Raises:
            ValueError: The subpath is invalid, the first segment is reserved, or another
                owner already serves the path.

        """
        if subpath and not SUBPATH_RE.fullmatch(subpath):
            msg = f"invalid subpath {subpath!r}: use lower case letters, digits, _ and -"
            raise ValueError(msg)
        prefix = self.prefix_for(owner)
        if not prefix or prefix.split("/", 1)[0] in RESERVED_SEGMENTS:
            msg = f"the prefix {prefix!r} starts with a reserved segment"
            raise ValueError(msg)
        path = f"/{prefix}/{subpath}" if subpath else f"/{prefix}"
        existing = self._routes.get(path)
        if existing is not None and existing.owner != owner:
            msg = f"{path} is already served by {existing.owner}"
            raise ValueError(msg)
        self._routes[path] = Route(owner, path, subpath, handler, title)
        return path

    def remove(self, owner: str) -> int:
        """Remove every route of an owner and return how many there were."""
        paths = [path for path, route in self._routes.items() if route.owner == owner]
        for path in paths:
            del self._routes[path]
        return len(paths)

    def match(self, path: str) -> Route | None:
        """Return the route served at exactly this path."""
        return self._routes.get(path)

    def by_owner(self) -> dict[str, list[Route]]:
        """The routes grouped by owner, each list sorted by path."""
        grouped: dict[str, list[Route]] = {}
        for route in sorted(self._routes.values(), key=lambda r: r.path):
            grouped.setdefault(route.owner, []).append(route)
        return grouped

    def count(self) -> int:
        """Return the number of routes."""
        return len(self._routes)

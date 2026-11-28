# Project: bastproxy
# Filename: plugins/core/web/libs/_store.py
#
# File Description: in-memory stores for the web plugin
#
# By: Bast
"""The in-memory stores: pages, login tokens, sessions and routes."""

# Standard Library
import inspect
import re
import secrets
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from bastproxy.libs.logger import get_logger

from ._http import Request
from ._table import Column, escape_cells, make_columns, page_rows
from ._tls import LOGGER_NAME

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
        self._view: set[str] = set()

    def _prune(self) -> None:
        now = self._clock()
        for token in [t for t, expires in self._tokens.items() if expires <= now]:
            del self._tokens[token]
            self._view.discard(token)

    def issue(self, *, view_only: bool = False) -> str:
        """Create a token; a view-only token starts a view-only session."""
        self._prune()
        token = secrets.token_urlsafe(32)
        self._tokens[token] = self._clock() + self.ttl
        if view_only:
            self._view.add(token)
        while len(self._tokens) > self.cap:
            dropped, _ = self._tokens.popitem(last=False)
            self._view.discard(dropped)
        return token

    def take(self, token: str) -> bool | None:
        """Use a token: None for an unknown, used or expired one, else True when view-only."""
        self._prune()
        if self._tokens.pop(token, None) is None:
            return None
        view = token in self._view
        self._view.discard(token)
        return view

    def consume(self, token: str) -> bool:
        """Use a token: True once for a live token, False for an unknown, used or expired one."""
        return self.take(token) is not None


class SessionStore:
    """Login sessions, in memory only, capped, oldest dropped first."""

    def __init__(self, cap: int = 20, clock: Callable[[], float] = time.monotonic) -> None:
        self.cap = cap
        self._clock = clock
        self._sessions: OrderedDict[str, float] = OrderedDict()
        self._view: set[str] = set()

    def _prune(self) -> None:
        now = self._clock()
        for sid in [s for s, expires in self._sessions.items() if expires <= now]:
            del self._sessions[sid]
            self._view.discard(sid)

    def create(self, lifetime_s: float, *, view_only: bool = False) -> str:
        """Start a session that lasts ``lifetime_s`` seconds and return its id."""
        self._prune()
        sid = secrets.token_urlsafe(32)
        self._sessions[sid] = self._clock() + lifetime_s
        if view_only:
            self._view.add(sid)
        while len(self._sessions) > self.cap:
            dropped, _ = self._sessions.popitem(last=False)
            self._view.discard(dropped)
        return sid

    def is_view_only(self, sid: str | None) -> bool:
        """True when the id belongs to a live view-only session."""
        self._prune()
        return sid is not None and sid in self._sessions and sid in self._view

    def is_valid(self, sid: str | None) -> bool:
        """True when the id belongs to a live session."""
        self._prune()
        return sid is not None and sid in self._sessions

    def lookup(self, sid: str | None) -> bool | None:
        """Read a session once: None when there is no live session, else True when view-only."""
        self._prune()
        if sid is None or sid not in self._sessions:
            return None
        return sid in self._view

    def clear(self) -> int:
        """End every session and return how many there were."""
        self._prune()
        count = len(self._sessions)
        self._sessions.clear()
        self._view.clear()
        return count

    def count(self) -> int:
        """Return the number of live sessions."""
        self._prune()
        return len(self._sessions)


SUBPATH_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*(/[a-z0-9][a-z0-9_-]*)*$")
CLIENT_SEGMENT = "webclient"
DATA_SEGMENT = "data"
RESERVED_SEGMENTS = frozenset({"p", "login", "static", "ws", CLIENT_SEGMENT, DATA_SEGMENT})


PROVIDER_KINDS = ("json", "table")


@dataclass(frozen=True)
class Provider:
    """A data provider: a route whose data other consumers can follow by topic."""

    name: str
    topic: str
    kind: str
    event: str | None = None
    snapshot: Callable[[], Any] | None = field(default=None, compare=False)


async def run_snapshot(snapshot: Callable[[], Any]) -> Any:
    """Call a provider's snapshot function and await the result when it is async."""
    data = snapshot()
    if inspect.isawaitable(data):
        data = await data
    return data


@dataclass(frozen=True)
class Route:
    """One page a plugin serves under its own prefix."""

    owner: str
    path: str
    subpath: str
    handler: Callable[..., Any]
    title: str
    columns: tuple[Column, ...] | None = None
    listed: bool = True
    provider: Provider | None = None


class ProviderListeners:
    """The internal interface that is told when a provider's data changed.

    A listener is a function taking the topic. Nothing here is saved on a reload.
    """

    def __init__(self) -> None:
        self._listeners: list[Callable[[str], None]] = []

    def add(self, listener: Callable[[str], None]) -> None:
        """Add a listener; adding the same one again does nothing."""
        if listener not in self._listeners:
            self._listeners.append(listener)

    def remove(self, listener: Callable[[str], None]) -> None:
        """Remove a listener; an unknown one is ignored."""
        if listener in self._listeners:
            self._listeners.remove(listener)

    def notify(self, topic: str) -> None:
        """Tell every listener that the topic changed; a raising listener is logged and skipped."""
        for listener in list(self._listeners):
            try:
                listener(topic)
            except Exception:
                get_logger(LOGGER_NAME).error(
                    "a provider listener failed for %s", topic, exc_info=True
                )


TABLE_SNAPSHOT_KEYS = frozenset({"rows", "lines", "unavailable"})


@dataclass(frozen=True)
class TableSnapshot:
    """What a table provider's snapshot returned, checked."""

    rows: Sequence[Sequence[Any]]
    lines: str | list[str]
    unavailable: str | None


def read_table_snapshot(data: Any) -> TableSnapshot:
    """Read a table snapshot: a list of rows, or a mapping of ``rows``, ``lines``, ``unavailable``.

    Raises:
        ValueError: The mapping has an unknown key, a bad ``lines`` or ``unavailable``, or
            neither ``rows`` nor ``unavailable``; or the rows are not a list.

    """
    if not isinstance(data, Mapping):
        return TableSnapshot(data, "", None)
    unknown = sorted(str(key) for key in data if key not in TABLE_SNAPSHOT_KEYS)
    if unknown:
        msg = f"unknown table snapshot keys {unknown}: use {sorted(TABLE_SNAPSHOT_KEYS)}"
        raise ValueError(msg)
    unavailable = data.get("unavailable")
    if unavailable is not None and (not isinstance(unavailable, str) or not unavailable):
        msg = "unavailable must be a non-empty string"
        raise ValueError(msg)
    lines = data.get("lines", "")
    if not isinstance(lines, str) and not (
        isinstance(lines, list) and all(isinstance(line, str) for line in lines)
    ):
        msg = "lines must be a string or a list of strings"
        raise ValueError(msg)
    rows = data.get("rows")
    if rows is None and unavailable is None:
        msg = "a table snapshot mapping needs rows or unavailable"
        raise ValueError(msg)
    if rows is None:
        rows = []
    if isinstance(rows, str | bytes) or not isinstance(rows, Sequence):
        msg = "rows must be a list of rows"
        raise ValueError(msg)
    return TableSnapshot(rows, lines, unavailable)


def socket_fields(provider: Provider, data: Any) -> dict[str, Any]:
    """The payload fields of a socket ``snapshot`` or ``update`` for a provider's data.

    A table snapshot that is unavailable gives ``data`` null and the ``unavailable`` message.

    Raises:
        ValueError: A table snapshot mapping is malformed.

    """
    if provider.kind == "table" and isinstance(data, Mapping):
        snapshot = read_table_snapshot(data)
        if snapshot.unavailable is not None:
            return {"data": None, "unavailable": snapshot.unavailable}
    return {"data": data}


def _colour_indexes(
    columns: tuple[Column, ...], declared: Sequence[Mapping[str, Any]]
) -> frozenset[int]:
    """The indexes of the columns declared with ``colour: True``.

    Raises:
        ValueError: ``colour`` is not a bool, or is set on a column that is not text.

    """
    found: set[int] = set()
    for position, (column, item) in enumerate(zip(columns, declared, strict=True)):
        colour = item.get("colour", False)
        if not isinstance(colour, bool):
            msg = f"column {column.name!r}: colour must be true or false"
            raise ValueError(msg)
        if colour:
            if column.type != "text":
                msg = f"column {column.name!r}: colour needs a text column"
                raise ValueError(msg)
            found.add(position)
    return frozenset(found)


def _provider_handler(
    snapshot: Callable[[], Any],
    kind: str,
    title: str,
    columns: tuple[Column, ...] | None,
    escape: Callable[[str], str],
    *,
    raw: frozenset[int] = frozenset(),
) -> Callable[[Request], Any]:
    """Build the route handler that serves a provider's snapshot."""

    async def handler(request: Request) -> dict[str, Any]:
        data = await run_snapshot(snapshot)
        if kind == "table" and columns is not None and request.table is not None:
            read = read_table_snapshot(data)
            if read.unavailable is not None:
                intro = (
                    read.lines if isinstance(read.lines, list) else [read.lines] * bool(read.lines)
                )
                return {"kind": "html", "title": title, "lines": [*intro, read.unavailable]}
            page, total = page_rows(read.rows, columns, request.table)
            result: dict[str, Any] = {
                "kind": "table",
                "title": title,
                "rows": escape_cells(page, escape, raw=raw),
                "total": total,
            }
            if isinstance(data, Mapping):
                result["lines"] = read.lines
            return result
        return {"kind": "json", "data": data}

    return handler


class RouteTable:
    """The routes of all plugins, keyed by the url path."""

    def __init__(self) -> None:
        self._routes: dict[str, Route] = {}

    @staticmethod
    def prefix_for(owner: str) -> str:
        """The url prefix of a plugin id: ``plugins.aardwolf.mapper`` gives ``aardwolf/mapper``."""
        return owner.removeprefix("plugins.").replace(".", "/")

    def add(
        self,
        owner: str,
        subpath: str,
        handler: Callable[..., Any],
        title: str,
        columns: Sequence[Mapping[str, Any]] | None = None,
        *,
        listed: bool = True,
    ) -> str:
        """Add a route and return its path.

        A route added with ``listed=False`` is served as usual but left out of the index.

        Raises:
            ValueError: The subpath is invalid, the first segment is reserved, another
                owner already serves the path, or the columns are invalid.

        """
        declared = make_columns(columns) if columns is not None else None
        path = self._claim(owner, subpath, provider=False)
        self._routes[path] = Route(owner, path, subpath, handler, title, declared, listed)
        return path

    def _claim(self, owner: str, subpath: str, *, provider: bool) -> str:
        """Validate a subpath for an owner and return the url path it would be served at.

        Raises:
            ValueError: The subpath is invalid, the first segment is reserved, another
                owner already serves the path. A provider is served under ``/data``, so a route
        and a provider of one name never meet.

        """
        if subpath and not SUBPATH_RE.fullmatch(subpath):
            msg = f"invalid subpath {subpath!r}: use lower case letters, digits, _ and -"
            raise ValueError(msg)
        prefix = self.prefix_for(owner)
        if not prefix or prefix.split("/", 1)[0] in RESERVED_SEGMENTS:
            msg = f"the prefix {prefix!r} starts with a reserved segment"
            raise ValueError(msg)
        path = f"/{prefix}/{subpath}" if subpath else f"/{prefix}"
        if provider:
            path = f"/{DATA_SEGMENT}{path}"
        existing = self._routes.get(path)
        if existing is not None and existing.owner != owner:
            msg = f"{path} is already served by {existing.owner}"
            raise ValueError(msg)
        return path

    def add_provider(
        self,
        owner: str,
        name: str,
        snapshot: Callable[[], Any],
        columns: Sequence[Mapping[str, Any]] | None,
        kind: str,
        event: str | None,
        escape: Callable[[str], str],
        *,
        title: object = None,
    ) -> str:
        """Add a data provider served at ``/data/<prefix>/<name>`` and return its topic.

        The topic is the path without the leading ``/data/``, with ``.`` for ``/``. A ``json``
        provider serves what ``snapshot`` returns; a ``table`` provider serves the rows
        ``snapshot`` returns (lists of cells, one per column), filtered, sorted and paged, or a
        mapping of ``rows``, ``lines`` (shown above the table) and ``unavailable`` (a message
        shown in place of the table). ``title`` is the heading and the index entry; it defaults
        to the topic. A column dict with ``colour: True`` keeps the colour codes of its text.

        Raises:
            ValueError: The name is empty or invalid, the kind is unknown, columns are
                missing for a table or given for json, the title is not text, a column
                colour is invalid, or the path is taken.

        """
        if title is not None and not isinstance(title, str):
            msg = "a provider title must be text"
            raise ValueError(msg)
        if not name:
            msg = "a provider needs a name"
            raise ValueError(msg)
        if kind not in PROVIDER_KINDS:
            msg = f"unknown provider kind {kind!r}: use one of {PROVIDER_KINDS}"
            raise ValueError(msg)
        if kind == "table" and not columns:
            msg = "a table provider needs columns"
            raise ValueError(msg)
        if kind == "json" and columns is not None:
            msg = "a json provider takes no columns"
            raise ValueError(msg)
        declared = make_columns(columns) if columns is not None else None
        path = self._claim(owner, name, provider=True)
        topic = path.removeprefix(f"/{DATA_SEGMENT}/").replace("/", ".")
        shown = title or topic
        raw = (
            _colour_indexes(declared, columns) if declared is not None and columns else frozenset()
        )
        handler = _provider_handler(snapshot, kind, shown, declared, escape, raw=raw)
        provider = Provider(name, topic, kind, event, snapshot)
        self._routes[path] = Route(owner, path, name, handler, shown, declared, True, provider)
        return topic

    def providers(self) -> list[Route]:
        """Every provider route, sorted by topic."""
        found = [r for r in self._routes.values() if r.provider is not None]
        return sorted(found, key=lambda r: r.path)

    def topics(self) -> list[str]:
        """The topics of all providers, sorted."""
        return [r.provider.topic for r in self.providers() if r.provider]

    def provider_for_topic(self, topic: str) -> Route | None:
        """Return the provider route of a topic, or None (a plain route is not a provider)."""
        route = self._routes.get(f"/{DATA_SEGMENT}/" + topic.replace(".", "/"))
        if route is not None and route.provider is not None and route.provider.topic == topic:
            return route
        return None

    def provider(self, owner: str, name: str) -> Route | None:
        """Return the provider route an owner registered under a name."""
        for route in self.providers():
            if route.owner == owner and route.provider is not None and route.provider.name == name:
                return route
        return None

    def provider_events(self) -> set[str]:
        """The events providers asked to follow."""
        return {r.provider.event for r in self.providers() if r.provider and r.provider.event}

    def topics_for_event(self, event: str) -> list[str]:
        """The topics of the providers that follow an event."""
        return [
            r.provider.topic for r in self.providers() if r.provider and r.provider.event == event
        ]

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
        """The routes grouped by owner, each list pages first, then providers, by path."""
        grouped: dict[str, list[Route]] = {}
        for route in sorted(self._routes.values(), key=lambda r: (r.provider is not None, r.path)):
            grouped.setdefault(route.owner, []).append(route)
        return grouped

    def pages_by_owner(self) -> dict[str, list[Route]]:
        """The plain routes (not providers) by owner, by path; owners with none are left out."""
        grouped: dict[str, list[Route]] = {}
        for route in sorted(self._routes.values(), key=lambda r: r.path):
            if route.provider is None:
                grouped.setdefault(route.owner, []).append(route)
        return grouped

    def providers_by_owner(self) -> dict[str, list[Route]]:
        """The providers grouped by owner, by topic; owners with none are left out."""
        grouped: dict[str, list[Route]] = {}
        for route in sorted(self.providers(), key=lambda r: r.provider.topic if r.provider else ""):
            grouped.setdefault(route.owner, []).append(route)
        return grouped

    def count(self) -> int:
        """Return the number of plain routes, not counting data providers."""
        return sum(1 for r in self._routes.values() if r.provider is None)

    def provider_count(self) -> int:
        """Return the number of data providers."""
        return sum(1 for r in self._routes.values() if r.provider is not None)

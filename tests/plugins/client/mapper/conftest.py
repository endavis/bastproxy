"""Fixtures for the mapper tests: a shared test map and a stand-in plugin."""

import asyncio
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from bastproxy.plugins.client.mapper.libs._graph import Exit, MapGraph
from bastproxy.plugins.client.mapper.libs._schema import TABLES
from bastproxy.plugins.client.mapper.libs._store import MapStore
from bastproxy.plugins.client.mapper.libs._walk import Walk
from bastproxy.plugins.client.mapper.plugin import _mapper as mapper_module
from bastproxy.plugins.client.mapper.plugin._mapper import MapperPlugin
from bastproxy.plugins.core.sqldb.libs._sqlite import create_database

OWNER = "plugins.client.mapper"


class FakeApi:
    """A stand-in for the plugin api: callable over a table of functions."""

    def __init__(self, table: dict[str, Callable[..., Any]]) -> None:
        self.table = table

    def __call__(self, name: str) -> Callable[..., Any]:
        return self.table[name]


class Harness:
    """The plugin plus what it raised and sent."""

    def __init__(self, plugin: Any) -> None:
        self.plugin = plugin
        self.events: list[tuple[str, dict[str, Any]]] = []
        self.mud: list[str] = []
        self.client: list[Any] = []
        self.settings: dict[str, Any] = {"maxdepth": 300, "shownotes": True, "reroute": True}
        self.args: dict[str, Any] = {}
        self.tasks: list[asyncio.Task[Any]] = []

    def names(self) -> list[str]:
        """Return the short names of the raised events."""
        return [name.removeprefix("ev_plugins.client.mapper_") for name, _ in self.events]

    def event(self, short: str) -> dict[str, Any]:
        """Return the args of the last event with this short name."""
        return next(a for n, a in reversed(self.events) if n.endswith(f"_{short}"))


def build_map(plugin: Any) -> None:
    """Fill the plugin with the test map described in the plan."""
    for uid in "ABCDEF":
        flags = ["noportal"] if uid == "B" else []
        plugin._api_room_add({"uid": uid, "name": f"Room {uid}", "area": "test", "flags": flags})
    add = plugin._api_exit_add
    add("A", "n", "B")
    add("B", "n", "C")
    add("A", "enter portal", "C", 5)
    add("C", "e", "D")
    add("D", "e", "E", 1, {"level": 50})
    add("A", "s", "E", 10)
    add("*", "portal f", "F")
    add("**", "recall", "A")
    add("E", "w", "-1")
    plugin._api_exit_add("F", "up", "-1")


@pytest.fixture
def harness(tmp_path: Path) -> Iterator[Harness]:
    """A MapperPlugin on a real database, with stub APIs and recorded sends."""
    plugin: Any = object.__new__(MapperPlugin)
    plugin.plugin_id = OWNER
    plugin.current_room = None
    plugin.walk = Walk()
    plugin.requirement_callbacks = {}
    plugin._search_token = 0
    plugin._unload_token = 0
    plugin.movement_callbacks = {}
    plugin.mismatches = {}
    db = create_database(OWNER, "map", TABLES, directory=tmp_path)
    plugin.store = MapStore(db)
    plugin.graph = MapGraph()
    h = Harness(plugin)

    def raise_event(name: str, event_args: dict[str, Any] | None = None) -> None:
        h.events.append((name, dict(event_args or {})))

    def add_task(coro: Any, _name: str = "") -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(coro)
            return
        h.tasks.append(loop.create_task(coro))

    plugin.api = FakeApi(
        {
            "libs.asynch:task.add": add_task,
            "plugins.core.events:event.raise": raise_event,
            "plugins.core.settings:setting.get": lambda _pid, name: h.settings[name],
            "plugins.core.commands:command.current.args.get": lambda: h.args,
            "plugins.core.colors:colorcode.escape": lambda s: s.replace("@", "@@"),
            "plugins.core.events:event.current.record.get": lambda: None,
        }
    )

    def send_mud(message: Any, *_a: Any, **_k: Any) -> MagicMock:
        h.mud.append(message.data if hasattr(message, "data") else message)
        return MagicMock()

    def send_client(message: Any, *_a: Any, **_k: Any) -> MagicMock:
        h.client.append(message)
        return MagicMock()

    with (
        patch.object(mapper_module, "SendDataDirectlyToMud", side_effect=send_mud),
        patch.object(mapper_module, "SendDataDirectlyToClient", side_effect=send_client),
        patch.object(mapper_module, "NetworkData", side_effect=lambda data, **_k: data),
    ):
        yield h
    db.close()


@pytest.fixture
def test_map(harness: Harness) -> Harness:
    """The harness with the shared test map loaded."""
    build_map(harness.plugin)
    harness.events.clear()
    return harness


def exits_of(graph: MapGraph, uid: str) -> list[Exit]:
    """Return the exits of a room sorted by direction."""
    return sorted(graph.exits_from(uid), key=lambda e: e.dir)

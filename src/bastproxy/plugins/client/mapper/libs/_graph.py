# Project: bastproxy
# Filename: plugins/client/mapper/libs/_graph.py
#
# File Description: the in-memory map graph and the pathfinder
#
# By: Bast
"""The in-memory map graph and Dijkstra pathfinding (ADR-0021).

This module imports nothing from bastproxy, so it is tested on its own.
"""

import heapq
import itertools
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any

from ._schema import (
    ANYWHERE_UID,
    NOPORTAL_FLAG,
    NORECALL_FLAG,
    RECALL_UID,
    UNKNOWN_UID,
)


@dataclass(frozen=True)
class Exit:
    """An exit from a room, or from the virtual rooms ``*`` and ``**``."""

    fromuid: str
    dir: str
    touid: str = UNKNOWN_UID
    cost: int = 1
    requirement: Any = None

    def to_dict(self) -> dict[str, Any]:
        """Return the exit as a plain dict."""
        return {
            "fromuid": self.fromuid,
            "touid": self.touid,
            "dir": self.dir,
            "cost": self.cost,
            "requirement": self.requirement,
        }


@dataclass
class PathResult:
    """A found path: its total cost and the exits to take."""

    cost: int
    steps: list[Exit] = field(default_factory=list)


class MapGraph:
    """Rooms with flags and the exits between them, kept in memory."""

    def __init__(self) -> None:
        """Initialize an empty graph."""
        self._flags: dict[str, frozenset[str]] = {}
        self._exits: dict[str, dict[str, Exit]] = {}

    def set_room(self, uid: str, flags: Iterable[str] = ()) -> None:
        """Add a room or replace its flags."""
        self._flags[uid] = frozenset(flags)

    def room_flags(self, uid: str) -> frozenset[str]:
        """Return the flags of a room, empty for an unknown room."""
        return self._flags.get(uid, frozenset())

    def has_room(self, uid: str) -> bool:
        """Check if a room is in the graph."""
        return uid in self._flags

    def remove_room(self, uid: str) -> None:
        """Remove a room and every exit from and to it."""
        self._flags.pop(uid, None)
        self._exits.pop(uid, None)
        for exits in self._exits.values():
            for direction in [d for d, e in exits.items() if e.touid == uid]:
                del exits[direction]

    def set_exit(self, exit_: Exit) -> None:
        """Add an exit or replace the exit with the same room and direction."""
        self._exits.setdefault(exit_.fromuid, {})[exit_.dir] = exit_

    def remove_exit(self, fromuid: str, direction: str) -> None:
        """Remove an exit if it exists."""
        self._exits.get(fromuid, {}).pop(direction, None)

    def exits_from(self, uid: str) -> list[Exit]:
        """Return the exits stored for a room, not counting exits from anywhere."""
        return list(self._exits.get(uid, {}).values())

    def edges(self, uid: str) -> Iterator[Exit]:
        """Yield the exits a character in ``uid`` can take, with the exits from anywhere.

        A ``noportal`` room blocks the ``*`` exits and a ``norecall`` room blocks the
        ``**`` exits. The uid does not have to be a known room.
        """
        yield from self.exits_from(uid)
        flags = self.room_flags(uid)
        if NOPORTAL_FLAG not in flags:
            yield from self.exits_from(ANYWHERE_UID)
        if NORECALL_FLAG not in flags:
            yield from self.exits_from(RECALL_UID)

    def snapshot(self) -> dict[str, Any]:
        """Return a comparable copy of the graph, used by tests."""
        return {
            "rooms": dict(self._flags),
            "exits": {u: dict(e) for u, e in self._exits.items() if e},
        }


def find_path(
    graph: MapGraph,
    start: str,
    target: str,
    *,
    max_depth: int,
    allowed: Callable[[Exit], bool],
) -> PathResult | None:
    """Find the cheapest path from ``start`` to ``target``.

    Ties on cost go to the path with fewer steps. A relaxation that would make a path
    longer than ``max_depth`` steps is dropped, so a target whose cheapest route is
    longer than the limit is unreachable even when a costlier, shorter route exists.
    Exits to an unexplored room and exits ``allowed`` rejects are never used.
    """
    if start == target:
        return PathResult(0, [])
    counter = itertools.count()
    best: dict[str, int] = {start: 0}
    came: dict[str, tuple[str, Exit]] = {}
    heap: list[tuple[int, int, int, str]] = [(0, 0, next(counter), start)]
    while heap:
        cost, steps, _tie, uid = heapq.heappop(heap)
        if cost > best.get(uid, cost):
            continue
        if uid == target:
            path: list[Exit] = []
            node = target
            while node != start:
                node, exit_ = came[node]
                path.append(exit_)
            path.reverse()
            return PathResult(cost, path)
        if steps + 1 > max_depth:
            continue
        for exit_ in graph.edges(uid):
            if exit_.touid == UNKNOWN_UID or not allowed(exit_):
                continue
            new_cost = cost + exit_.cost
            if exit_.touid not in best or new_cost < best[exit_.touid]:
                best[exit_.touid] = new_cost
                came[exit_.touid] = (uid, exit_)
                heapq.heappush(heap, (new_cost, steps + 1, next(counter), exit_.touid))
    return None

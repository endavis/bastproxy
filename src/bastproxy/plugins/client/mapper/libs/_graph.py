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
import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from ._schema import (
    ANYWHERE_UID,
    NOPORTAL_FLAG,
    NORECALL_FLAG,
    PLAIN_DIRECTIONS,
    RECALL_UID,
    SHORT_DIRECTIONS,
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


def requirement_key(requirement: Any) -> str:
    """Return a stable string for a requirement, the same whatever its dict key order."""
    return json.dumps(requirement, sort_keys=True)


@dataclass
class PathResult:
    """A found path: its total cost and the exits to take."""

    cost: int
    steps: list[Exit] = field(default_factory=list)


class MapGraph:
    """Rooms with flags and the exits between them, kept in memory.

    ``freeze`` hands out a view that a worker thread can read while the graph keeps
    changing: the view shares the outer dicts and the next write copies them first
    (copy-on-write). The per-room exit dicts are replaced on a write, never mutated,
    so a shared outer dict never changes under a reader.
    """

    def __init__(self) -> None:
        """Initialize an empty graph."""
        self._flags: dict[str, frozenset[str]] = {}
        self._exits: dict[str, dict[str, Exit]] = {}
        self._shared = False
        self._requirements: dict[str, Exit] = {}

    def _unshare(self) -> None:
        """Copy the outer dicts when a frozen view shares them."""
        if self._shared:
            self._flags = dict(self._flags)
            self._exits = dict(self._exits)
            self._shared = False

    def freeze(self) -> "MapGraph":
        """Return a view of the graph as it is now that no later write changes."""
        view = object.__new__(MapGraph)
        view._flags = self._flags
        view._exits = self._exits
        view._shared = True
        view._requirements = dict(self._requirements)
        self._shared = True
        return view

    def requirements(self) -> dict[str, Exit]:
        """Return a sample exit for every distinct requirement ever set, by key."""
        return dict(self._requirements)

    def set_room(self, uid: str, flags: Iterable[str] = ()) -> None:
        """Add a room or replace its flags."""
        self._unshare()
        self._flags[uid] = frozenset(flags)

    def room_flags(self, uid: str) -> frozenset[str]:
        """Return the flags of a room, empty for an unknown room."""
        return self._flags.get(uid, frozenset())

    def has_room(self, uid: str) -> bool:
        """Check if a room is in the graph."""
        return uid in self._flags

    def remove_room(self, uid: str) -> None:
        """Remove a room and every exit from and to it."""
        self._unshare()
        self._flags.pop(uid, None)
        self._exits.pop(uid, None)
        replacements: dict[str, dict[str, Exit]] = {}
        for fromuid, exits in self._exits.items():
            if any(e.touid == uid for e in exits.values()):
                replacements[fromuid] = {d: e for d, e in exits.items() if e.touid != uid}
        self._exits.update(replacements)

    def set_exit(self, exit_: Exit) -> None:
        """Add an exit or replace the exit with the same room and direction."""
        self._unshare()
        inner = dict(self._exits.get(exit_.fromuid, {}))
        inner[exit_.dir] = exit_
        self._exits[exit_.fromuid] = inner
        if exit_.requirement is not None:
            self._requirements.setdefault(requirement_key(exit_.requirement), exit_)

    def remove_exit(self, fromuid: str, direction: str) -> None:
        """Remove an exit if it exists."""
        self._unshare()
        if direction in self._exits.get(fromuid, {}):
            inner = dict(self._exits[fromuid])
            del inner[direction]
            self._exits[fromuid] = inner

    def exits_from(self, uid: str) -> list[Exit]:
        """Return the exits stored for a room, not counting exits from anywhere."""
        return list(self._exits.get(uid, {}).values())

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
    portals: bool = True,
    recalls: bool = True,
) -> PathResult | None:
    """Find the cheapest path from ``start`` to ``target``.

    Ties on cost go to the path with fewer steps. A relaxation that would make a path
    longer than ``max_depth`` steps is dropped, so a target whose cheapest route is
    longer than the limit is unreachable even when a costlier, shorter route exists.
    Exits to an unexplored room and exits ``allowed`` rejects are never used.
    A ``noportal`` room cannot take the ``*`` exits and a ``norecall`` room cannot
    take the ``**`` exits; the start does not have to be a known room.
    With ``portals`` false the exits from ``*`` are never used, and with ``recalls``
    false the exits from ``**`` are never used.
    """
    if start == target:
        return PathResult(0, [])
    counter = itertools.count()
    best: dict[str, int] = {start: 0}
    came: dict[str, tuple[str, Exit]] = {}
    heap: list[tuple[int, int, int, str]] = [(0, 0, next(counter), start)]
    portals_done = False
    recall_done = False
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
        flags = graph.room_flags(uid)
        candidates = graph.exits_from(uid)
        # The exits from anywhere lead to the same rooms from every room, and rooms
        # come off the heap cheapest first, so only the first room that may use them
        # can improve a cost. Relax them once per search, not once per room.
        if portals and not portals_done and NOPORTAL_FLAG not in flags:
            portals_done = True
            candidates += graph.exits_from(ANYWHERE_UID)
        if recalls and not recall_done and NORECALL_FLAG not in flags:
            recall_done = True
            candidates += graph.exits_from(RECALL_UID)
        for exit_ in candidates:
            if exit_.touid == UNKNOWN_UID or not allowed(exit_):
                continue
            new_cost = cost + exit_.cost
            if exit_.touid not in best or new_cost < best[exit_.touid]:
                best[exit_.touid] = new_cost
                came[exit_.touid] = (uid, exit_)
                heapq.heappush(heap, (new_cost, steps + 1, next(counter), exit_.touid))
    return None


def speedwalk(steps: Iterable[Exit] | list[str], separator: str) -> str:
    """Compress a path into a speedwalk string such as ``3n2e``.

    ``steps`` are exits or direction strings. Consecutive plain directions become runs
    of a count and a short direction (a single step stays bare) written together. A
    custom exit is its own segment. Segments are joined with ``separator``, so the line
    can be typed back as separate commands. An empty path gives ``""``.
    """
    segments: list[str] = []
    plain = ""
    run_dir = ""
    run_count = 0

    def end_run() -> None:
        nonlocal plain, run_dir, run_count
        if run_count:
            plain += f"{run_count}{run_dir}" if run_count > 1 else run_dir
        run_dir = ""
        run_count = 0

    def end_plain() -> None:
        nonlocal plain
        end_run()
        if plain:
            segments.append(plain)
        plain = ""

    for step in steps:
        direction = step if isinstance(step, str) else step.dir
        if direction in PLAIN_DIRECTIONS:
            short = SHORT_DIRECTIONS.get(direction, direction)
            if short != run_dir:
                end_run()
                run_dir = short
            run_count += 1
        else:
            end_plain()
            segments.append(direction)
    end_plain()
    return separator.join(segments)

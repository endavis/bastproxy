# Project: bastproxy
# Filename: plugins/client/mapper/libs/_batch.py
#
# File Description: the merge and validation rules of a batch write
#
# By: Bast
"""The merge and validation rules of a batch write (ADR-0021).

This module imports nothing from bastproxy, so it is tested on its own.
"""

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from ._graph import Exit
from ._schema import UNKNOWN_UID

# the most rows one map.batch.add call accepts: areas, rooms, exits (embedded ones
# included) and notes. One call is one transaction, so this caps how long it blocks.
BATCH_LIMIT = 1000

BAD_EXIT = "bad"
BAD_REQUIREMENT = "requirement"


@dataclass
class BatchResult:
    """What a batch wrote: counts, the final room flags and the final exits."""

    areas: int = 0
    rooms: int = 0
    new_rooms: int = 0
    exits: int = 0
    new_exits: int = 0
    notes: int = 0
    skipped: int = 0
    room_flags: dict[str, list[str]] = field(default_factory=dict)
    written_exits: list[Exit] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        """Return the counts as a plain dict."""
        return {
            "areas": self.areas,
            "rooms": self.rooms,
            "new_rooms": self.new_rooms,
            "exits": self.exits,
            "new_exits": self.new_exits,
            "notes": self.notes,
            "skipped": self.skipped,
        }

    def changed(self) -> bool:
        """Return True when at least one row was written."""
        return bool(self.areas or self.rooms or self.exits or self.notes)


def exit_problem(fromuid: Any, dir: str, cost: Any, requirement: Any) -> str | None:
    """Return BAD_EXIT or BAD_REQUIREMENT when an exit is invalid, else None."""
    if not fromuid or not dir or not isinstance(cost, int) or cost < 0:
        return BAD_EXIT
    try:
        json.dumps(requirement)
    except (TypeError, ValueError):
        return BAD_REQUIREMENT
    return None


def normalize_room(room: Any) -> dict[str, Any] | None:
    """Return the room as a row dict with a string uid, or None when it has no uid."""
    uid = room.get("uid") if isinstance(room, Mapping) else None
    if uid is None or str(uid) == "":
        return None
    return {
        "uid": str(uid),
        "name": room.get("name", ""),
        "area": room.get("area", ""),
        "terrain": room.get("terrain", ""),
        "x": room.get("x", 0),
        "y": room.get("y", 0),
        "z": room.get("z", 0),
        "flags": list(room.get("flags", [])),
        "details": dict(room.get("details", {})),
    }


def merge_room(
    stored: Mapping[str, Any] | None, given: Mapping[str, Any], overwrite: bool
) -> dict[str, Any] | None:
    """Return the room row to write, or None when nothing changes.

    ``given`` is a normalized room. With ``overwrite`` it replaces the stored room.
    Without, a stored room keeps every field and gains only the flags it lacks.
    """
    if stored is None:
        return dict(given)
    if overwrite:
        merged = dict(given)
        return None if merged == dict(stored) else merged
    missing = [f for f in given["flags"] if f not in stored["flags"]]
    if not missing:
        return None
    merged = dict(stored)
    merged["flags"] = [*stored["flags"], *dict.fromkeys(missing)]
    return merged


def merge_exit(
    stored: Exit | None, given: Exit, overwrite: bool, *, keep_details: bool = False
) -> Exit | None:
    """Return the exit to write, or None when nothing changes.

    An unexplored touid never replaces a known one. With ``overwrite`` the given cost
    and requirement replace the stored ones. Without, the stored cost is kept, an
    unexplored touid is filled and a missing requirement is filled. With
    ``keep_details`` (an exit embedded in a room, as ``room.add`` does) and
    ``overwrite``, a stored exit keeps its cost and requirement and only its touid
    is updated.
    """
    if stored is None:
        return given
    if overwrite and keep_details:
        touid = stored.touid if given.touid == UNKNOWN_UID else given.touid
        merged = Exit(stored.fromuid, stored.dir, touid, stored.cost, stored.requirement)
    elif overwrite:
        touid = stored.touid if given.touid == UNKNOWN_UID else given.touid
        merged = Exit(given.fromuid, given.dir, touid, given.cost, given.requirement)
    else:
        touid = given.touid if stored.touid == UNKNOWN_UID else stored.touid
        requirement = given.requirement if stored.requirement is None else stored.requirement
        merged = Exit(stored.fromuid, stored.dir, touid, stored.cost, requirement)
    return None if merged == stored else merged


def count_rows(
    areas: Iterable[Any] | None,
    rooms: Iterable[Any] | None,
    exits: Iterable[Any] | None,
    notes: Mapping[Any, Any] | None,
) -> int:
    """Count the rows of a batch: embedded room exits count as exits."""
    total = len(list(areas or ())) + len(list(exits or ())) + len(notes or {})
    for room in rooms or ():
        total += 1
        if isinstance(room, Mapping):
            total += len(room.get("exits") or {})
    return total

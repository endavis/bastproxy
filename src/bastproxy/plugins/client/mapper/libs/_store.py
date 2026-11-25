# Project: bastproxy
# Filename: plugins/client/mapper/libs/_store.py
#
# File Description: reads and writes the map database
#
# By: Bast
"""Reads and writes the map database (ADR-0021).

``MapStore`` is duck-typed on the ``select`` and ``modify`` methods of the sqldb
``Sqldb`` class, so this module never imports the sqldb plugin. Every value goes in
through bound parameters.
"""

import json
from collections.abc import Iterable, Mapping, Sequence
from contextlib import AbstractContextManager
from typing import Any, Protocol

from ._batch import BatchResult, exit_problem, merge_exit, merge_room, normalize_room
from ._graph import Exit, MapGraph
from ._schema import INDEX_SQL, UNKNOWN_UID


class Database(Protocol):
    """The two methods of ``Sqldb`` the store uses."""

    def select(
        self, sql_statement: str, params: Sequence[Any] | Mapping[str, Any] = ()
    ) -> list[dict[str, Any]]:
        """Run a select statement."""
        ...

    def modify(self, sql_statement: str, data: Any = None) -> tuple[int | None, Any]:
        """Run a statement that changes the database."""
        ...

    def modifymany(self, sql_statement: str, data: Any = None) -> tuple[int | None, Any]:
        """Run a statement for many rows, all or none."""
        ...

    def transaction(self) -> AbstractContextManager[None]:
        """Run several statements in one commit."""
        ...


UPSERT_EXIT_SQL = (
    "INSERT INTO exits(fromuid, dir, touid, cost, requirement) VALUES(?, ?, ?, ?, ?) "
    "ON CONFLICT(fromuid, dir) DO UPDATE SET "
    "touid = CASE WHEN excluded.touid = '-1' THEN exits.touid ELSE excluded.touid END, "
    "cost = excluded.cost, requirement = excluded.requirement"
)
UPSERT_EXIT_KEEP_SQL = (
    "INSERT INTO exits(fromuid, dir, touid, cost, requirement) VALUES(?, ?, ?, ?, ?) "
    "ON CONFLICT(fromuid, dir) DO UPDATE SET "
    "touid = CASE WHEN excluded.touid = '-1' THEN exits.touid ELSE excluded.touid END"
)
UPSERT_ROOM_SQL = (
    "INSERT OR REPLACE INTO rooms(uid, name, area, terrain, x, y, z, flags, details) "
    "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)"
)
SELECT_CHUNK = 500


def _select_in(db: Database, sql: str, values: Sequence[str]) -> list[dict[str, Any]]:
    """Run ``sql`` (with one ``{marks}`` placeholder list) for ``values``, in chunks."""
    rows: list[dict[str, Any]] = []
    for start in range(0, len(values), SELECT_CHUNK):
        chunk = values[start : start + SELECT_CHUNK]
        rows.extend(db.select(sql.format(marks=", ".join("?" * len(chunk))), chunk))
    return rows


def _like(text: str) -> str:
    """Escape ``text`` for a LIKE pattern that uses ``ESCAPE '\\'``."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _row_to_exit(row: Mapping[str, Any]) -> Exit:
    """Build an Exit from an exits row."""
    requirement = json.loads(row["requirement"]) if row["requirement"] is not None else None
    return Exit(row["fromuid"], row["dir"], row["touid"], row["cost"], requirement)


def _row_to_room(row: Mapping[str, Any]) -> dict[str, Any]:
    """Build a room dict from a rooms row."""
    room = dict(row)
    room["flags"] = json.loads(room["flags"] or "[]")
    room["details"] = json.loads(room["details"] or "{}")
    return room


def room_differences(
    stored_room: Mapping[str, Any] | None,
    stored_exits: Iterable[Exit],
    update: Mapping[str, Any],
) -> dict[str, Any]:
    """Compare a room update with what is stored.

    Returns a dict with ``area`` as ``(old, new)`` when the room moved to another area,
    and ``exits`` as ``{direction: (old touid, new touid)}`` for an exit whose known
    touid differs, or a direction present on one side only (``None`` for the missing
    side). An unexplored touid (``-1``) on either side is never a difference. Exits
    are only compared when the update has an ``exits`` key. A room that is not stored
    has no differences.
    """
    differences: dict[str, Any] = {}
    if stored_room is None:
        return differences
    if "area" in update and update["area"] != stored_room.get("area"):
        differences["area"] = (stored_room.get("area"), update["area"])
    if "exits" in update:
        stored = {exit_.dir: exit_.touid for exit_ in stored_exits}
        given = {str(d): str(t) for d, t in update["exits"].items()}
        exits: dict[str, tuple[str | None, str | None]] = {}
        for direction, touid in given.items():
            if direction not in stored:
                exits[direction] = (None, touid)
            elif UNKNOWN_UID not in (stored[direction], touid) and stored[direction] != touid:
                exits[direction] = (stored[direction], touid)
        for direction, touid in stored.items():
            if direction not in given:
                exits[direction] = (touid, None)
        if exits:
            differences["exits"] = exits
    return differences


class MapStore:
    """Rooms, areas, exits and notes in the map database."""

    def __init__(self, db: Database) -> None:
        """Initialize the store and make sure the indexes exist."""
        self.db = db
        for statement in INDEX_SQL:
            self.db.modify(statement)

    # areas
    def add_area(
        self, uid: str, name: str, flags: Iterable[str], details: Mapping[str, Any]
    ) -> None:
        """Add an area or replace it."""
        self.db.modify(
            "INSERT OR REPLACE INTO areas(uid, name, flags, details) VALUES(?, ?, ?, ?)",
            (uid, name, json.dumps(list(flags)), json.dumps(dict(details))),
        )

    def get_area(self, uid: str) -> dict[str, Any] | None:
        """Get an area or None."""
        rows = self.db.select("SELECT * FROM areas WHERE uid = ?", (uid,))
        return _row_to_room(rows[0]) if rows else None

    def list_areas(self) -> list[dict[str, Any]]:
        """List all areas by uid."""
        return [_row_to_room(r) for r in self.db.select("SELECT * FROM areas ORDER BY uid")]

    def remove_area(self, uid: str) -> list[str]:
        """Remove an area and its rooms. Returns the uids of the removed rooms."""
        rooms = [r["uid"] for r in self.db.select("SELECT uid FROM rooms WHERE area = ?", (uid,))]
        for room_uid in rooms:
            self.remove_room(room_uid)
        self.db.modify("DELETE FROM areas WHERE uid = ?", (uid,))
        return rooms

    # rooms
    def upsert_room(self, room: Mapping[str, Any]) -> None:
        """Insert a room or replace the stored one."""
        self.db.modify(
            UPSERT_ROOM_SQL,
            (
                room["uid"],
                room.get("name", ""),
                room.get("area", ""),
                room.get("terrain", ""),
                room.get("x", 0),
                room.get("y", 0),
                room.get("z", 0),
                json.dumps(list(room.get("flags", []))),
                json.dumps(dict(room.get("details", {}))),
            ),
        )

    def get_room(self, uid: str) -> dict[str, Any] | None:
        """Get a room without its exits, or None."""
        rows = self.db.select("SELECT * FROM rooms WHERE uid = ?", (uid,))
        return _row_to_room(rows[0]) if rows else None

    def remove_room(self, uid: str) -> bool:
        """Remove a room, the exits from and to it, and its note."""
        exists = self.get_room(uid) is not None
        self.db.modify("DELETE FROM exits WHERE fromuid = ? OR touid = ?", (uid, uid))
        self.db.modify("DELETE FROM bookmarks WHERE uid = ?", (uid,))
        self.db.modify("DELETE FROM rooms WHERE uid = ?", (uid,))
        return exists

    def list_rooms(
        self,
        name: str | None = None,
        area: str | None = None,
        flag: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """List rooms by case-insensitive name part, area and flag."""
        clauses: list[str] = []
        params: list[Any] = []
        if name:
            clauses.append("name LIKE ? ESCAPE '\\'")
            params.append(f"%{_like(name)}%")
        if area:
            clauses.append("area = ?")
            params.append(area)
        sql = "SELECT * FROM rooms"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY uid"
        rooms = [_row_to_room(r) for r in self.db.select(sql, params)]
        if flag:
            rooms = [r for r in rooms if flag in r["flags"]]
        return rooms[:limit] if limit is not None else rooms

    def unexplored(self, area: str | None = None) -> list[dict[str, Any]]:
        """List rooms that have an exit to an unexplored room."""
        sql = "SELECT * FROM rooms WHERE uid IN (SELECT fromuid FROM exits WHERE touid = ?)"
        params: list[Any] = [UNKNOWN_UID]
        if area:
            sql += " AND area = ?"
            params.append(area)
        return [_row_to_room(r) for r in self.db.select(sql + " ORDER BY uid", params)]

    # exits
    def upsert_exit(self, exit_: Exit, *, keep_details: bool = False) -> Exit:
        """Add or update an exit and return the stored one.

        An unexplored touid never overwrites a known one. With ``keep_details`` an
        existing exit keeps its stored cost and requirement and only its touid is
        updated; a new exit still gets the given values.
        """
        self.db.modify(
            UPSERT_EXIT_KEEP_SQL if keep_details else UPSERT_EXIT_SQL,
            (
                exit_.fromuid,
                exit_.dir,
                exit_.touid,
                exit_.cost,
                json.dumps(exit_.requirement) if exit_.requirement is not None else None,
            ),
        )
        stored = self.get_exit(exit_.fromuid, exit_.dir)
        assert stored is not None  # just written
        return stored

    def get_exit(self, fromuid: str, direction: str) -> Exit | None:
        """Get one exit or None."""
        rows = self.db.select(
            "SELECT * FROM exits WHERE fromuid = ? AND dir = ?", (fromuid, direction)
        )
        return _row_to_exit(rows[0]) if rows else None

    def remove_exit(self, fromuid: str, direction: str) -> bool:
        """Remove an exit. Returns True when it existed."""
        existed = self.get_exit(fromuid, direction) is not None
        self.db.modify("DELETE FROM exits WHERE fromuid = ? AND dir = ?", (fromuid, direction))
        return existed

    def exits_from(self, fromuid: str) -> list[Exit]:
        """List the exits stored for a room or ``*``/``**``."""
        rows = self.db.select("SELECT * FROM exits WHERE fromuid = ? ORDER BY dir", (fromuid,))
        return [_row_to_exit(r) for r in rows]

    # notes
    def set_note(self, uid: str, text: str) -> None:
        """Set the note of a room."""
        self.db.modify("INSERT OR REPLACE INTO bookmarks(uid, notes) VALUES(?, ?)", (uid, text))

    def get_note(self, uid: str) -> str | None:
        """Get the note of a room, or None."""
        rows = self.db.select("SELECT notes FROM bookmarks WHERE uid = ?", (uid,))
        return rows[0]["notes"] if rows else None

    def remove_note(self, uid: str) -> bool:
        """Remove a note. Returns True when it existed."""
        existed = self.get_note(uid) is not None
        self.db.modify("DELETE FROM bookmarks WHERE uid = ?", (uid,))
        return existed

    # batches
    def write_batch(
        self,
        areas: Iterable[Any] | None,
        rooms: Iterable[Any] | None,
        exits: Iterable[Any] | None,
        notes: Mapping[Any, Any] | None,
        overwrite: bool,
    ) -> BatchResult:
        """Write areas, rooms, exits and notes in one transaction.

        The stored rows are read once per table, merged in Python in the order areas,
        rooms with their embedded exits, exits, notes, and only the changed rows are
        written. Bad items are skipped and counted. Raises ``sqlite3.Error`` with
        nothing written when a statement fails.
        """
        result = BatchResult()
        raw_rooms = list(rooms or ())
        room_items = [normalize_room(r) for r in raw_rooms]
        area_rows: dict[str, tuple[Any, ...]] = {}
        given_areas: dict[str, tuple[str, str, str]] = {}
        for area in areas or ():
            uid = area.get("uid") if isinstance(area, Mapping) else None
            if not isinstance(uid, str) or not uid:
                result.skipped += 1
                continue
            area_row = (
                area.get("name", ""),
                json.dumps(list(area.get("flags", ()))),
                json.dumps(dict(area.get("details") or {})),
            )
            if overwrite or uid not in given_areas:
                given_areas[uid] = area_row
        note_items = {str(uid): text for uid, text in (notes or {}).items()}
        room_uids = [r["uid"] for r in room_items if r is not None]
        with self.db.transaction():
            stored_areas = {
                r["uid"]
                for r in _select_in(
                    self.db, "SELECT uid FROM areas WHERE uid IN ({marks})", list(given_areas)
                )
            }
            for uid, area_row in given_areas.items():
                if overwrite or uid not in stored_areas:
                    area_rows[uid] = (uid, *area_row)
            result.areas = len(area_rows)

            wanted = list(dict.fromkeys([*room_uids, *note_items]))
            current_rooms = {
                r["uid"]: _row_to_room(r)
                for r in _select_in(self.db, "SELECT * FROM rooms WHERE uid IN ({marks})", wanted)
            }
            written_rooms: dict[str, dict[str, Any]] = {}
            new_rooms: set[str] = set()
            current_exits: dict[tuple[str, str], Exit] = {}
            written_exits: dict[tuple[str, str], Exit] = {}
            exit_items: list[Any] = []
            embedded: list[bool] = []
            result.skipped += sum(1 for r in room_items if r is None)
            for raw, room in zip(raw_rooms, room_items, strict=True):
                if room is None:
                    continue
                uid = room["uid"]
                merged = merge_room(current_rooms.get(uid), room, overwrite)
                if merged is not None:
                    if uid not in current_rooms:
                        new_rooms.add(uid)
                    current_rooms[uid] = merged
                    written_rooms[uid] = merged
                for direction, touid in (raw.get("exits") or {}).items():
                    exit_items.append({"fromuid": uid, "dir": str(direction), "touid": str(touid)})
                    embedded.append(True)
            explicit = list(exits or ())
            exit_items.extend(explicit)
            embedded.extend(False for _ in explicit)

            parsed: list[Exit | None] = []
            for item in exit_items:
                parsed.append(self._parse_exit(item))
            result.skipped += sum(1 for p in parsed if p is None)
            from_uids = list(dict.fromkeys(p.fromuid for p in parsed if p is not None))
            for row in _select_in(
                self.db, "SELECT * FROM exits WHERE fromuid IN ({marks})", from_uids
            ):
                current_exits[(row["fromuid"], row["dir"])] = _row_to_exit(row)
            stored_exit_keys = set(current_exits)
            for given, is_embedded in zip(parsed, embedded, strict=True):
                if given is None:
                    continue
                key = (given.fromuid, given.dir)
                exit_merged = merge_exit(
                    current_exits.get(key), given, overwrite, keep_details=is_embedded
                )
                if exit_merged is not None:
                    current_exits[key] = exit_merged
                    written_exits[key] = exit_merged

            note_uids = [u for u in note_items if u in current_rooms]
            result.skipped += len(note_items) - len(note_uids)
            stored_notes = {
                r["uid"]: r["notes"]
                for r in _select_in(
                    self.db, "SELECT uid, notes FROM bookmarks WHERE uid IN ({marks})", note_uids
                )
            }
            note_rows: list[tuple[str, str]] = []
            for uid in note_uids:
                text = note_items[uid]
                if not isinstance(text, str):
                    result.skipped += 1
                elif stored_notes.get(uid) == text or (not overwrite and stored_notes.get(uid)):
                    continue
                else:
                    note_rows.append((uid, text))

            self.db.modifymany(
                "INSERT OR REPLACE INTO areas(uid, name, flags, details) VALUES(?, ?, ?, ?)",
                list(area_rows.values()),
            )
            self.db.modifymany(
                UPSERT_ROOM_SQL,
                [
                    (
                        r["uid"],
                        r["name"],
                        r["area"],
                        r["terrain"],
                        r["x"],
                        r["y"],
                        r["z"],
                        json.dumps(r["flags"]),
                        json.dumps(r["details"]),
                    )
                    for r in written_rooms.values()
                ],
            )
            self.db.modifymany(
                UPSERT_EXIT_SQL,
                [
                    (
                        e.fromuid,
                        e.dir,
                        e.touid,
                        e.cost,
                        json.dumps(e.requirement) if e.requirement is not None else None,
                    )
                    for e in written_exits.values()
                ],
            )
            self.db.modifymany(
                "INSERT OR REPLACE INTO bookmarks(uid, notes) VALUES(?, ?)", note_rows
            )
        result.rooms = len(written_rooms)
        result.new_rooms = len(new_rooms)
        result.exits = len(written_exits)
        result.new_exits = len(written_exits.keys() - stored_exit_keys)
        result.notes = len(note_rows)
        result.room_flags = {uid: r["flags"] for uid, r in written_rooms.items()}
        result.written_exits = list(written_exits.values())
        return result

    @staticmethod
    def _parse_exit(item: Any) -> Exit | None:
        """Build an Exit from a batch item, or None when it is invalid."""
        if not isinstance(item, Mapping):
            return None
        fromuid = item.get("fromuid")
        direction = item.get("dir")
        cost = item.get("cost", 1)
        requirement = item.get("requirement")
        if not isinstance(direction, str) or exit_problem(fromuid, direction, cost, requirement):
            return None
        return Exit(str(fromuid), direction, str(item.get("touid", UNKNOWN_UID)), cost, requirement)

    def load_graph(self) -> MapGraph:
        """Build the graph from the database."""
        graph = MapGraph()
        for row in self.db.select("SELECT uid, flags FROM rooms"):
            graph.set_room(row["uid"], json.loads(row["flags"] or "[]"))
        for row in self.db.select("SELECT * FROM exits"):
            graph.set_exit(_row_to_exit(row))
        return graph

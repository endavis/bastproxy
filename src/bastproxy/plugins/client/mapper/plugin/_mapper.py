# Project: bastproxy
# Filename: plugins/client/mapper/plugin/_mapper.py
#
# File Description: a plugin that stores the map, finds paths and walks them
#
# By: Bast
"""The map, pathfinding and walking, with game plugins as adapters (ADR-0021)."""

# Standard Library
import asyncio
import json
import logging
from collections.abc import Callable
from functools import partial
from typing import Any

# Project
from bastproxy.libs.api import AddAPI
from bastproxy.libs.logger import log_to
from bastproxy.libs.records import NetworkData, SendDataDirectlyToClient, SendDataDirectlyToMud
from bastproxy.libs.validators import int_range
from bastproxy.plugins._baseplugin import BasePlugin, RegisterPluginHook
from bastproxy.plugins.client.mapper.libs._batch import (
    BAD_EXIT,
    BATCH_LIMIT,
    count_rows,
    exit_problem,
)
from bastproxy.plugins.client.mapper.libs._graph import Exit, MapGraph, find_path, requirement_key
from bastproxy.plugins.client.mapper.libs._schema import DB_NAME, DB_VERSION, TABLES, UNKNOWN_UID
from bastproxy.plugins.client.mapper.libs._store import MapStore, room_differences
from bastproxy.plugins.client.mapper.libs._walk import MAX_REROUTES, SEARCHING, Walk, WalkUpdate
from bastproxy.plugins.core.commands import AddArgument, AddParser, CommandResult
from bastproxy.plugins.core.events import RegisterToEvent

DEFAULT_MAX_DEPTH = 300
FIND_LIMIT = 50

EVENT_PREFIX = "ev_plugins.client.mapper_"
EVENTS: dict[str, tuple[str, dict[str, str]]] = {
    "room_arrived": (
        "the character is in a room, raised by room.current.set",
        {"uid": "the room the character is in", "previous": "the room before, or None"},
    ),
    "room_changed": (
        "a room was added or updated",
        {"uid": "the room uid", "new": "True when the room was not stored before"},
    ),
    "room_mismatch": (
        "a room update contradicts the stored room",
        {
            "uid": "the room uid",
            "differences": "dict with area as (old, new) and exits as {dir: (old, new)}",
        },
    ),
    "map_changed": (
        "a batch write changed the map, raised once by map.batch.add",
        {
            "areas": "the areas written",
            "rooms": "the rooms written",
            "new_rooms": "the rooms that were not stored before",
            "exits": "the exits written, new and changed together",
            "new_exits": "the written exits that were not stored before",
            "notes": "the notes written",
            "skipped": "the items skipped as bad",
        },
    ),
    "walk_started": (
        "a walk started",
        {"target": "the target room uid", "steps": "the steps, as dicts"},
    ),
    "walk_step": (
        "a walk step was sent",
        {"index": "the step number", "step": "the step dict", "commands": "the commands sent"},
    ),
    "walk_done": ("a walk reached its target", {"target": "the target room uid"}),
    "walk_failed": (
        "a walk could not start or was stopped",
        {"target": "the target room uid", "reason": "why", "uid": "the room the character is in"},
    ),
}


class MapperPlugin(BasePlugin):
    """a plugin that stores the map, finds paths and walks them."""

    store: MapStore
    graph: MapGraph

    @RegisterPluginHook("__init__")
    def _phook_init_plugin(self) -> None:
        """Initialize the instance."""
        self.current_room: str | None = None
        self.walk = Walk()
        self.requirement_callbacks: dict[str, Callable[[Any, dict[str, Any]], bool]] = {}
        self.movement_callbacks: dict[str, Callable[[list[dict[str, Any]]], list[str]]] = {}
        self._search_token = 0
        self._unload_token = 0

    @RegisterPluginHook("uninitialize")
    def _phook_mapper_uninitialize(self) -> None:
        """Drop the results of searches still running."""
        self._search_token += 1
        self._unload_token += 1

    @RegisterPluginHook("after_load")
    def _phook_initialize(self) -> None:
        """Open the map database, load the graph, add events and settings."""
        db = self.api("plugins.core.sqldb:database.add")(
            self.plugin_id, DB_NAME, TABLES, version=DB_VERSION
        )
        self.store = MapStore(db)
        self.graph = self.store.load_graph()
        for name, (description, arg_descriptions) in EVENTS.items():
            self.api("plugins.core.events:event.add")(
                f"{EVENT_PREFIX}{name}",
                self.plugin_id,
                description=[description],
                arg_descriptions=arg_descriptions,
            )
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id,
            "maxdepth",
            DEFAULT_MAX_DEPTH,
            int,
            "the most steps a path may have",
            validator=int_range(1, label="number of steps"),
        )
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id, "shownotes", True, bool, "show a room's note when entering it"
        )
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id, "reroute", True, bool, "find a new path when a walk ends up elsewhere"
        )

    # helpers
    def _raise(self, name: str, **event_args: Any) -> None:
        """Raise one of the mapper events."""
        self.api("plugins.core.events:event.raise")(f"{EVENT_PREFIX}{name}", event_args=event_args)

    def _setting(self, name: str) -> Any:
        """Get one of this plugin's settings."""
        return self.api("plugins.core.settings:setting.get")(self.plugin_id, name)

    @staticmethod
    def _active(callbacks: dict[str, Any]) -> Any:
        """Return the most recently registered callback, or None."""
        return next(reversed(callbacks.values())) if callbacks else None

    def _register(self, callbacks: dict[str, Any], kind: str, owner_id: str, callback: Any) -> None:
        """Register a callback for an owner, warning when it replaces another owner's."""
        callbacks.pop(owner_id, None)
        if callbacks:
            log_to(
                [self.plugin_id],
                logging.WARNING,
                "%s callback of %s replaces the one of %s",
                kind,
                owner_id,
                next(reversed(callbacks)),
            )
        callbacks[owner_id] = callback

    # areas
    @AddAPI("area.add", description="add an area or replace it")
    def _api_area_add(
        self,
        uid: str,
        name: str = "",
        flags: tuple[str, ...] | list[str] = (),
        details: dict[str, Any] | None = None,
    ) -> bool:
        """Add an area or replace it.

        @Yuid@w       = the area uid, a non-empty string
        @Yname@w      = the area name
        @Yflags@w     = a list of flag strings
        @Ydetails@w   = a JSON-serialisable dict

        This function returns True when the area was stored.
        """
        if not isinstance(uid, str) or not uid:
            log_to([self.plugin_id], logging.WARNING, "_api_area_add: bad area uid")
            return False
        self.store.add_area(uid, name, flags, details or {})
        return True

    @AddAPI("area.get", description="get an area")
    def _api_area_get(self, uid: str) -> dict[str, Any] | None:
        """Get an area as a dict with uid, name, flags and details, or None."""
        return self.store.get_area(uid)

    @AddAPI("area.list", description="list the areas")
    def _api_area_list(self) -> list[dict[str, Any]]:
        """List all areas."""
        return self.store.list_areas()

    @AddAPI("area.remove", description="remove an area, its rooms, their exits and notes")
    def _api_area_remove(self, uid: str) -> int:
        """Remove an area, its rooms, the exits from and to them, and their notes.

        This function returns the number of rooms removed.
        """
        rooms = self.store.remove_area(uid)
        for room_uid in rooms:
            self.graph.remove_room(room_uid)
        return len(rooms)

    # rooms
    @AddAPI("room.add", description="add a room or update it, with change detection")
    def _api_room_add(self, room: dict[str, Any]) -> bool:
        """Add a room or update it.

        @Yroom@w   = a dict with uid (required), name, area, terrain, x, y, z, flags (list),
                     details (dict) and optionally exits ({direction: touid})

        An update that contradicts the stored room raises the room_mismatch event.
        Exits missing from the update are kept, and an unexplored touid never
        overwrites a known one. An exit that already exists keeps its stored cost and
        requirement, only exit.add changes them. This function returns True when the
        room was stored.
        """
        uid = room.get("uid") if isinstance(room, dict) else None
        if uid is None or str(uid) == "":
            log_to([self.plugin_id], logging.WARNING, "_api_room_add: the room has no uid")
            return False
        room = {**room, "uid": str(uid)}
        uid = room["uid"]
        stored = self.store.get_room(uid)
        differences = room_differences(stored, self.store.exits_from(uid), room)
        self.store.upsert_room(room)
        self.graph.set_room(uid, room.get("flags", []))
        for direction, touid in (room.get("exits") or {}).items():
            self._add_exit(uid, str(direction), str(touid), 1, None, keep_details=True)
        self._raise("room_changed", uid=uid, new=stored is None)
        if differences:
            self._raise("room_mismatch", uid=uid, differences=differences)
        return True

    @AddAPI("room.get", description="get a room with its exits and note")
    def _api_room_get(self, uid: str) -> dict[str, Any] | None:
        """Get a room, with ``exits`` as a list of dicts and its ``note``, or None."""
        room = self.store.get_room(uid)
        if room is None:
            return None
        room["exits"] = [e.to_dict() for e in self.store.exits_from(uid)]
        room["note"] = self.store.get_note(uid)
        return room

    @AddAPI("room.remove", description="remove a room, its exits and its note")
    def _api_room_remove(self, uid: str) -> bool:
        """Remove a room, the exits from and to it, and its note."""
        removed = self.store.remove_room(uid)
        self.graph.remove_room(uid)
        return removed

    @AddAPI("room.list", description="list rooms by name, area and flag")
    def _api_room_list(
        self,
        name: str | None = None,
        area: str | None = None,
        flag: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """List rooms.

        @Yname@w    = a part of the room name, case-insensitive
        @Yarea@w    = the area uid
        @Yflag@w    = a flag the room has
        @Ylimit@w   = the most rooms to return
        """
        return self.store.list_rooms(name, area, flag, limit)

    @AddAPI("room.list.unexplored", description="list rooms with an unexplored exit")
    def _api_room_list_unexplored(self, area: str | None = None) -> list[dict[str, Any]]:
        """List rooms that have an exit whose touid is -1."""
        return self.store.unexplored(area)

    @AddAPI("room.current.get", description="get the room the character is in")
    def _api_room_current_get(self) -> str | None:
        """Get the uid of the current room, or None when it is not known."""
        return self.current_room

    @AddAPI("room.current.set", description="tell the mapper which room the character is in")
    def _api_room_current_set(self, uid: str) -> None:
        """Set the current room. A game plugin calls this on every arrival.

        This raises room_arrived, shows the room's note when the shownotes setting is
        on and gives the arrival to the walk, which sends its next step.
        """
        previous = self.current_room
        self.current_room = uid
        self._raise("room_arrived", uid=uid, previous=previous)
        if self._setting("shownotes") and (note := self.store.get_note(uid)):
            SendDataDirectlyToClient(
                NetworkData([f"Note: {note}"], owner_id=self.plugin_id),
            )()
        self._handle_walk_update(self.walk.arrived(uid), uid)

    # notes
    @AddAPI("room.note.set", description="set the note of a room")
    def _api_room_note_set(self, uid: str, text: str) -> bool:
        """Set the note of a room. This function returns True when the room exists."""
        if self.store.get_room(uid) is None:
            return False
        self.store.set_note(uid, text)
        return True

    @AddAPI("room.note.get", description="get the note of a room")
    def _api_room_note_get(self, uid: str) -> str | None:
        """Get the note of a room, or None."""
        return self.store.get_note(uid)

    @AddAPI("room.note.remove", description="remove the note of a room")
    def _api_room_note_remove(self, uid: str) -> bool:
        """Remove the note of a room. This function returns True when there was one."""
        return self.store.remove_note(uid)

    # exits
    @AddAPI("exit.add", description="add an exit or update it")
    def _api_exit_add(
        self,
        fromuid: str,
        dir: str,
        touid: str = UNKNOWN_UID,
        cost: int = 1,
        requirement: Any = None,
    ) -> bool:
        """Add an exit or update the exit with the same room and direction.

        @Yfromuid@w       = the room uid, or ``*`` (portals) or ``**`` (recall)
        @Ydir@w           = the command that takes the exit
        @Ytouid@w         = the room it leads to, ``-1`` when not explored
        @Ycost@w          = the cost of taking the exit
        @Yrequirement@w   = a JSON-serialisable value for the requirement callback, or None

        An unexplored touid never overwrites a known one. This function returns True
        when the exit was stored.
        """
        return self._add_exit(fromuid, dir, touid, cost, requirement, keep_details=False)

    def _add_exit(
        self,
        fromuid: str,
        dir: str,
        touid: str,
        cost: int,
        requirement: Any,
        *,
        keep_details: bool,
    ) -> bool:
        """Validate and store an exit, see ``exit.add``.

        ``keep_details`` keeps the stored cost and requirement of an existing exit.
        """
        problem = exit_problem(fromuid, dir, cost, requirement)
        if problem == BAD_EXIT:
            log_to([self.plugin_id], logging.WARNING, "_api_exit_add: bad exit %r %r", fromuid, dir)
            return False
        if problem:
            log_to([self.plugin_id], logging.WARNING, "_api_exit_add: requirement is not JSON")
            return False
        stored = self.store.upsert_exit(
            Exit(str(fromuid), dir, str(touid), cost, requirement), keep_details=keep_details
        )
        self.graph.set_exit(stored)
        return True

    @AddAPI(
        "map.batch.add", description="write many areas, rooms, exits and notes in one transaction"
    )
    def _api_map_batch_add(
        self,
        areas: list[dict[str, Any]] | None = None,
        rooms: list[dict[str, Any]] | None = None,
        exits: list[dict[str, Any]] | None = None,
        notes: dict[str, str] | None = None,
        overwrite: bool = True,
    ) -> dict[str, int] | None:
        """Write areas, rooms, exits and notes in one transaction, then update the graph.

        @Yareas@w       = a list of area.add dicts (uid, name, flags, details)
        @Yrooms@w       = a list of room.add dicts, with optional exits ({direction: touid})
        @Yexits@w       = a list of dicts with fromuid, dir, touid, cost and requirement
        @Ynotes@w       = a dict of {room uid: text}, set only for a stored room
        @Yoverwrite@w   = True to replace what is stored as the per-item apis do,
                          False to fill gaps: a stored area is kept, a stored room only
                          gains missing flags, a stored exit keeps its cost and only
                          fills an unexplored touid or a missing requirement, and a
                          note is set only where there is none. With True, an exit
                          embedded in a room keeps its stored cost and requirement
                          as room.add does; an explicit exit replaces them

        An unexplored touid never overwrites a known one. A bad item is skipped and
        counted. A batch of more than BATCH_LIMIT rows (embedded exits included) is
        refused and nothing is written, so the caller sends slices and yields between
        them. No room_changed or room_mismatch is raised, one map_changed is raised when
        a row changed. sqlite3.Error propagates with nothing written.

        This function returns the counts (areas, rooms, new_rooms, exits, new_exits,
        notes, skipped), or None when the batch is over the limit.
        """
        total = count_rows(areas, rooms, exits, notes)
        if total > BATCH_LIMIT:
            log_to(
                [self.plugin_id],
                logging.WARNING,
                "_api_map_batch_add: %s rows is over the limit of %s, nothing written",
                total,
                BATCH_LIMIT,
            )
            return None
        result = self.store.write_batch(areas, rooms, exits, notes, overwrite)
        for uid, flags in result.room_flags.items():
            self.graph.set_room(uid, flags)
        for stored_exit in result.written_exits:
            self.graph.set_exit(stored_exit)
        if result.skipped:
            log_to(
                [self.plugin_id],
                logging.WARNING,
                "_api_map_batch_add: skipped %s bad items",
                result.skipped,
            )
        if result.changed():
            self._raise("map_changed", **result.counts())
        return result.counts()

    @AddAPI("exit.remove", description="remove an exit")
    def _api_exit_remove(self, fromuid: str, dir: str) -> bool:
        """Remove an exit. This function returns True when it existed."""
        self.graph.remove_exit(fromuid, dir)
        return self.store.remove_exit(fromuid, dir)

    @AddAPI("exit.list", description="list the exits of a room")
    def _api_exit_list(self, fromuid: str) -> list[dict[str, Any]]:
        """List the exits stored for a room or for ``*``/``**``, as dicts."""
        return [e.to_dict() for e in self.store.exits_from(fromuid)]

    # callbacks
    @AddAPI(
        "requirement.register", description="register the callback that checks exit requirements"
    )
    def _api_requirement_register(
        self, owner_id: str, callback: Callable[[Any, dict[str, Any]], bool]
    ) -> None:
        """Register the requirement callback.

        @Yowner_id@w   = the plugin id
        @Ycallback@w   = ``callback(requirement, exit_dict) -> bool``; True lets the path
                         use the exit. A callback that raises blocks the exit.

        The most recent registration is the active one.
        """
        self._register(self.requirement_callbacks, "requirement", owner_id, callback)

    @AddAPI("requirement.unregister", description="remove a requirement callback")
    def _api_requirement_unregister(self, owner_id: str) -> None:
        """Remove the requirement callback of an owner."""
        self.requirement_callbacks.pop(owner_id, None)

    @AddAPI("movement.register", description="register the callback that turns steps into commands")
    def _api_movement_register(
        self, owner_id: str, callback: Callable[[list[dict[str, Any]]], list[str]]
    ) -> None:
        """Register the movement callback.

        @Yowner_id@w   = the plugin id
        @Ycallback@w   = ``callback(steps) -> list of commands``, steps being exit dicts.
                         A callback that raises or returns bad data is replaced by the default,
                         which sends each step's direction.

        The most recent registration is the active one.
        """
        self._register(self.movement_callbacks, "movement", owner_id, callback)

    @AddAPI("movement.unregister", description="remove a movement callback")
    def _api_movement_unregister(self, owner_id: str) -> None:
        """Remove the movement callback of an owner."""
        self.movement_callbacks.pop(owner_id, None)

    @RegisterToEvent(event_name="ev_plugin_unloaded")
    def _eventcb_plugin_unloaded(self) -> None:
        """A plugin was unloaded, drop its callbacks."""
        if event_record := self.api("plugins.core.events:event.current.record.get")():
            owner = event_record["plugin_id"]
            self.requirement_callbacks.pop(owner, None)
            self.movement_callbacks.pop(owner, None)

    @RegisterToEvent(event_name="ev_libs.net.mud_muddisconnect")
    def _eventcb_disconnect(self) -> None:
        """The MUD connection closed, stop an active walk."""
        self._api_walk_clear("disconnected")

    # paths
    def _ask(self, callback: Callable[[Any, dict[str, Any]], bool], exit_: Exit) -> bool:
        """Ask the requirement callback about an exit; a callback that raises blocks it."""
        try:
            return bool(callback(exit_.requirement, exit_.to_dict()))
        except Exception:
            log_to(
                [self.plugin_id],
                logging.ERROR,
                "requirement callback failed for %s, the exit is blocked",
                requirement_key(exit_.requirement),
                exc_info=True,
            )
            return False

    def _allowed(self) -> Callable[[Exit], bool]:
        """Build the exit filter for one search, asking the callback once per requirement."""
        callback = self._active(self.requirement_callbacks)
        memo: dict[str, bool] = {}

        def allowed(exit_: Exit) -> bool:
            if exit_.requirement is None or callback is None:
                return True
            key = requirement_key(exit_.requirement)
            if key not in memo:
                memo[key] = self._ask(callback, exit_)
            return memo[key]

        return allowed

    def _prejudged(self) -> Callable[[Exit], bool]:
        """Ask the callback about every requirement in the map, here on the loop.

        The filter returned only looks the answers up, so a worker thread can use it.
        """
        callback = self._active(self.requirement_callbacks)
        if callback is None:
            return lambda _exit: True
        verdicts = {
            key: self._ask(callback, sample) for key, sample in self.graph.requirements().items()
        }

        def allowed(exit_: Exit) -> bool:
            if exit_.requirement is None:
                return True
            return verdicts.get(requirement_key(exit_.requirement), False)

        return allowed

    def _in_thread(
        self,
        work: Callable[[], Any],
        done: Callable[[Any, Exception | None], None],
        name: str,
    ) -> None:
        """Run ``work`` in a worker thread, then ``done(result, error)`` on the loop."""
        self.api("libs.asynch:task.add")(
            self._run_in_thread(work, done, self._unload_token), f"{self.plugin_id}:{name}"
        )

    async def _run_in_thread(
        self,
        work: Callable[[], Any],
        done: Callable[[Any, Exception | None], None],
        unload_token: int,
    ) -> None:
        """Await the worker, then hand its result or error to ``done``."""
        result: Any = None
        error: Exception | None = None
        try:
            result = await asyncio.to_thread(work)
        except Exception as exc:
            error = exc
            log_to([self.plugin_id], logging.ERROR, "path search failed", exc_info=True)
        if unload_token != self._unload_token:
            return
        try:
            done(result, error)
        except Exception:
            log_to([self.plugin_id], logging.ERROR, "path search completion failed", exc_info=True)

    def _search(
        self,
        start: str,
        target: str,
        done: Callable[[Any, Exception | None], None],
        name: str,
    ) -> None:
        """Search a frozen view of the graph in a worker thread."""
        view = self.graph.freeze()
        allowed = self._prejudged()
        depth = int(self._setting("maxdepth"))
        work = partial(find_path, view, start, target, max_depth=depth, allowed=allowed)
        self._in_thread(work, done, name)

    def _tell(self, lines: list[str]) -> None:
        """Send lines to the client."""
        SendDataDirectlyToClient(NetworkData(lines, owner_id=self.plugin_id))()

    def _find(self, start: str, target: str, max_depth: int | None = None) -> Any:
        """Run the pathfinder and return a PathResult or None."""
        depth = int(self._setting("maxdepth")) if max_depth is None else max_depth
        return find_path(self.graph, start, target, max_depth=depth, allowed=self._allowed())

    @AddAPI("path.get", description="find the cheapest path between two rooms")
    def _api_path_get(
        self, start: str, target: str, max_depth: int | None = None
    ) -> dict[str, Any] | None:
        """Find the cheapest path.

        @Ystart@w       = the room uid to start from
        @Ytarget@w      = the room uid to reach
        @Ymax_depth@w   = the most steps, default the maxdepth setting

        This function returns ``{"start", "target", "cost", "steps"}`` with each step a dict
        of fromuid, touid, dir, cost and requirement, or None when the target cannot be
        reached. The search runs on the event loop, so a long one stalls it; walks and
        commands search in a worker thread instead.
        """
        result = self._find(start, target, max_depth)
        if result is None:
            return None
        return {
            "start": start,
            "target": target,
            "cost": result.cost,
            "steps": [step.to_dict() for step in result.steps],
        }

    # moving
    def _send_steps(self, steps: list[Exit]) -> list[str]:
        """Turn steps into commands with the movement callback and send them to the MUD."""
        default = [step.dir for step in steps]
        commands = default
        if callback := self._active(self.movement_callbacks):
            try:
                result = callback([step.to_dict() for step in steps])
                if isinstance(result, list) and all(isinstance(c, str) for c in result):
                    commands = result
                else:
                    raise TypeError("the movement callback must return a list of str")
            except Exception:
                log_to(
                    [self.plugin_id],
                    logging.ERROR,
                    "movement callback failed, sending the directions",
                    exc_info=True,
                )
                commands = default
        for command in commands:
            SendDataDirectlyToMud(NetworkData(command, owner_id=f"{self.plugin_id}:walk"))()
        return commands

    def _fail(self, target: str | None, reason: str) -> None:
        """Raise walk_failed."""
        self._raise("walk_failed", target=target, reason=reason, uid=self.current_room)

    def _send_walk_step(self, step: Exit) -> None:
        """Send one walk step and raise walk_step."""
        commands = self._send_steps([step])
        self._raise("walk_step", index=self.walk.index, step=step.to_dict(), commands=commands)

    def _handle_walk_update(self, update: WalkUpdate, uid: str) -> None:
        """Act on what an arrival did to the walk."""
        if update.kind == "step" and update.step is not None:
            self._send_walk_step(update.step)
        elif update.kind == "done":
            self._raise("walk_done", target=self.walk.target)
        elif update.kind == "unexpected":
            self._reroute(uid)

    def _reroute(self, uid: str) -> None:
        """The character is in a room the walk did not expect."""
        target = self.walk.target
        if target is not None and self._setting("reroute") and self.walk.reroutes < MAX_REROUTES:
            self._begin_walk(target, uid, "reroute", False)
            return
        self.walk.stop()
        self._fail(target, "unexpected room")

    def _begin_walk(self, target: str, start: str, mode: str, report: bool) -> None:
        """Put the walk in the searching state and search in a worker thread."""
        self._search_token += 1
        token = self._search_token
        self.walk.searching(target, start)
        self._search(
            start, target, partial(self._walk_found, token, mode, start, target, report), "walk"
        )

    def _walk_found(
        self,
        token: int,
        mode: str,
        start: str,
        target: str,
        report: bool,
        result: Any,
        error: Exception | None,
    ) -> None:
        """Act on the result of a walk search, unless the walk moved on meanwhile."""
        if token != self._search_token or self.walk.state != SEARCHING:
            return
        reason = ""
        if error is not None:
            reason = "search failed"
        elif self.current_room != start:
            reason = "moved during search"
        elif result is None:
            reason = "unexpected room" if mode == "reroute" else "no path"
        if reason:
            if reason == "no path" and mode == "start":
                self.walk.finish()
            else:
                self.walk.stop()
            self._fail(target, reason)
            if report:
                self._tell([f"could not walk to {target}: {reason}"])
            return
        steps: list[Exit] = result.steps
        if mode == "reroute":
            if not steps:
                self.walk.finish()
                self._raise("walk_done", target=target)
                return
            self.walk.reroute(steps, start)
            self._send_walk_step(steps[0])
            return
        if mode == "start":
            self.walk.start(target, steps, start)
        else:
            self.walk.restart(steps, start)
        if report:
            self._tell([f"walking to {target}"])
        self._raise("walk_started", target=target, steps=[s.to_dict() for s in steps])
        if not steps:
            self.walk.finish()
            self._raise("walk_done", target=target)
        else:
            self._send_walk_step(steps[0])

    def _start_walk(self, target: str, report: bool) -> bool:
        """Start the search for a walk from the current room."""
        start = self.current_room
        if start is None:
            self._fail(target, "current room unknown")
            return False
        self._begin_walk(target, start, "start", report)
        return True

    def _restart_walk(self, report: bool) -> bool:
        """Start the search for resuming a stopped walk."""
        target = self.walk.target
        if not self.walk.can_restart() or target is None:
            return False
        start = self.current_room
        if start is None:
            self._fail(target, "current room unknown")
            return False
        self._begin_walk(target, start, "restart", report)
        return True

    @AddAPI("walk.start", description="walk to a room one step at a time")
    def _api_walk_start(self, target: str) -> bool:
        """Start a walk from the current room.

        The path is searched in a worker thread. This function returns True once the search
        has started and the walk is ``searching``; walk_started follows when the path is
        found, and walk_failed with the reason ``no path`` when there is none. Each step is
        sent when the previous one is confirmed by room.current.set. This function returns
        False, raising walk_failed, when the current room is not known.
        """
        return self._start_walk(target, False)

    @AddAPI("walk.restart", description="resume a stopped walk")
    def _api_walk_restart(self) -> bool:
        """Walk to the target of a stopped walk, from the current room.

        Like walk.start, this returns True once the search has started and reports a missing
        path later as walk_failed. It returns False when no walk is stopped or the current
        room is not known.
        """
        return self._restart_walk(False)

    @AddAPI("walk.clear", description="stop the walk, keeping its target")
    def _api_walk_clear(self, reason: str = "stopped") -> bool:
        """Stop an active walk. walk.restart can resume it.

        This function returns True when a walk was active, raising walk_failed with the reason.
        """
        target = self.walk.target
        if not self.walk.stop():
            return False
        self._fail(target, reason)
        return True

    @AddAPI("walk.get", description="get the state of the walk")
    def _api_walk_get(self) -> dict[str, Any]:
        """Get ``{state, target, steps, index, reroutes}``.

        The state is idle, searching, walking or stopped.
        """
        return self.walk.as_dict()

    # commands
    def _args(self) -> dict[str, Any]:
        """Get the arguments of the running command."""
        args: dict[str, Any] = self.api("plugins.core.commands:command.current.args.get")()
        return args

    def _room_line(self, room: dict[str, Any], steps: str) -> str:
        """Format a room for a list, with the steps to it from the current room."""
        escape = self.api("plugins.core.colors:colorcode.escape")
        return f"{room['uid']} | {escape(room['name'])} | {escape(room['area'])} | {steps}"

    def _find_lines(self, rooms: list[dict[str, Any]], total: int, steps: list[str]) -> list[str]:
        """Format the find table."""
        lines = [
            "uid | name | area | steps",
            *(self._room_line(r, n) for r, n in zip(rooms, steps, strict=True)),
        ]
        if total > FIND_LIMIT:
            lines.append(f"{total} rooms found, showing {FIND_LIMIT}")
        return lines

    @AddParser(description="find rooms by name, area or flag")
    @AddArgument("text", help="a part of the room name", nargs="*", default=[])
    @AddArgument("-a", "--area", help="only rooms in this area", default=None)
    @AddArgument("-f", "--flag", help="only rooms with this flag", default=None)
    @AddArgument("-u", "--unexplored", help="list rooms with unexplored exits", action="store_true")
    def _command_find(self) -> CommandResult:
        """Find rooms.

        With a known current room the step counts are searched in a worker thread and the
        table is sent to the client when they are ready.
        """
        args = self._args()
        if args["unexplored"]:
            rooms = self.store.unexplored(args["area"])
        else:
            rooms = self.store.list_rooms(
                " ".join(args["text"]) or None, args["area"], args["flag"]
            )
        if not rooms:
            return CommandResult(True, ["No rooms found"])
        shown = rooms[:FIND_LIMIT]
        start = self.current_room
        if start is None:
            return CommandResult(True, self._find_lines(shown, len(rooms), ["-"] * len(shown)))
        view = self.graph.freeze()
        allowed = self._prejudged()
        depth = int(self._setting("maxdepth"))
        uids = [room["uid"] for room in shown]

        def work() -> list[str]:
            counts: list[str] = []
            for uid in uids:
                found = find_path(view, start, uid, max_depth=depth, allowed=allowed)
                counts.append(str(len(found.steps)) if found is not None else "-")
            return counts

        def done(counts: Any, error: Exception | None) -> None:
            if error is not None:
                self._tell(["the path search for find failed"])
                return
            self._tell(self._find_lines(shown, len(rooms), counts))

        self._in_thread(work, done, "find")
        return CommandResult(True, [f"{len(rooms)} rooms found, finding the steps"])

    def _path_command(self, uid: str, done: Callable[[Any, Exception | None], None]) -> str:
        """Start the search of a path command from the current room; return the reply."""
        if self.current_room is None:
            return ""
        self._search(self.current_room, uid, done, "path")
        return f"finding a path to {uid}"

    @AddParser(description="send the whole path to a room at once")
    @AddArgument("uid", help="the room uid")
    def _command_goto(self) -> CommandResult:
        """Go to a room, sending the whole path through the movement callback."""
        uid = self._args()["uid"]
        reply = self._path_command(uid, partial(self._goto_found, self.current_room, uid))
        if not reply:
            return CommandResult(False, ["the current room is not known"])
        return CommandResult(True, [reply])

    def _goto_found(
        self, start: str | None, uid: str, result: Any, error: Exception | None
    ) -> None:
        """Send the path found for goto, unless the character moved or there is no path."""
        if error is not None:
            self._tell([f"the path search to {uid} failed"])
        elif self.current_room != start:
            self._tell([f"not going to {uid}: you moved during the search"])
        elif result is None:
            self._tell([f"no path to {uid}"])
        else:
            commands = self._send_steps(result.steps)
            self._tell([f"going to {uid}: {', '.join(commands) or 'already there'}"])

    @AddParser(description="walk to a room one step at a time")
    @AddArgument("uid", help="the room uid")
    def _command_walkto(self) -> CommandResult:
        """Start a walk."""
        uid = self._args()["uid"]
        if self._start_walk(uid, True):
            return CommandResult(True, [f"finding a path to {uid}"])
        return CommandResult(False, [f"could not start a walk to {uid}"])

    @AddParser(description="resume a stopped walk")
    def _command_resume(self) -> CommandResult:
        """Resume a stopped walk."""
        if self._restart_walk(True):
            return CommandResult(True, [f"finding a path to {self.walk.target}"])
        return CommandResult(False, ["there is no stopped walk to resume"])

    @AddParser(description="stop the walk")
    def _command_stop(self) -> CommandResult:
        """Stop the walk."""
        if self._api_walk_clear("stopped"):
            return CommandResult(True, ["walk stopped"])
        return CommandResult(False, ["there is no walk to stop"])

    @AddParser(description="show the path to a room without moving")
    @AddArgument("uid", help="the room uid")
    def _command_where(self) -> CommandResult:
        """Show a path."""
        uid = self._args()["uid"]
        reply = self._path_command(uid, partial(self._where_found, uid))
        if not reply:
            return CommandResult(False, ["the current room is not known"])
        return CommandResult(True, [reply])

    def _where_found(self, uid: str, result: Any, error: Exception | None) -> None:
        """Send the path found for where."""
        if error is not None:
            self._tell([f"the path search to {uid} failed"])
        elif result is None:
            self._tell([f"no path to {uid}"])
        else:
            directions = ", ".join(step.dir for step in result.steps) or "already there"
            self._tell([f"cost {result.cost}: {directions}"])

    @AddParser(description="show a room, its exits and its note")
    @AddArgument("uid", help="the room uid, default the current room", nargs="?", default=None)
    def _command_showroom(self) -> CommandResult:
        """Show a room."""
        uid = self._args()["uid"] or self.current_room
        room = self._api_room_get(uid) if uid else None
        if room is None:
            return CommandResult(False, [f"room {uid} is not known" if uid else "no current room"])
        escape = self.api("plugins.core.colors:colorcode.escape")
        lines = [
            f"room    : {room['uid']} {escape(room['name'])}",
            f"area    : {escape(room['area'])}",
            f"terrain : {escape(room['terrain'])}",
            f"coords  : {room['x']} {room['y']} {room['z']}",
            f"flags   : {', '.join(room['flags']) or '(none)'}",
            f"note    : {escape(room['note']) if room['note'] else '(none)'}",
            "exits   :",
        ]
        lines.extend(
            f"    {e['dir']} -> {e['touid']} (cost {e['cost']})"
            + (f" requires {escape(json.dumps(e['requirement']))}" if e["requirement"] else "")
            for e in room["exits"]
        )
        return CommandResult(True, lines)

    @AddParser(description="remove a room or an area")
    @AddArgument("-r", "--room", help="the room uid to remove", default=None)
    @AddArgument("-a", "--area", help="the area uid to remove, with its rooms", default=None)
    def _command_purge(self) -> CommandResult:
        """Remove a room or an area."""
        args = self._args()
        if bool(args["room"]) == bool(args["area"]):
            return CommandResult(False, ["Please give exactly one of -r ROOM or -a AREA"])
        if args["room"]:
            if self._api_room_remove(args["room"]):
                return CommandResult(True, [f"room {args['room']} removed"])
            return CommandResult(False, [f"room {args['room']} is not known"])
        count = self._api_area_remove(args["area"])
        return CommandResult(True, [f"area {args['area']} removed with {count} rooms"])

    @AddParser(description="show, set or delete the note of a room")
    @AddArgument("words", help="an optional room uid, then the note text", nargs="*", default=[])
    @AddArgument("-d", "--delete", help="delete the note", action="store_true")
    def _command_note(self) -> CommandResult:
        """Show, set or delete a note.

        The first word is the room uid when that room is stored, else the current room
        is used and every word is the note text.
        """
        args = self._args()
        words: list[str] = list(args["words"])
        uid = self.current_room
        if words and self.store.get_room(words[0]) is not None:
            uid = words.pop(0)
        if uid is None:
            return CommandResult(False, ["no room given and the current room is not known"])
        if self.store.get_room(uid) is None:
            return CommandResult(False, [f"room {uid} is not known"])
        if args["delete"]:
            if self._api_room_note_remove(uid):
                return CommandResult(True, [f"note of {uid} deleted"])
            return CommandResult(False, [f"room {uid} has no note"])
        if words:
            self._api_room_note_set(uid, " ".join(words))
            return CommandResult(True, [f"note of {uid} set"])
        note = self.store.get_note(uid)
        escape = self.api("plugins.core.colors:colorcode.escape")
        return CommandResult(
            True, [f"note of {uid}: {escape(note)}" if note else f"{uid} has no note"]
        )

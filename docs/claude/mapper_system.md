---
title: Mapper System
description: How the mapper plugin stores the map, finds paths and walks them, and what a game plugin adapter does
audience:
  - users
  - contributors
tags:
  - architecture
  - mapper
---

# Mapper System

`plugins.client.mapper` owns the map (areas, rooms, exits and notes), a pathfinder and a step-by-step walk engine. It knows nothing about any game. A game plugin is an adapter: it feeds the mapper rooms and exits, tells it which room the character is in, and answers game rules through two callbacks. The decision is recorded in [ADR-0021](../decisions/0021-the-mapper-owns-the-map-and-walking-and-game-plugins-adapt-it-through-callbacks.md) (issue #754). For using the commands, see [Mapper](../client/mapper.md).

The pure logic is in `plugins/client/mapper/libs/` and imports nothing from bastproxy: `_graph.py` (graph and pathfinder), `_walk.py` (walk state machine), `_store.py` (database access and change detection) and `_schema.py` (tables). the plugin class in the `plugin` package wires them to APIs, events, settings and commands.

## Storage

The plugin creates one sqlite database, `map`, with `plugins.core.sqldb:database.add` ([sqldb system](sqldb_system.md)) and no `directory`, so it lives in the plugin's data directory under the proxy home: one map per proxy home.

| Table | Holds |
| :--- | :--- |
| `areas` | `uid`, `name`, `flags` (JSON list), `details` (JSON dict) |
| `rooms` | `uid`, `name`, `area`, `terrain`, `x`, `y`, `z`, `flags`, `details` |
| `exits` | `fromuid`, `dir`, `touid`, `cost`, `requirement` (JSON or NULL), unique on `fromuid` and `dir` |
| `bookmarks` | `uid`, `notes`: the room notes |
| `storage` | `name`, `data`: free storage for an adapter |

The layout follows the MUSHclient mapper so an adapter can import an existing database. As there, a portal is an exit from the virtual room `*` and recall is an exit from `**`. The Aardwolf-only `level` column is replaced by `requirement`, a JSON value only the adapter understands. An exit with `touid` `-1` is unexplored. The graph is also held in memory, loaded in `after_load` and updated on every write.

## Adapter contract

1. Feed rooms and exits with `room.add` and `exit.add`. A room dict has `uid` (required), `name`, `area`, `terrain`, `x`, `y`, `z`, `flags` and `details`, and optionally `exits` as `{direction: touid}`.
2. Call `room.current.set(uid)` whenever the character enters or re-enters a room. This is the only arrival signal; the mapper does not read GMCP.
3. Register the callbacks, each keyed by the owner plugin id. The most recent registration is the active one, and registering over another owner logs a warning. A plugin's callbacks are dropped when it unloads.

| Callback | Signature | On failure |
| :--- | :--- | :--- |
| `requirement.register(owner_id, callback)` | `callback(requirement, exit_dict) -> bool`, only called for an exit that has a requirement. True lets the path use the exit. | A callback that raises is logged and blocks the exit. With no callback, exits are allowed. |
| `movement.register(owner_id, callback)` | `callback(steps: list[dict]) -> list[str]`, steps being exit dicts. Returns the commands to send. | A callback that raises or returns something other than a list of strings is logged, and the directions are sent. |

The requirement callback runs at most once per distinct requirement in one search. A walk calls the movement callback with one step at a time; the `goto` command calls it with the whole path, so an adapter can return a speedwalk such as `run 3n2e`. Commands are sent with `SendDataDirectlyToMud`.

## Pathfinding

`path.get(start, target, max_depth=None)` runs Dijkstra over the in-memory graph.

- The cost of a path is the sum of the exit costs. Ties go to the path with fewer steps.
- Exits from anywhere (`*` and `**`) count as exits of every room, so a portal costs what its exit costs. A room with the flag `noportal` blocks `*` and a room with `norecall` blocks `**`. A start uid that is not in the graph still gets these exits.
- Exits with `touid` `-1`, and exits the requirement callback blocks, are never used.
- The depth limit (the `maxdepth` setting when `max_depth` is None) prunes any path that would pass the limit. It bounds the search: a target whose cheapest route is longer than the limit is unreachable, even if a costlier, shorter route exists.
- `start == target` gives cost 0 and no steps. An unreachable target gives None.

## Walking

A walk has three states: `idle`, `walking` and `stopped`.

- `walk.start(target)` finds a path from the current room, raises `walk_started` and sends only the first step.
- Each `room.current.set` is given to the walk. The arrival of the step's target sends the next step (`walk_step`), or finishes the walk (`walk_done`). An arrival at the room the step left from, for example after `look`, is ignored.
- An arrival anywhere else re-paths from there and continues when the `reroute` setting is on, up to 3 times. Otherwise the walk stops with `walk_failed`, reason `unexpected room`.
- `walk.clear` stops the walk and keeps its target. `walk.restart` re-paths from the current room to that target. A MUD disconnect stops an active walk.
- A walk only starts from `walk.start` or a command. Arrivals while `idle` or `stopped` send nothing.

## Change detection

`room.add` on a stored room compares the update with what is stored. It raises `room_mismatch` when the area differs, when a stored exit has a different known `touid`, or when a direction exists on only one side. The room row is then replaced and the given exits are stored. Stored exits are never deleted and a `-1` never overwrites a known `touid`. What to purge is left to the adapter or the user.

## APIs

All are `plugins.client.mapper:<name>`. Names follow [ADR-0004](../decisions/0004-api-names-are-resource-first-and-cmdq-is-renamed-mudcmds.md).

| API | Returns |
| :--- | :--- |
| `area.add(uid, name="", flags=(), details=None)`, `area.get(uid)`, `area.list()` | bool, dict or None, list |
| `area.remove(uid)` | the number of rooms removed, with their exits and notes |
| `room.add(room)`, `room.get(uid)`, `room.remove(uid)` | bool, the room with `exits` and `note`, bool |
| `room.list(name=None, area=None, flag=None, limit=None)` | rooms; `name` is a case-insensitive substring |
| `room.list.unexplored(area=None)` | rooms with an exit whose `touid` is `-1` |
| `room.current.set(uid)`, `room.current.get()` | None, the uid or None |
| `room.note.set(uid, text)`, `room.note.get(uid)`, `room.note.remove(uid)` | bool, str or None, bool |
| `exit.add(fromuid, dir, touid="-1", cost=1, requirement=None)`, `exit.remove(fromuid, dir)`, `exit.list(fromuid)` | bool, bool, list of dicts |
| `path.get(start, target, max_depth=None)` | `{"start", "target", "cost", "steps": [{"fromuid", "touid", "dir", "cost", "requirement"}]}` or None |
| `requirement.register`, `requirement.unregister`, `movement.register`, `movement.unregister` | None |
| `walk.start(target)`, `walk.restart()`, `walk.clear(reason="stopped")` | bool |
| `walk.get()` | `{state, target, steps, index, reroutes}` |

## Events

| Event | Arguments |
| :--- | :--- |
| `ev_plugins.client.mapper_room_arrived` | `uid`, `previous` |
| `ev_plugins.client.mapper_room_changed` | `uid`, `new` |
| `ev_plugins.client.mapper_room_mismatch` | `uid`, `differences` |
| `ev_plugins.client.mapper_walk_started` | `target`, `steps` |
| `ev_plugins.client.mapper_walk_step` | `index`, `step`, `commands` |
| `ev_plugins.client.mapper_walk_done` | `target` |
| `ev_plugins.client.mapper_walk_failed` | `target`, `reason`, `uid` |

## Settings

| Setting | Default | Meaning |
| :--- | :--- | :--- |
| `maxdepth` | 300 | the most steps a path may have |
| `shownotes` | True | show a room's note when entering it |
| `reroute` | True | find a new path when a walk ends up elsewhere |

## Commands

`#bp.client.mapper.find`, `goto`, `walkto`, `resume`, `stop`, `where`, `showroom`, `purge` and `note`. See [Mapper](../client/mapper.md).

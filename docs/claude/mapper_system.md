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
4. Optionally add the adapter's commands under the mapper with `self.api("plugins.core.commands:command.add.for.plugin")("plugins.client.mapper", self._command_x)` from `after_load`. The mapper sets `accepts_command_extensions_f`; see [ADR-0024](../decisions/0024-plugins-add-commands-under-another-plugins-name-only-when-that-plugin-accepts-them.md).

| Callback | Signature | On failure |
| :--- | :--- | :--- |
| `requirement.register(owner_id, callback)` | `callback(requirement, exit_dict) -> bool`, only called for an exit that has a requirement, with `exit_dict` the one exit that carries it. True lets the path use the exit. A walk or command search asks it on the event loop before the search, once for every distinct requirement in the map; `path.get` asks it lazily, once per requirement it reaches. | A callback that raises is logged and blocks the exit. With no callback, exits are allowed. |
| `movement.register(owner_id, callback)` | `callback(steps: list[dict]) -> list[str]`, steps being exit dicts. Returns the commands to send. | A callback that raises or returns something other than a list of strings is logged, and the directions are sent. |

The requirement callback runs at most once per distinct requirement in one search, always on the event loop, so it may call `self.api(...)` and log. A walk calls the movement callback with one step at a time; the `goto` command calls it with the whole path, so an adapter can return a speedwalk such as `run 3n2e`. Commands are sent with `SendDataDirectlyToMud`.

## Pathfinding

`path.get(start, target, max_depth=None, portals=True, recalls=True)` runs Dijkstra over the in-memory graph.

- `portals=False` never uses the exits from `*`, and `recalls=False` never uses the exits from `**`. These are the same exits the `noportal` and `norecall` room flags block. A room's own custom exit, such as `enter portal`, is not a portal.

- The cost of a path is the sum of the exit costs. Ties go to the path with fewer steps.
- Exits from anywhere (`*` and `**`) count as exits of every room, so a portal costs what its exit costs. A room with the flag `noportal` blocks `*` and a room with `norecall` blocks `**`. A start uid that is not in the graph still gets these exits.
- Exits with `touid` `-1`, and exits the requirement callback blocks, are never used.
- The depth limit (the `maxdepth` setting when `max_depth` is None) prunes any path that would pass the limit. It bounds the search: a target whose cheapest route is longer than the limit is unreachable, even if a costlier, shorter route exists.
- `start == target` gives cost 0 and no steps. An unreachable target gives None.

## Walking

A walk has four states: `idle`, `searching`, `walking` and `stopped`.

- `walk.start(target, portals=True, recalls=True)` starts a path search from the current room and returns True once it has started, with the walk `searching`. When the search finishes it raises `walk_started` and sends only the first step. A target with no path arrives later as `walk_failed`, reason `no path`. It returns False, raising `walk_failed` with reason `current room unknown`, when the current room is not known.
- Arrivals while `searching` are ignored. If the character moved when the search ends, the walk stops with `walk_failed`, reason `moved during search`; a search that raised stops it with reason `search failed`. `walk.clear` during a search stops it and the late result is dropped.
- Each `room.current.set` is given to the walk. The arrival of the step's target sends the next step (`walk_step`), or finishes the walk (`walk_done`). An arrival at the room the step left from, for example after `look`, is ignored.
- An arrival anywhere else re-paths from there and continues when the `reroute` setting is on, up to 3 times. Otherwise the walk stops with `walk_failed`, reason `unexpected room`.
- `walk.clear` stops the walk and keeps its target. `walk.restart` searches a path from the current room to that target and returns like `walk.start`. A MUD disconnect stops an active walk.
- The walk keeps `portals` and `recalls` for its reroutes and `walk.restart`. `walkto` and `next` start walks with both off unless `-p` is given.
- A walk only starts from `walk.start` or a command. Arrivals while `idle` or `stopped` send nothing.

## Threading

Walks (`walk.start`, `walk.restart` and reroutes) and the commands `find`, `goto`, `where`, `speedwalk`, `walkto`, `next` and `resume` run the pathfinder in a worker thread, so a long search does not stall the event loop. The search does not run in parallel with the loop, as Python runs one thread at a time; it frees the loop, which keeps running between the switches. A command answers at once with a line like "finding a path to X" and reports its result in a later line to the client.

- **Copy-on-write views.** A search reads a frozen view of the graph. Taking the view shares the graph's outer dicts, and the first write after it copies them, so writes on the loop never change what a worker reads and no lock is needed. Per-room exit dicts are replaced on a write, never mutated.
- **Requirement callbacks stay on the loop.** Before the search the plugin asks the callback about every distinct requirement in the map and gives the worker a lookup, so adapters keep the API and the log. A requirement missing from the answers blocks its exit.
- **`path.get` stays synchronous** and runs on the event loop.
- **`load_graph` stays synchronous** at plugin load. The database connection belongs to the loop thread, and an adapter may write rooms right after load.
- **Web pages draw in a worker too.** The `area` page reads the area and its rooms on the loop, takes `graph.freeze()` and `current_room`, then draws with `await asyncio.to_thread(draw_area_svg, ...)`. The worker only reads the frozen view and the room dicts; it never calls an API or the database.
- A search result is dropped when the plugin unloads or the walk was stopped or restarted meanwhile.

## Web pages

`plugins.client.mapper` depends on `plugins.core.web` and, in an `after_load` hook (priority 60), registers four routes with `web.route.add`. It keeps each returned path in `web_paths`, so links use the real paths and a refused route only loses its links. Pages are GET only and need the web session; the web core enforces both (405, 401). See the [web system](web_system.md) and [ADR-0022](../decisions/0022-the-web-plugin-serves-token-links-and-session-gated-plugin-routes-over-a-get-only-standard-library-server.md).

| Path | Kind | Content |
| :--- | :--- | :--- |
| `/client/mapper` | table | Areas with room and unexplored counts; the uid links to the area map. |
| `/client/mapper/area?uid=` | svg | The area map, one nested `<svg>` per z level. |
| `/client/mapper/room?uid=` | table | Room details as lines, exits as rows linking to the target rooms. |
| `/client/mapper/find?name=` | table | Rooms whose name has the text, with column filters, sort and paging. |

- **Map.** Rooms are boxes at their stored x and y (y grows downwards) when those spread the rooms: on every z level each room has an int x and y and no two share an `(x, y)`. Otherwise (Aardwolf sends one coordinate for a whole area) the whole area, z included, is laid out from its exits by `_positions`: a breadth-first walk from the current room (else the lowest uid) puts each neighbour one step away in its compass direction (`u`/`d` change z), a taken cell moves the room to the nearest free one, and each part the exits do not connect starts two columns right of the parts before it. The layout is deterministic and pure, so it runs in the worker. Rooms are boxes at those positions, with a `<title>` tooltip of uid and name and a link to the room page. A line joins two rooms of a level; an exit that leaves the area is a `leaves` stub (a dot when it has no compass direction); an exit to another z level or `u`/`d` is an arrow; an unexplored exit is a dashed stub. Room classes: `current`, `unexplored`, `noportal`, `norecall`.
- **Errors.** A missing or empty `uid` is 400. An unknown area (no `areas` row and no rooms) or room is 404, through the web core's `error` kind. `find` never returns 404 and rejects a `name` over 200 characters with 400.
- **Escaping.** MUD text in SVG goes through `xml_text` (invalid XML characters dropped, then `html.escape`). Text in HTML cells and lines goes through `colorcode.escape` first, as `showroom` does. Link hrefs are built with `urlencode`.
- **SQL.** `find` builds its statement from fixed fragments (`SEARCH_COLUMNS`) and binds every value; `%`, `_` and `\` in a search text match literally.
- The pure builders are in `src/bastproxy/plugins/client/mapper/libs/_pages.py`, the queries in `MapStore.area_counts`, `get_rooms` and `search_rooms`.

## Change detection

`room.add` on a stored room compares the update with what is stored and raises `room_mismatch` with the `differences`:

- `name`, `terrain`, `x`, `y`, `z` as `(old, new)` and `details` as `{key: (old, new)}` (keys both sides have). These are updated and reported. A missing or `None` update value is not compared.
- `area` as `(old, new)` when both are non-empty. The stored area is kept until `accept`. An empty stored area is filled without a report.
- `exits` as `{dir: (old, new)}`. An existing exit whose known `touid` differs is reported and keeps its stored `touid` until `accept`. A new direction is added and reported as `(None, touid)`. A stored plain direction (`PLAIN_DIRECTIONS`: `n s e w u d ne nw se sw` and the long forms) the update lacks is reported as `(touid, None)` and kept. A custom exit is never reported as removed; one whose command is literally a plain direction is treated as plain. A `-1` on either side is never a difference.
- A room with the `ignoreexits` flag skips the exit comparison and its exits are written as given. `room.add` keeps this flag when the update's flags leave it out; a call without `flags` keeps the stored flags.

An exit that already exists keeps its stored `cost` and `requirement`, only `exit.add` changes them. `room.add` never deletes an exit. The held update is kept per room in memory (lost on reload) until a matching `room.add`, `room.remove` or `area.remove`. `accept [uid]` runs `room.add(update, accept=True)`, which writes the area and `touid`s as given and raises no `room_mismatch`, then removes the stale plain exits. `purge -a` stays for a replaced area.

## Batch writes

`map.batch.add` writes many rows in one call, one sqlite transaction and one commit. It is synchronous and never awaits.

- **Input.** `areas` is a list of `area.add` dicts, `rooms` a list of `room.add` dicts (embedded `exits` included), `exits` a list of dicts with the keys of `exit.list`, and `notes` a dict `{uid: text}`. Rows are written in that order, a room before its embedded exits.
- **Limit.** A call takes at most `BATCH_LIMIT` (1000) rows, embedded exits counted. A bigger batch is refused with a warning, returns None and writes nothing. The caller sends slices and yields (`await asyncio.sleep(0)`) between calls.
- **Bad items.** An item that `room.add`, `exit.add` or `area.add` would refuse, or a note for a room that is neither stored nor in the batch, is skipped and counted in `skipped`, with one warning per batch. A `sqlite3.Error` propagates with nothing written and the graph untouched.
- **`overwrite=True`.** Behaves like `room.add(..., accept=True)` and the per-item exit apis: rooms and areas are replaced, an explicit exit takes the new cost and requirement (as `exit.add`), an exit embedded in a room keeps its stored cost and requirement and only updates its `touid` (as `room.add`), flags are written as given, and an unexplored touid never replaces a known one.
- **`overwrite=False`.** Fills gaps only: a stored area is kept, a stored room keeps every field and gains only the flags it lacks, a stored exit keeps its cost and only fills an unexplored touid or a missing requirement, and a note is set only where there is none or it is empty.
- **Events.** No `room_changed` or `room_mismatch` is raised, so a batch does no change detection; use `room.add` for that. One `map_changed` with the counts is raised when a row changed.
- **Counts.** `areas`, `rooms`, `new_rooms`, `exits`, `new_exits`, `notes` and `skipped`. `exits` counts every exit written and `new_exits` those whose `(fromuid, dir)` was not stored before the batch, so `exits - new_exits` is the number of stored exits changed. A key repeated within a batch counts once.
- **Graph.** Updated after the commit from the merged values, so a view from `freeze()` taken before the batch never changes.

## APIs

All are `plugins.client.mapper:<name>`. Names follow [ADR-0004](../decisions/0004-api-names-are-resource-first-and-cmdq-is-renamed-mudcmds.md).

| API | Returns |
| :--- | :--- |
| `area.add(uid, name="", flags=(), details=None)`, `area.get(uid)`, `area.list()` | bool, dict or None, list |
| `area.remove(uid)` | the number of rooms removed, with their exits and notes |
| `room.add(room, accept=False)`, `room.get(uid)`, `room.remove(uid)` | bool, the room with `exits` and `note`, bool |
| `room.flag.add(uid, flag)`, `room.flag.remove(uid, flag)` | bool (False for an unknown room, or a flag not set) |
| `room.list(name=None, area=None, flag=None, limit=None)` | rooms; `name` is a case-insensitive substring |
| `room.list.unexplored(area=None)` | rooms with an exit whose `touid` is `-1` |
| `room.current.set(uid)`, `room.current.get()` | None, the uid or None |
| `room.note.set(uid, text)`, `room.note.get(uid)`, `room.note.remove(uid)` | bool, str or None, bool |
| `map.batch.add(areas=None, rooms=None, exits=None, notes=None, overwrite=True)` | the counts dict, or None when over `BATCH_LIMIT` |
| `exit.add(fromuid, dir, touid="-1", cost=1, requirement=None)`, `exit.remove(fromuid, dir)`, `exit.list(fromuid)` | bool, bool, list of dicts |
| `path.get(start, target, max_depth=None, portals=True, recalls=True)` | `{"start", "target", "cost", "steps": [{"fromuid", "touid", "dir", "cost", "requirement"}]}` or None |
| `requirement.register`, `requirement.unregister`, `movement.register`, `movement.unregister` | None |
| `walk.start(target, portals=True, recalls=True)`, `walk.restart()`, `walk.clear(reason="stopped")` | bool |
| `walk.get()` | `{state, target, steps, index, reroutes}`, state being `idle`, `searching`, `walking` or `stopped` |

## Events

| Event | Arguments |
| :--- | :--- |
| `ev_plugins.client.mapper_room_arrived` | `uid`, `previous` |
| `ev_plugins.client.mapper_room_changed` | `uid`, `new` |
| `ev_plugins.client.mapper_room_mismatch` | `uid`, `differences` |
| `ev_plugins.client.mapper_map_changed` | `areas`, `rooms`, `new_rooms`, `exits`, `new_exits`, `notes`, `skipped` |
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
| `find_limit` | 50 | the most rooms `find` lists, 0 for no limit |

## Commands

`#bp.client.mapper.find`, `goto`, `walkto`, `next`, `resume`, `stop`, `where`, `speedwalk`, `showroom`, `purge`, `note`, `accept` and `ignoreexits`. See [Mapper](../client/mapper.md).

An adapter's commands, added with `command.add.for.plugin`, appear under `#bp.client.mapper` in a help section named after the adapter. Their code, logs and errors belong to the adapter.

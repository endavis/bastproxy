---
title: "ADR-0021: The mapper owns the map and walking, and game plugins adapt it through callbacks"
description: The mapper plugin owns the map, pathfinding and walking; game plugins feed it rooms and register requirement and movement callbacks.
date: 2026-11-24
audience:
  - contributors
tags:
  - adr
---

# ADR-0021: The mapper owns the map and walking, and game plugins adapt it through callbacks

## Status

Accepted

## Context

Issue #754: bastproxy has no mapper, and the only mappers so far (the old Aardwolf mapper of bastproxy and the Aardwolf MUSHclient mapper) are Aardwolf-only. Rooms, exits and paths are not specific to one game. The issue called for a core plugin that is not required. The loader marks every `plugins.core` plugin as required, so the plugin is `plugins.client.mapper`: it loads at startup and can be unloaded.

## Decision

- **Split.** The mapper owns the map (areas, rooms, exits, notes), a Dijkstra pathfinder and a step-by-step walk engine. A game plugin is an adapter: it feeds rooms and exits, reports the current room and registers two callbacks.
- **Storage.** One sqlite database `map` per proxy home, created with `plugins.core.sqldb:database.add` (ADR-0014) and no `directory`, so the default plugin data directory applies. The tables follow the MUSHclient layout: `areas`, `rooms`, `exits`, `bookmarks`, `storage`. Exits from anywhere are exits from the virtual rooms `*` (portals) and `**` (recall). The Aardwolf `level` column becomes `requirement`, JSON text.
- **Requirement callback.** `requirement.register(owner_id, callback)` with `callback(requirement, exit_dict) -> bool`. The requirement is an opaque JSON value. It is only called for an exit that has one, once per distinct value in one search, on the event loop: a walk or command search asks it for every distinct requirement in the map before the search starts and gives the worker a lookup. A callback that raises blocks the exit. With no callback, exits are allowed.
- **Movement callback.** `movement.register(owner_id, callback)` with `callback(steps: list[dict]) -> list[str]`. A walk calls it with one step; `goto` calls it with the whole path, so a game can send a speedwalk. A callback that raises or returns bad data falls back to each step's direction. The most recent registration is active and an unloading owner's callbacks are dropped.
- **Arrival.** The adapter calls `room.current.set(uid)`. The mapper does not parse GMCP. It raises `ev_plugins.client.mapper_room_arrived` and gives the arrival to the walk in the same call.
- **Walking.** A walk sends the next step only when `room.current.set` confirms the last one. An arrival at the room the step left is ignored. An unexpected room is rerouted (setting `reroute`, at most 3 times) or stops the walk. `walk.restart` resumes a stopped walk. `walk.start` and `walk.restart` return True once a search has started, the walk is `searching` and a missing path arrives later as `walk_failed`, with the extra reasons `moved during search` and `search failed`. A walk starts only from `walk.start` or a command, and a MUD disconnect stops it. `walk.start` and `path.get` take `portals` and `recalls` (default True) to leave out the exits from `*` and `**`; the walk keeps them for reroutes, and `walkto` and `next` search without them unless `-p` is given. (amended 2026-11-25 by #798)
- **Searching.** Walks and the commands `find`, `goto`, `where`, `speedwalk`, `walkto`, `next` and `resume` run the pathfinder with `asyncio.to_thread` on a copy-on-write view of the graph, queued with `libs.asynch:task.add`. Commands answer at once and report the result in a later line.
- **Change detection.** `room.add` on a stored room raises `ev_plugins.client.mapper_room_mismatch` when something differs. Name, terrain, coordinates and details are updated and reported. A stored non-empty area and the `touid` of an existing exit are kept when the update contradicts them, and reported until the user accepts them with `accept` (`room.add(..., accept=True)`). A new direction is added and reported. A stored-only exit is reported only when it is a plain direction (`PLAIN_DIRECTIONS`), never a custom exit. A room with the `ignoreexits` flag, a user-owned flag kept by `room.add`, skips the exit comparison. Stored exits are never deleted by `room.add` and an unexplored target (`-1`) never overwrites a known one. `accept` removes the stale plain exits; `purge` stays for a replaced area. (amended 2026-11-25 by #795, #796, #797)
- **Batch writes.** `map.batch.add` writes areas, rooms (with embedded exits), exits and notes in one synchronous call and one sqlite transaction (`Sqldb.transaction()`), at most 1000 rows per call; the caller slices and yields between calls. It reads the stored rows once per table and merges in Python, with `overwrite=True` as `room.add` with `accept=True` and the per-item exit apis do (flags are written as given) (amended 2026-11-25 by #796) and `overwrite=False` to fill gaps only. It raises one `ev_plugins.client.mapper_map_changed` with counts instead of `room_changed` and `room_mismatch` per room, and updates the graph after the commit.
- **Commands.** An adapter may add its commands under `client.mapper` through `plugins.core.commands:command.add.for.plugin` ([ADR-0024](0024-plugins-add-commands-under-another-plugins-name-only-when-that-plugin-accepts-them.md)); the mapper sets `accepts_command_extensions_f`. (amended 2026-11-26 by #834)
- **Names.** The API names follow ADR-0004's closed action list, which has no `find`, `search`, `resume`, `purge` or `stop`: `path.get`, `room.list` and `room.list.unexplored`, `walk.restart`, `walk.clear`, `area.remove`, `room.flag.add` and `room.flag.remove`. Commands keep the issue's names: `find`, `goto`, `walkto`, `next`, `resume`, `stop`, `where`, `speedwalk`, `showroom`, `purge`, `note`, `accept`, `ignoreexits`. (amended 2026-11-25 by #796, #797, #799)

## Rationale

Rooms, exits, costs and paths are the same in every game, while requirements, portals and movement commands are not. Keeping the first in one plugin and the second in callbacks lets every game plugin reuse the pathfinder and the walk engine. Stepping on confirmed arrival keeps the proxy from walking the character blindly, and never starting a walk on its own keeps it from moving a character the user did not tell to move.

## Alternatives Considered

- **Fixed level and tier fields on exits.** Rejected: they are Aardwolf rules. A JSON requirement checked by a game callback serves any game.
- **The mapper parsing GMCP.** Rejected: GMCP room data is game specific. `room.current.set` keeps the mapper independent of it.
- **Walking by sending the whole path.** Rejected for walks: it cannot stop or reroute on an unexpected room. `goto` still does it, through the movement callback.
- **A lock around the graph.** Rejected: every write on the loop would wait for the whole search.
- **A full snapshot per search.** Rejected: copying every room and exit on the loop for every search costs more than copying the two outer dicts once after a write.
- **Requirement callbacks in the worker thread.** Rejected: adapters call the API and log, and neither is thread-safe.
- **An awaitable `path.get`.** Rejected: ADR-0004 has no fitting action word, and the walks and commands are the long searches.
- **Loading the graph in a thread.** Rejected for now: the database connection belongs to the loop thread, and an adapter may write right after load. Possible follow-up.
- **A begin/commit pair for batches.** Rejected: it leaves a transaction open across the caller's awaits on the shared connection, where every other statement would nest into it.
- **A core plugin.** Rejected: the loader forces core plugins to be required.

## Consequences

- A game plugin needs an adapter before the mapper is useful. Importing an existing MUSHclient database is adapter work.
- The depth limit prunes by step count, so a target whose cheapest route is longer than the limit is unreachable even when a costlier, shorter route exists.
- The map is held in memory as well as in the database, and written to both.
- `path.get` still searches on the event loop, and the graph is still loaded synchronously at plugin load.
- `walk.start` and `walk.restart` no longer report a missing path in their return value; it arrives as `walk_failed`.

## Related Issues

- Issue #754: add a mapper plugin with pathfinding and walking
- Issue #756: run mapper path searches off the event loop
- Issue #760: write many mapper rooms and exits in one transaction
- Issue #762: recapturing a room keeps its exits' requirement and cost
- Issue #766: web pages for the area map and room lookup
- Issue #795: a room update never reports a custom exit as removed
- Issue #796: a room update keeps the stored area and exits until accepted
- Issue #797: per-room ignoreexits flag
- Issue #798: walkto and next avoid portals unless asked
- Issue #799: next, exact find and speedwalk
- Issue #800: find defaults, showroom details and the find_limit setting
- Issue #834: let a game adapter add its commands under the core mapper's namespace

## Related Documentation

- [Mapper system](../claude/mapper_system.md)
- [Mapper](../client/mapper.md)
- [ADR-0004](0004-api-names-are-resource-first-and-cmdq-is-renamed-mudcmds.md)
- [ADR-0024](0024-plugins-add-commands-under-another-plugins-name-only-when-that-plugin-accepts-them.md)
- [ADR-0014](0014-plugins-add-sqldb-databases-through-databaseadd-with-plain-data-definitions.md)

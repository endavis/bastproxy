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
- **Requirement callback.** `requirement.register(owner_id, callback)` with `callback(requirement, exit_dict) -> bool`. The requirement is an opaque JSON value. It is only called for an exit that has one, once per distinct value in one search. A callback that raises blocks the exit. With no callback, exits are allowed.
- **Movement callback.** `movement.register(owner_id, callback)` with `callback(steps: list[dict]) -> list[str]`. A walk calls it with one step; `goto` calls it with the whole path, so a game can send a speedwalk. A callback that raises or returns bad data falls back to each step's direction. The most recent registration is active and an unloading owner's callbacks are dropped.
- **Arrival.** The adapter calls `room.current.set(uid)`. The mapper does not parse GMCP. It raises `ev_plugins.client.mapper_room_arrived` and gives the arrival to the walk in the same call.
- **Walking.** A walk sends the next step only when `room.current.set` confirms the last one. An arrival at the room the step left is ignored. An unexpected room is rerouted (setting `reroute`, at most 3 times) or stops the walk. `walk.restart` resumes a stopped walk. A walk starts only from `walk.start` or a command, and a MUD disconnect stops it.
- **Change detection.** `room.add` on a stored room raises `ev_plugins.client.mapper_room_mismatch` when the area changed or a known exit target differs or exists on one side only. It never deletes stored exits and an unexplored target (`-1`) never overwrites a known one. Purging is left to the adapter or the user.
- **Names.** The API names follow ADR-0004's closed action list, which has no `find`, `search`, `resume`, `purge` or `stop`: `path.get`, `room.list` and `room.list.unexplored`, `walk.restart`, `walk.clear` and `area.remove`. Commands keep the issue's names: `find`, `goto`, `walkto`, `resume`, `stop`, `where`, `showroom`, `purge`, `note`.

## Rationale

Rooms, exits, costs and paths are the same in every game, while requirements, portals and movement commands are not. Keeping the first in one plugin and the second in callbacks lets every game plugin reuse the pathfinder and the walk engine. Stepping on confirmed arrival keeps the proxy from walking the character blindly, and never starting a walk on its own keeps it from moving a character the user did not tell to move.

## Alternatives Considered

- **Fixed level and tier fields on exits.** Rejected: they are Aardwolf rules. A JSON requirement checked by a game callback serves any game.
- **The mapper parsing GMCP.** Rejected: GMCP room data is game specific. `room.current.set` keeps the mapper independent of it.
- **Walking by sending the whole path.** Rejected for walks: it cannot stop or reroute on an unexpected room. `goto` still does it, through the movement callback.
- **A core plugin.** Rejected: the loader forces core plugins to be required.

## Consequences

- A game plugin needs an adapter before the mapper is useful. Importing an existing MUSHclient database is adapter work.
- The depth limit prunes by step count, so a target whose cheapest route is longer than the limit is unreachable even when a costlier, shorter route exists.
- The map is held in memory as well as in the database, and written to both.

## Related Issues

- Issue #754: add a mapper plugin with pathfinding and walking

## Related Documentation

- [Mapper system](../claude/mapper_system.md)
- [Mapper](../client/mapper.md)
- [ADR-0004](0004-api-names-are-resource-first-and-cmdq-is-renamed-mudcmds.md)
- [ADR-0014](0014-plugins-add-sqldb-databases-through-databaseadd-with-plain-data-definitions.md)

---
title: Mapper
description: Find rooms, show paths and walk to a room with the mapper plugin, which game plugins feed with rooms and exits
audience:
  - users
  - contributors
tags:
  - client
  - mapper
---

# Mapper

The `plugins.client.mapper` plugin stores a map of rooms, exits and areas, finds the cheapest path between two rooms and walks it. It does not know any game: a game plugin has to feed it rooms and exits and tell it where the character is. Without one the map is empty. The map is a sqlite database under the proxy home, one per proxy home. How a game plugin does this, the APIs and the events are in the [mapper system](../claude/mapper_system.md) page, and the design is in [ADR-0021](../decisions/0021-the-mapper-owns-the-map-and-walking-and-game-plugins-adapt-it-through-callbacks.md).

The plugin can be unloaded. Its commands are `#bp.client.mapper.<name>`.

## Commands

| Command | What it does |
| :--- | :--- |
| `find <text> [-a area] [-f flag] [-u]` | Lists rooms whose name has the text (case-insensitive), with uid, name, area and the steps from the current room. `-a` and `-f` filter by area and flag, `-u` lists rooms with unexplored exits. At most 50 are shown. |
| `goto <uid>` | Sends the whole path to the MUD at once, through the game plugin's movement callback when it has one. |
| `walkto <uid>` | Walks to the room one step at a time. Each step is sent after the previous one is confirmed. |
| `stop` | Stops the walk and keeps its target. |
| `resume` | Walks on to the target of a stopped walk, from the current room. |
| `where <uid>` | Shows the directions and cost of the path without moving. |
| `showroom [uid]` | Shows a room (default the current room): name, area, terrain, coordinates, flags, note and exits. |
| `purge -r <uid>` or `purge -a <area>` | Removes a room, or an area with its rooms. |
| `accept [uid]` | Accepts the area and exit changes a room update held (default the current room), and removes the plain exits that went stale. |
| `ignoreexits [uid] [-c]` | Sets the `ignoreexits` flag on a room (default the current room): its exits are no longer compared with the game. `-c` clears it. |
| `note [uid] [text...] [-d]` | Shows, sets or deletes a note. The first word is the room uid when that room is stored, otherwise the current room is used and every word is the note. |

Example, after a game plugin has filled the map:

```text
#bp.client.mapper.find fountain -a example
#bp.client.mapper.walkto 1234
#bp.client.mapper.stop
#bp.client.mapper.resume
```

## Room changes

When the game sends a stored room again, its name, terrain, coordinates and details are updated. A different area and exits that contradict stored ones are kept and reported (the `room_mismatch` event) until you run `accept`; a stored custom exit is never reported as removed. `accept` is gentler than `purge -r`, which deletes the room, its note and every exit leading to it. Use `purge -a` for a replaced area. For a room whose exits vary, set `ignoreexits`; list those rooms with `find -f ignoreexits`.

## Importing maps

A game plugin can import a whole map in batches with `map.batch.add`, in slices of up to 1000 rows. Importing in fill mode (`overwrite=False`) fills gaps only and never overrides rooms, exits and notes the mapper already holds. An import raises one `map_changed` event per batch instead of one event per room.

## Walking

`find`, `goto`, `where`, `walkto` and `resume` search the path in the background. Each answers at once with a line such as "finding a path to X", and its result (the table, the path, or "no path") comes as a separate line after the search.

A walk only starts when you run `walkto` (or a plugin calls `walk.start`); it never starts by itself. If the character ends up in a room the walk did not expect, the mapper finds a new path from there, up to 3 times, and then stops. A MUD disconnect stops a walk. `stop` keeps the target so `resume` can continue.

## Web pages

When the web server is enabled (see the [web server](../web-server.md) page) and you are logged in, the mapper serves four pages under `/client/mapper`. They are read only. The index at `/` lists Areas and Find rooms; the area map and room pages are reached by links, because they need `?uid=`.

| Page | What it shows |
| :--- | :--- |
| `/client/mapper` | The areas with their room and unexplored counts. Click an area to see its map. Sort and filter the columns. |
| `/client/mapper/area?uid=<area>` | A map of the area, one picture per z level. Rooms are boxes (hover for the uid and name, click for the room page); lines are exits. Blue stubs leave the area, arrows go up or down, dashed orange stubs are unexplored exits. The current room is highlighted, a dashed border marks a noportal room and a dark red fill a norecall room. |
| `/client/mapper/room?uid=<uid>` | A room's name, area, terrain, coordinates, flags and note, and a table of its exits with links to the rooms they lead to. |
| `/client/mapper/find?name=<text>` | Rooms whose name has the text, with links to the room and its area. Leave `name` empty to list every room. |

An unknown area or room gives a 404 page and a missing `uid` a 400 page.

## Paths

The path is the cheapest by exit cost. Exits from anywhere (portals and recall) are used when the room allows them, and the game plugin decides which exits the character may take. The `maxdepth` setting limits the number of steps: a room whose cheapest route is longer than the limit is reported as unreachable, even if a costlier but shorter route exists.

## Settings

Set with `#bp.client.mapper.set <name> <value>`.

| Setting | Default | Meaning |
| :--- | :--- | :--- |
| `maxdepth` | 300 | the most steps a path may have |
| `shownotes` | True | show a room's note when entering it |
| `reroute` | True | find a new path when a walk ends up elsewhere |

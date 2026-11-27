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
| `find <text> [-e] [-a [area]] [-f flag] [-u]` | Lists rooms whose name has the text (case-insensitive) as a table with the columns `#` (the row number), uid, name, area and the steps from the current room. `-e` matches the whole name instead (still case-insensitive). `-a area` and `-f flag` filter by area and flag; a bare `-a` means the current room's area, and must come after the text (`find temple -a`), because `find -a temple` reads `temple` as the area. `-u` lists rooms with unexplored exits. At most `find_limit` rooms are shown (default 50, 0 for no limit). The list is kept for `next`. A find with no match keeps the previous list. |
| `goto <uid>` | Sends the whole path to the MUD at once, through the game plugin's movement callback when it has one. |
| `walkto <uid> [-n]` | Walks to the room one step at a time. Each step is sent after the previous one is confirmed. It uses the portal and recall exits (the exits from `*` and `**`) unless `-n` (`--noportals`) is given. |
| `next [index] [-n]` | Walks to the next unvisited room of the last `find`, like `walkto` (portals and recalls unless `-n`). `next 3` walks to row 3 of the table and the next `next` goes to row 4. It fails at the end of the list, with an index out of range, or before any `find`. |
| `stop` | Stops the walk and keeps its target. |
| `resume` | Walks on to the target of a stopped walk, from the current room. |
| `where <uid>` | Shows the directions and cost of the path without moving. |
| `speedwalk <start> <target>` | Shows the compressed path between two stored rooms, such as `A to D, cost 3: 2ne`. Runs of plain directions are compressed (`3n2e`); a custom exit, such as `enter portal` or a portal or recall exit, is its own segment, and segments are joined with the proxy's command separator: `2n\|enter portal\|2es` (shown with `\|` here because the table uses the same character). It uses portals and recalls, like `where`. |
| `showroom [uid]` | Shows a room (default the current room): name, area, terrain, coordinates, flags, details, note and exits. The details are one `key: value` line each, or `(none)`. |
| `purge -r <uid>` or `purge -a <area>` | Removes a room, or an area with its rooms. `-r` always needs a uid: purge deletes the room, its note and every exit leading to it, so it never defaults to the current room. |
| `accept [uid]` | Accepts the area and exit changes a room update held (default the current room), and removes the plain exits that went stale. |
| `ignoreexits [uid] [-c]` | Sets the `ignoreexits` flag on a room (default the current room): its exits are no longer compared with the game. `-c` clears it. |
| `note [uid] [text...] [-d]` | Shows, sets or deletes a note. The first word is the room uid when that room is stored, otherwise the current room is used and every word is the note. |

Example, after a game plugin has filled the map:

```text
#bp.client.mapper.find fountain -a example
#bp.client.mapper.walkto 1234
#bp.client.mapper.find temple -a
#bp.client.mapper.next
#bp.client.mapper.stop
#bp.client.mapper.resume
```

A game adapter can add its own commands under `#bp.client.mapper`. They are listed in a section named after the adapter, such as `aardwolf.mapper`, and the adapter's old `#bp.<adapter>.*` names keep working.

## Room changes

When the game sends a stored room again, its name, terrain, coordinates and details are updated. A different area and exits that contradict stored ones are kept and reported (the `room_mismatch` event) until you run `accept`; a stored custom exit is never reported as removed. `accept` is gentler than `purge -r`, which deletes the room, its note and every exit leading to it. Use `purge -a` for a replaced area. For a room whose exits vary, set `ignoreexits`; list those rooms with `find -f ignoreexits`.

## Importing maps

A game plugin can import a whole map in batches with `map.batch.add`, in slices of up to 1000 rows. Importing in fill mode (`overwrite=False`) fills gaps only and never overrides rooms, exits and notes the mapper already holds. An import raises one `map_changed` event per batch instead of one event per room.

## Walking

`find`, `goto`, `where`, `speedwalk`, `walkto`, `next` and `resume` search the path in the background. Each answers at once with a line such as "finding a path to X", and its result (the table, the path, or "no path") comes as a separate line after the search.

A walk only starts when you run `walkto` or `next` (or a plugin calls `walk.start`); it never starts by itself. If the character ends up in a room the walk did not expect, the mapper finds a new path from there, up to 3 times, and then stops. A MUD disconnect stops a walk. `stop` keeps the target so `resume` can continue.

## Web pages

When the web server is enabled (see the [web server](../web-server.md) page) and you are logged in, the mapper serves four pages under `/client/mapper`. They are read only. The index at `/` lists Areas and Find rooms; the area map and room pages are reached by links, because they need `?uid=`.

| Page | What it shows |
| :--- | :--- |
| `/client/mapper` | The areas with their room and unexplored counts. Click an area to see its map. Sort and filter the columns. |
| `/client/mapper/area?uid=<area>` | A map of the area, one picture per z level. Rooms sit at their stored coordinates; when those put rooms in the same spot or are missing, the map is laid out from the exits instead. Rooms are boxes (hover for the uid and name, click for the room page); lines are exits. Blue stubs leave the area, arrows go up or down, dashed orange stubs are unexplored exits. The current room is highlighted, a dashed border marks a noportal room and a dark red fill a norecall room. |
| `/client/mapper/room?uid=<uid>` | A room's name, area, terrain, coordinates, flags and note, and a table of its exits with links to the rooms they lead to. |
| `/client/mapper/find?name=<text>` | Rooms whose name has the text, with links to the room and its area. Leave `name` empty to list every room. |

An unknown area or room gives a 404 page and a missing `uid` a 400 page.

## Paths

The path is the cheapest by exit cost. Exits from anywhere (portals and recall) are used when the room allows them, and the game plugin decides which exits the character may take. A portal is an exit from the virtual room `*` and a recall an exit from `**`; a room's own custom exit, such as `enter portal`, is neither. `walkto` and `next` use them unless `-n` is given, and `goto`, `where`, `speedwalk` and the step counts of `find` always use them. A reroute and `resume` search the way the walk started, with or without them. The `maxdepth` setting limits the number of steps: a room whose cheapest route is longer than the limit is reported as unreachable, even if a costlier but shorter route exists.

## Settings

Set with `#bp.client.mapper.set <name> <value>`.

| Setting | Default | Meaning |
| :--- | :--- | :--- |
| `maxdepth` | 300 | the most steps a path may have |
| `shownotes` | True | show a room's note when entering it |
| `reroute` | True | find a new path when a walk ends up elsewhere |
| `find_limit` | 50 | the most rooms `find` lists, 0 for no limit |

## Changes from the old plugin

Where this plugin deliberately differs from the old Aardwolf mapper:

- `walk` became `walkto`, which walks step by step. It first avoided portals and recalls (`-p` allowed them); that reverses in #837: they are used by default and `-n` avoids them, for a walk that must not skip rooms.
- `next` walks like `walkto`. The old one used `goto` with portals; it now walks step by step so that `stop` and `resume` apply.
- `spw` became `speedwalk <start> <target>`. The old one glued custom exits into the string (`2nenter portal2es`), which cannot be sent; the new one joins them with the command separator.
- `find -e` is case-insensitive. The old exact search was case-sensitive only as a side effect, and room names are typed by hand.
- `area` became `find -a`, and a bare `-a` means the current area.
- `purgeroom` with no argument used to purge the current room. `purge -r` still requires a uid, because purge is destructive.
- `showroom` shows the room's details. The old "Ignore Exits Mismatch" field is the `ignoreexits` flag in the flags line.
- A room's note on entry stays a one-line `Note:`.
- The old `find` was unlimited. It is limited by the `find_limit` setting (default 50, 0 for no limit).

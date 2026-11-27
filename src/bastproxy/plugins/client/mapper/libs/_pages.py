# Project: bastproxy
# Filename: plugins/client/mapper/libs/_pages.py
#
# File Description: builders for the mapper web pages: area svg, link cells, table paging
#
# By: Bast
"""Pure builders for the mapper web pages (#766).

This module imports nothing from other plugins, so it is tested on its own. The area map is
drawn from a frozen graph and plain room dicts, so ``draw_area_svg`` is safe to run in a
worker thread: it never calls an API or the database.

Link cells are the dicts ``{"text": str, "href": str}`` that ``plugins.core.web`` renders as
links in a table; the href is a same-origin absolute path.
"""

import hashlib
import html
import json
import math
import re
import textwrap
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from itertools import count
from typing import Any
from urllib.parse import urlencode

from ._graph import MapGraph
from ._schema import NOPORTAL_FLAG, NORECALL_FLAG, UNKNOWN_UID

# the grid: one room per PITCH, drawn as a BOX square, with STUB long exit stubs
PITCH = 88
BOX = 32
STUB = 18
MARGIN = 48
LABEL = 22
# the longest text drawn in or under a room box; longer text is cut with an ellipsis
NAME_CHARS = 14
NUMBER_CHARS = 5
MARKER_CHARS = 5
# the details panel: the line width in characters, the line height and character width in px
PANEL_CHARS = 40
PANEL_LINE = 16
_PANEL_CHAR_WIDTH = 8
_PANEL_PAD = 16
# the fill of a room with no terrain, and of the terrains no adapter colours
EMPTY_TERRAIN = "#222"
FALLBACK_PALETTE = (
    "#2e5e8c",
    "#3d7a4a",
    "#6b4f8a",
    "#8a6a2e",
    "#2e7f7f",
    "#7a3d5c",
    "#4f6b2e",
    "#4a4a8c",
    "#7f5a3c",
    "#2f6f5f",
    "#5c5c5c",
    "#3c6e9e",
)
COLOR_RE = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})")

_UP = "u"
_DOWN = "d"
# the svg offset of an exit direction (y grows downwards, as the room coordinates do)
VECTORS: dict[str, tuple[int, int]] = {
    "n": (0, -1),
    "s": (0, 1),
    "e": (1, 0),
    "w": (-1, 0),
    "ne": (1, -1),
    "nw": (-1, -1),
    "se": (1, 1),
    "sw": (-1, 1),
}

# characters that cannot appear in an XML 1.0 document, not even escaped
# code points an XML 1.0 document can hold (the Char production), as inclusive ranges
_XML_CHAR_RANGES = (
    (0x9, 0xA),
    (0xD, 0xD),
    (0x20, 0xD7FF),
    (0xE000, 0xFFFD),
    (0x10000, 0x10FFFF),
)


def _xml_char(char: str) -> bool:
    """Return True when ``char`` may appear in an XML 1.0 document."""
    code = ord(char)
    return any(low <= code <= high for low, high in _XML_CHAR_RANGES)


_SVG_STYLE = (
    "rect.bg{fill:#000}.level-label{fill:#999;font:12px monospace}"
    ".room rect{stroke:#888;stroke-width:1.5}"
    ".room.norecall rect{stroke:#c33}"
    ".room.unexplored rect{stroke:#e90}.room.noportal rect{stroke-dasharray:4 2}"
    ".room.current rect{stroke:#fff;stroke-width:3}"
    ".room.selected rect{stroke:#4c4;stroke-width:3}"
    ".room text{font:10px monospace;text-anchor:middle}"
    ".room text.name{fill:#ccc;paint-order:stroke;stroke:#000;stroke-width:3}"
    ".panel text{fill:#ccc;font:12px monospace}.panel a text{fill:#6cf}"
    ".link{stroke:#888;stroke-width:1.5}.leaves{stroke:#6cf;stroke-width:1.5;fill:none}"
    "circle.leaves{fill:#6cf}.unexplored-stub{stroke:#e90;stroke-width:1.5;stroke-dasharray:3 2}"
    ".updown{fill:#6cf;font:11px monospace}.updown.unexplored{fill:#e90}"
)

AREA_COLUMNS: list[dict[str, str]] = [
    {"name": "uid", "label": "Area", "type": "text"},
    {"name": "name", "label": "Name", "type": "text"},
    {"name": "rooms", "label": "Rooms", "type": "int"},
    {"name": "unexplored", "label": "Unexplored", "type": "int"},
]
EXIT_COLUMNS: list[dict[str, str]] = [
    {"name": "dir", "label": "Exit", "type": "text"},
    {"name": "to", "label": "To", "type": "text"},
    {"name": "name", "label": "Name", "type": "text"},
    {"name": "cost", "label": "Cost", "type": "int"},
    {"name": "requirement", "label": "Requires", "type": "text"},
]
FIND_COLUMNS: list[dict[str, str]] = [
    {"name": "uid", "label": "Room", "type": "text"},
    {"name": "name", "label": "Name", "type": "text"},
    {"name": "area", "label": "Area", "type": "text"},
    {"name": "terrain", "label": "Terrain", "type": "text"},
]


def xml_text(text: Any) -> str:
    """Return ``text`` safe inside svg text and attributes.

    Characters XML cannot hold (control characters such as ESC, lone surrogates) are dropped,
    then ``& < > "`` and ``'`` are escaped.
    """
    return html.escape("".join(c for c in str(text) if _xml_char(c)), quote=True)


def valid_color(value: Any) -> bool:
    """Return True when ``value`` is a ``#rgb`` or ``#rrggbb`` colour string."""
    return isinstance(value, str) and COLOR_RE.fullmatch(value) is not None


def terrain_color(terrain: str, colors: Mapping[str, str] | None = None) -> str:
    """Return the fill colour of a terrain.

    The adapter's mapping wins when it holds a valid colour; an empty terrain is
    ``EMPTY_TERRAIN``; any other terrain gets a palette colour from the first byte of its
    sha256, so it is the same on every run (never ``hash()``, which is seeded per process).
    """
    if colors is not None:
        value = colors.get(terrain)
        if valid_color(value):
            return str(value)
    if not terrain:
        return EMPTY_TERRAIN
    digest = hashlib.sha256(terrain.encode("utf-8", "surrogatepass")).digest()
    return FALLBACK_PALETTE[digest[0] % len(FALLBACK_PALETTE)]


def text_color(background: str) -> str:
    """Return ``#000`` or ``#fff``, whichever reads better on the ``background`` colour."""
    digits = background[1:]
    if len(digits) == 3:
        digits = "".join(c * 2 for c in digits)
    channels = []
    for i in (0, 2, 4):
        value = int(digits[i : i + 2], 16) / 255
        channels.append(value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4)
    luminance = 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
    return "#000" if luminance > 0.179 else "#fff"


def _cut(text: str, limit: int) -> str:
    """Return ``text``, cut to ``limit`` characters with a final ellipsis when it is longer."""
    return text if len(text) <= limit else text[: limit - 1] + "…"


def href(path: str, **params: str) -> str:
    """Return ``path`` with the params as a query string, percent-encoded and not html-escaped."""
    return f"{path}?{urlencode(params)}" if params else path


def link_cell(text: str, path: str, **params: str) -> dict[str, str]:
    """Return a link cell: the text shown and the url it goes to."""
    return {"text": text, "href": href(path, **params)}


def _cell_text(cell: Any) -> str:
    if isinstance(cell, Mapping):
        return str(cell["text"])
    return "" if cell is None else str(cell)


def _number(cell: Any) -> float | None:
    try:
        number = float(_cell_text(cell))
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def escape_rows(rows: Sequence[Sequence[Any]], escape: Callable[[str], str]) -> list[list[Any]]:
    """Return the rows with the text of every cell colour-code escaped.

    The web plugin converts cell text with the colour converter, so MUD text must be escaped
    first (the ``colorcode.escape`` api). Numbers and ``None`` pass through.
    """
    result: list[list[Any]] = []
    for row in rows:
        cells: list[Any] = []
        for cell in row:
            if isinstance(cell, Mapping):
                cells.append({"text": escape(str(cell["text"])), "href": cell["href"]})
            elif isinstance(cell, str):
                cells.append(escape(cell))
            else:
                cells.append(cell)
        result.append(cells)
    return result


def page_rows(
    rows: Sequence[Sequence[Any]],
    columns: Sequence[Mapping[str, str]],
    *,
    sort: str | None,
    descending: bool,
    filters: Mapping[str, Any],
    offset: int,
    count: int,
) -> tuple[list[Sequence[Any]], int]:
    """Filter, sort and page ``rows`` the way a table request asks.

    A text filter matches a case-insensitive part of the cell text (the text of a link cell),
    an int or float filter matches an equal number. A text sort ignores case, a number sort
    puts cells without a number last. Returns the page and the number of rows that matched.
    """
    index = {column["name"]: i for i, column in enumerate(columns)}
    kinds = {column["name"]: column.get("type", "text") for column in columns}
    kept: list[Sequence[Any]] = []
    for row in rows:
        for name, wanted in filters.items():
            if name not in index:
                continue
            cell = row[index[name]]
            if kinds[name] == "text":
                if str(wanted).casefold() not in _cell_text(cell).casefold():
                    break
            elif _number(cell) != float(wanted):
                break
        else:
            kept.append(row)
    if sort is not None and sort in index:
        position = index[sort]
        if kinds[sort] == "text":
            kept.sort(key=lambda r: _cell_text(r[position]).casefold(), reverse=descending)
        else:
            numbered = [r for r in kept if _number(r[position]) is not None]
            blank = [r for r in kept if _number(r[position]) is None]
            numbered.sort(key=lambda r: _number(r[position]) or 0.0, reverse=descending)
            kept = numbered + blank
    return kept[offset : offset + count], len(kept)


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


# the directions that place a neighbour, in the order the layout tries them: x, y, z steps
_STEPS: dict[str, tuple[int, int, int]] = {
    **{name: (dx, dy, 0) for name, (dx, dy) in VECTORS.items()},
    _UP: (0, 0, 1),
    _DOWN: (0, 0, -1),
}
_DIR_ORDER = {name: index for index, name in enumerate(_STEPS)}
_OPPOSITE = {
    name: next(o for o, v in _STEPS.items() if v == tuple(-c for c in step))
    for name, step in _STEPS.items()
}
_UID_PARTS = re.compile(r"(\d+)")


def _uid_key(uid: str) -> tuple[tuple[int, int, str], ...]:
    """Sort key for a uid: digit runs compare as numbers, so ``2`` comes before ``10``."""
    return tuple(
        (0, int(part), "") if part.isdigit() else (1, 0, part)
        for part in _UID_PARTS.split(uid)
        if part
    )


def _stored_positions(rooms: Sequence[Mapping[str, Any]]) -> dict[str, tuple[int, int, int]] | None:
    """Return the stored ``(x, y, z)`` of every room, or None when they do not spread the rooms.

    The stored coordinates are usable when, on every z level, every room has an int x and y
    and no two rooms share an ``(x, y)``.
    """
    result: dict[str, tuple[int, int, int]] = {}
    seen: set[tuple[int, int, int]] = set()
    for room in rooms:
        x, y = room.get("x"), room.get("y")
        if (
            not isinstance(x, int)
            or not isinstance(y, int)
            or isinstance(x, bool)
            or isinstance(y, bool)
        ):
            return None
        cell = (x, y, _int(room.get("z")))
        if cell in seen:
            return None
        seen.add(cell)
        result[str(room["uid"])] = cell
    return result


def _free_cell(
    target: tuple[int, int, int], taken: set[tuple[int, int, int]]
) -> tuple[int, int, int]:
    """Return ``target`` when free, else the nearest free cell on its level.

    Nearest is by squared distance, then smaller dy, then smaller dx.
    """
    if target not in taken:
        return target
    tx, ty, tz = target
    for radius in count(1):
        offsets = sorted(
            (
                (dx, dy)
                for dx in range(-radius, radius + 1)
                for dy in range(-radius, radius + 1)
                if dx * dx + dy * dy <= radius * radius
            ),
            key=lambda d: (d[0] * d[0] + d[1] * d[1], d[1], d[0]),
        )
        for dx, dy in offsets:
            if (tx + dx, ty + dy, tz) not in taken:
                return tx + dx, ty + dy, tz
    raise AssertionError("unreachable")  # pragma: no cover


def _exit_layout(
    rooms: Sequence[Mapping[str, Any]], graph: MapGraph, current: str | None
) -> dict[str, tuple[int, int, int]]:
    """Lay the rooms out from their in-area exits, breadth first.

    Neighbours are one step away in the exit's direction (a reverse edge places the source at
    the target minus the vector). A taken cell sends the room to the nearest free cell. Each
    part the exits do not connect starts at its lowest uid, two columns right of the parts
    before it.
    """
    uids = {str(r["uid"]) for r in rooms}
    edges: dict[str, list[tuple[int, str, tuple[int, int, int]]]] = {u: [] for u in uids}
    for uid in uids:
        for exit_ in graph.exits_from(uid):
            step = _STEPS.get(exit_.dir)
            if step is None or exit_.touid not in uids or exit_.touid == uid:
                continue
            back = tuple(-c for c in step)
            edges[uid].append((_DIR_ORDER[exit_.dir], exit_.touid, step))
            edges[exit_.touid].append(
                (_DIR_ORDER[_OPPOSITE[exit_.dir]], uid, (back[0], back[1], back[2]))
            )
    placed: dict[str, tuple[int, int, int]] = {}
    taken: set[tuple[int, int, int]] = set()
    pending = sorted(uids, key=_uid_key)
    starts = [current] if current in uids and current is not None else []
    while len(placed) < len(uids):
        if starts:
            start = starts.pop()
            origin = (0, 0, 0)
        else:
            start = next(u for u in pending if u not in placed)
            origin = (max((c[0] for c in placed.values()), default=-2) + 2, 0, 0)
        cell = _free_cell(origin, taken)
        placed[start] = cell
        taken.add(cell)
        queue = deque([start])
        while queue:
            uid = queue.popleft()
            ux, uy, uz = placed[uid]
            for _order, other, (dx, dy, dz) in sorted(
                edges[uid], key=lambda e: (e[0], _uid_key(e[1]))
            ):
                if other in placed:
                    continue
                cell = _free_cell((ux + dx, uy + dy, uz + dz), taken)
                placed[other] = cell
                taken.add(cell)
                queue.append(other)
    return placed


def _positions(
    rooms: Sequence[Mapping[str, Any]], graph: MapGraph, current: str | None
) -> dict[str, tuple[int, int, int]]:
    """Return ``{uid: (x, y, z)}`` for drawing: stored coordinates when they spread the rooms.

    Otherwise the whole area, z included, is laid out from its exits (``_exit_layout``).
    """
    stored = _stored_positions(rooms)
    if stored is not None:
        return stored
    return _exit_layout(rooms, graph, current)


def _stub(cx: int, cy: int, vector: tuple[int, int], css: str) -> str:
    """A short line leaving a room box in the direction of ``vector``."""
    dx, dy = vector
    half = BOX // 2
    x1, y1 = cx + dx * half, cy + dy * half
    x2, y2 = x1 + dx * STUB, y1 + dy * STUB
    return f"<line class='{css}' x1='{x1}' y1='{y1}' x2='{x2}' y2='{y2}'/>"


def _level(
    z: int,
    rooms: Sequence[Mapping[str, Any]],
    by_uid: Mapping[str, Mapping[str, Any]],
    graph: MapGraph,
    current: str | None,
    room_path: str | None,
    pos: Mapping[str, tuple[int, int, int]],
    area_uid: str = "",
    area_path: str | None = None,
    selected: str | None = None,
    terrain_colors: Mapping[str, str] | None = None,
) -> tuple[str, int, int]:
    """Draw one z level as a nested svg body: the svg text without its position, width, height."""
    xs = [pos[str(r["uid"])][0] for r in rooms]
    ys = [pos[str(r["uid"])][1] for r in rooms]
    minx, miny = min(xs), min(ys)
    width = (max(xs) - minx) * PITCH + 2 * MARGIN
    height = (max(ys) - miny) * PITCH + 2 * MARGIN + LABEL

    def centre(room: Mapping[str, Any]) -> tuple[int, int]:
        x, y, _z = pos[str(room["uid"])]
        return MARGIN + (x - minx) * PITCH, LABEL + MARGIN + (y - miny) * PITCH

    lines: list[str] = []
    marks: list[str] = []
    drawn: set[frozenset[str]] = set()
    unexplored: set[str] = set()
    for room in rooms:
        uid = str(room["uid"])
        cx, cy = centre(room)
        for exit_ in graph.exits_from(uid):
            vector = VECTORS.get(exit_.dir)
            up_down = exit_.dir in (_UP, _DOWN)
            if exit_.touid == UNKNOWN_UID:
                unexplored.add(uid)
                if vector is not None:
                    lines.append(_stub(cx, cy, vector, "unexplored-stub"))
                elif up_down:
                    mark = "▲" if exit_.dir == _UP else "▼"
                    marks.append(
                        f"<text class='updown unexplored' x='{cx + 4}' y='{cy - BOX // 2 - 2}'>"
                        f"{mark}</text>"
                    )
                continue
            target = by_uid.get(exit_.touid)
            if target is None:
                # the exit leaves the area
                if vector is not None:
                    lines.append(_stub(cx, cy, vector, "leaves"))
                elif up_down:
                    mark = "▲" if exit_.dir == _UP else "▼"
                    marks.append(
                        f"<text class='updown leaves' x='{cx + 4}' y='{cy - BOX // 2 - 2}'>"
                        f"{mark}</text>"
                    )
                else:
                    marks.append(
                        f"<circle class='leaves' cx='{cx + BOX // 2}' cy='{cy - BOX // 2}' r='3'/>"
                    )
                continue
            target_z = pos[exit_.touid][2]
            if target_z != z:
                mark = "▲" if target_z > z else "▼"
                marks.append(
                    f"<text class='updown' x='{cx - BOX // 2}' y='{cy - BOX // 2 - 2}'>"
                    f"{mark}</text>"
                )
                continue
            pair = frozenset((uid, exit_.touid))
            if pair in drawn or exit_.touid == uid:
                continue
            drawn.add(pair)
            tx, ty = centre(target)
            lines.append(f"<line class='link' x1='{cx}' y1='{cy}' x2='{tx}' y2='{ty}'/>")
    boxes: list[str] = []
    for room in rooms:
        uid = str(room["uid"])
        cx, cy = centre(room)
        flags = set(room.get("flags") or ())
        classes = ["room"]
        if uid == current:
            classes.append("current")
        if uid in unexplored:
            classes.append("unexplored")
        if NOPORTAL_FLAG in flags:
            classes.append("noportal")
        if NORECALL_FLAG in flags:
            classes.append("norecall")
        if uid == selected:
            classes.append("selected")
        name = str(room.get("name") or "")
        tip = xml_text(f"{uid} {name}".strip())
        fill = terrain_color(str(room.get("terrain") or ""), terrain_colors)
        ink = xml_text(text_color(fill))
        half = BOX // 2
        markers = [m for m in (room.get("markers") or ()) if isinstance(m, str)]
        texts = (
            f"<text class='uid' x='{cx}' y='{cy - 2}' fill='{ink}'>"
            f"{xml_text(_cut(uid, NUMBER_CHARS))}</text>"
        )
        if markers:
            texts += (
                f"<text class='markers' x='{cx}' y='{cy + 10}' fill='{ink}'>"
                f"{xml_text(_cut(''.join(markers), MARKER_CHARS))}</text>"
            )
        if name:
            texts += (
                f"<text class='name' x='{cx}' y='{cy + half + 13}'>"
                f"{xml_text(_cut(name, NAME_CHARS))}</text>"
            )
        body = (
            f"<g class='{' '.join(classes)}'><title>{tip}</title>"
            f"<rect x='{cx - half}' y='{cy - half}' width='{BOX}' height='{BOX}' "
            f"fill='{xml_text(fill)}'/>{texts}</g>"
        )
        if area_path is not None:
            link = href(area_path, uid=area_uid, room=uid)
            body = f"<a href='{xml_text(link)}'>{body}</a>"
        elif room_path is not None:
            body = f"<a href='{xml_text(href(room_path, uid=uid))}'>{body}</a>"
        boxes.append(body)
    label = f"<text class='level-label' x='8' y='15'>z {z}</text>"
    return label + "".join(lines) + "".join(marks) + "".join(boxes), width, height


def _panel_lines(room: Mapping[str, Any], graph: MapGraph, by_uid: Mapping[str, Any]) -> list[str]:
    """The details lines of a room, in the order of the ``showroom`` command."""
    uid = str(room["uid"])
    flags = ", ".join(str(f) for f in room.get("flags") or ()) or "(none)"
    markers = ", ".join(m for m in (room.get("markers") or ()) if isinstance(m, str))
    lines = [
        f"room: {uid} {room.get('name') or ''}".rstrip(),
        f"area: {room.get('area') or ''}",
        f"terrain: {room.get('terrain') or ''}",
        f"coords: {room.get('x')} {room.get('y')} {room.get('z')}",
        f"flags: {flags}",
        f"markers: {markers or '(none)'}",
    ]
    details = room.get("details") or {}
    if details:
        lines.append("details:")
        for key in sorted(details, key=str):
            value = details[key]
            text = value if isinstance(value, str) else json.dumps(value, default=str)
            lines.append(f"{key}: {text}")
    else:
        lines.append("details: (none)")
    exits = sorted(graph.exits_from(uid), key=lambda e: e.dir)
    lines.append("exits:" if exits else "exits: (none)")
    for exit_ in exits:
        if exit_.touid in (UNKNOWN_UID, "-1"):
            line = f"{exit_.dir} -> unexplored"
        else:
            target = by_uid.get(exit_.touid)
            name = f" {target.get('name') or ''}".rstrip() if target is not None else ""
            line = f"{exit_.dir} -> {exit_.touid}{name}"
        line += f" (cost {exit_.cost})"
        if exit_.requirement:
            line += f" requires {json.dumps(exit_.requirement, sort_keys=True, default=str)}"
        lines.append(line)
    return lines


def _panel(
    room: Mapping[str, Any],
    graph: MapGraph,
    by_uid: Mapping[str, Any],
    room_path: str | None,
    x: int,
) -> tuple[str, int, int]:
    """Draw the details panel as a nested svg holding only text and a link: svg, width, height."""
    wrapped: list[str] = []
    for line in _panel_lines(room, graph, by_uid):
        wrapped.extend(textwrap.wrap(line, PANEL_CHARS) or [""])
    texts = [
        f"<text x='{_PANEL_PAD}' y='{_PANEL_PAD + (i + 1) * PANEL_LINE}'>{xml_text(line)}</text>"
        for i, line in enumerate(wrapped)
    ]
    if room_path is not None:
        y = _PANEL_PAD + (len(wrapped) + 2) * PANEL_LINE
        link = xml_text(href(room_path, uid=str(room["uid"])))
        texts.append(f"<a href='{link}'><text x='{_PANEL_PAD}' y='{y}'>room page</text></a>")
        rows = len(wrapped) + 2
    else:
        rows = len(wrapped)
    width = PANEL_CHARS * _PANEL_CHAR_WIDTH + 2 * _PANEL_PAD
    height = 2 * _PANEL_PAD + (rows + 1) * PANEL_LINE
    svg = (
        f"<svg class='panel' x='{x}' y='0' width='{width}' height='{height}'>"
        + "".join(texts)
        + "</svg>"
    )
    return svg, width, height


def draw_area_svg(
    area_uid: str,
    area_name: str,
    rooms: Sequence[Mapping[str, Any]],
    graph: MapGraph,
    *,
    current: str | None = None,
    room_path: str | None = None,
    area_path: str | None = None,
    selected: str | None = None,
    terrain_colors: Mapping[str, str] | None = None,
) -> str:
    """Draw an area as one svg document with a nested svg per z level.

    Args:
        area_uid: the area uid, shown in the document title.
        area_name: the area name, shown in the document title.
        rooms: the rooms of the area, dicts with uid, name, x, y, z and flags.
        graph: a frozen view of the map graph, the source of the exits.
        current: the uid of the room the character is in, marked when it is drawn.
        room_path: the path of the room page; with it every room box links to its room, and
            the details panel links to the room page.
        area_path: the path of the area page; with it every room box links to the area page
            with the room selected (``?uid=<area>&room=<uid>``), instead of to the room page.
        selected: the uid of the room to show in the details panel, when it is in the area.
        terrain_colors: the adapter's ``{terrain: "#rgb"}`` fill colours; other terrains get a
            stable fallback colour.

    Rooms are boxes on a grid from their x and y (y grows downwards). When the stored
    coordinates do not spread the rooms (a room without an int x or y, or two rooms in one
    cell of a level), the whole area is laid out from its exits instead, see ``_positions``.
    A line joins two rooms
    of a level. An exit that leaves the area is a short ``leaves`` stub (a dot when it has no
    compass direction), an exit to another level is an up or down arrow, and an unexplored
    exit is a dashed stub. The room classes are ``current``, ``unexplored``, ``noportal``,
    ``norecall`` and ``selected``. A room box shows its number and its ``markers`` inside and
    its name under it, filled by terrain colour. All MUD text (names, uids) is escaped, and the
    svg has no script.
    """
    by_uid = {str(r["uid"]): r for r in rooms}
    pos = _positions(rooms, graph, current)
    levels: dict[int, list[Mapping[str, Any]]] = {}
    for room in rooms:
        levels.setdefault(pos[str(room["uid"])][2], []).append(room)
    parts: list[str] = []
    offset = 0
    total_width = 2 * MARGIN
    for z in sorted(levels):
        body, width, height = _level(
            z,
            levels[z],
            by_uid,
            graph,
            current,
            room_path,
            pos,
            area_uid,
            area_path,
            selected,
            terrain_colors,
        )
        parts.append(
            f"<svg class='level' data-z='{z}' x='0' y='{offset}' width='{width}' "
            f"height='{height}' viewBox='0 0 {width} {height}'>{body}</svg>"
        )
        offset += height
        total_width = max(total_width, width)
    if not parts:
        parts.append("<text class='level-label' x='8' y='20'>no rooms</text>")
        offset = 2 * MARGIN
    if selected is not None and selected in by_uid:
        panel, panel_width, panel_height = _panel(
            by_uid[selected], graph, by_uid, room_path, total_width
        )
        parts.append(panel)
        total_width += panel_width
        offset = max(offset, panel_height)
    title = xml_text(f"{area_uid} {area_name}".strip())
    return (
        "<?xml version='1.0' encoding='UTF-8'?>"
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{total_width}' height='{offset}' "
        f"viewBox='0 0 {total_width} {offset}'><title>{title}</title>"
        f"<style>{_SVG_STYLE}</style><rect class='bg' width='100%' height='100%'/>"
        + "".join(parts)
        + "</svg>"
    )

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

import html
import math
from collections.abc import Callable, Mapping, Sequence
from typing import Any
from urllib.parse import urlencode

from ._graph import MapGraph
from ._schema import NOPORTAL_FLAG, NORECALL_FLAG, UNKNOWN_UID

# the grid: one room per PITCH, drawn as a BOX square, with STUB long exit stubs
PITCH = 40
BOX = 24
STUB = 14
MARGIN = 36
LABEL = 22

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
    ".room rect{fill:#222;stroke:#888;stroke-width:1.5}"
    ".room.current rect{fill:#26a;stroke:#fff;stroke-width:2.5}"
    ".room.unexplored rect{stroke:#e90}.room.noportal rect{stroke-dasharray:4 2}"
    ".room.norecall rect{fill:#322}"
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
) -> tuple[str, int, int]:
    """Draw one z level as a nested svg body: the svg text without its position, width, height."""
    xs = [_int(r["x"]) for r in rooms]
    ys = [_int(r["y"]) for r in rooms]
    minx, miny = min(xs), min(ys)
    width = (max(xs) - minx) * PITCH + 2 * MARGIN
    height = (max(ys) - miny) * PITCH + 2 * MARGIN + LABEL

    def centre(room: Mapping[str, Any]) -> tuple[int, int]:
        return MARGIN + (_int(room["x"]) - minx) * PITCH, LABEL + MARGIN + (
            _int(room["y"]) - miny
        ) * PITCH

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
            if _int(target["z"]) != z:
                mark = "▲" if _int(target["z"]) > z else "▼"
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
        tip = xml_text(f"{uid} {room.get('name') or ''}".strip())
        body = (
            f"<g class='{' '.join(classes)}'><title>{tip}</title>"
            f"<rect x='{cx - BOX // 2}' y='{cy - BOX // 2}' width='{BOX}' height='{BOX}'/></g>"
        )
        if room_path is not None:
            body = f"<a href='{xml_text(href(room_path, uid=uid))}'>{body}</a>"
        boxes.append(body)
    label = f"<text class='level-label' x='8' y='15'>z {z}</text>"
    return label + "".join(lines) + "".join(marks) + "".join(boxes), width, height


def draw_area_svg(
    area_uid: str,
    area_name: str,
    rooms: Sequence[Mapping[str, Any]],
    graph: MapGraph,
    *,
    current: str | None = None,
    room_path: str | None = None,
) -> str:
    """Draw an area as one svg document with a nested svg per z level.

    Args:
        area_uid: the area uid, shown in the document title.
        area_name: the area name, shown in the document title.
        rooms: the rooms of the area, dicts with uid, name, x, y, z and flags.
        graph: a frozen view of the map graph, the source of the exits.
        current: the uid of the room the character is in, marked when it is drawn.
        room_path: the path of the room page; with it every room box links to its room.

    Rooms are boxes on a grid from their x and y (y grows downwards). A line joins two rooms
    of a level. An exit that leaves the area is a short ``leaves`` stub (a dot when it has no
    compass direction), an exit to another level is an up or down arrow, and an unexplored
    exit is a dashed stub. The room classes are ``current``, ``unexplored``, ``noportal`` and
    ``norecall``. All MUD text (names, uids) is escaped, and the svg has no script.
    """
    by_uid = {str(r["uid"]): r for r in rooms}
    levels: dict[int, list[Mapping[str, Any]]] = {}
    for room in rooms:
        levels.setdefault(_int(room["z"]), []).append(room)
    parts: list[str] = []
    offset = 0
    total_width = 2 * MARGIN
    for z in sorted(levels):
        body, width, height = _level(z, levels[z], by_uid, graph, current, room_path)
        parts.append(
            f"<svg class='level' data-z='{z}' x='0' y='{offset}' width='{width}' "
            f"height='{height}' viewBox='0 0 {width} {height}'>{body}</svg>"
        )
        offset += height
        total_width = max(total_width, width)
    if not parts:
        parts.append("<text class='level-label' x='8' y='20'>no rooms</text>")
        offset = 2 * MARGIN
    title = xml_text(f"{area_uid} {area_name}".strip())
    return (
        "<?xml version='1.0' encoding='UTF-8'?>"
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{total_width}' height='{offset}' "
        f"viewBox='0 0 {total_width} {offset}'><title>{title}</title>"
        f"<style>{_SVG_STYLE}</style><rect class='bg' width='100%' height='100%'/>"
        + "".join(parts)
        + "</svg>"
    )

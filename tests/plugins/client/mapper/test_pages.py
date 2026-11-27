"""Tests for the pure mapper page builders (#766)."""

import hashlib
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import parse_qs, urlsplit

from bastproxy.plugins.client.mapper.libs._graph import Exit, MapGraph
from bastproxy.plugins.client.mapper.libs._pages import (
    AREA_COLUMNS,
    BOX,
    EMPTY_TERRAIN,
    FALLBACK_PALETTE,
    LABEL,
    MARGIN,
    MARKER_CHARS,
    NAME_CHARS,
    NUMBER_CHARS,
    PANEL_CHARS,
    PITCH,
    _positions,
    draw_area_svg,
    escape_rows,
    href,
    link_cell,
    page_rows,
    terrain_color,
    text_color,
    valid_color,
    xml_text,
)

NS = "{http://www.w3.org/2000/svg}"


def room(uid: str, x: int, y: int, z: int = 0, **extra: Any) -> dict[str, Any]:
    return {"uid": uid, "name": f"Room {uid}", "x": x, "y": y, "z": z, "flags": [], **extra}


def graph_of(rooms: list[dict[str, Any]], exits: list[Exit]) -> MapGraph:
    graph = MapGraph()
    for r in rooms:
        graph.set_room(r["uid"], r["flags"])
    for e in exits:
        graph.set_exit(e)
    return graph


def parse(svg: str) -> ET.Element:
    return ET.fromstring(svg)


def classes(root: ET.Element) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for group in root.iter(f"{NS}g"):
        title = group.find(f"{NS}title")
        assert title is not None
        result[(title.text or "").split()[0]] = (group.get("class") or "").split()
    return result


def test_xml_text_escapes_and_drops_invalid_characters() -> None:
    assert xml_text("<a & 'b' \"c\">") == "&lt;a &amp; &#x27;b&#x27; &quot;c&quot;&gt;"
    assert xml_text("a\x1b[1mb\x00c\ud800d") == "a[1mbcd"
    assert xml_text("tab\tnl\n") == "tab\tnl\n"


def test_href_and_link_cell_encode_the_query() -> None:
    assert href("/c/m/room") == "/c/m/room"
    cell = link_cell("t", "/c/m/room", uid="a b&c=d'<")
    assert set(cell) == {"text", "href"}
    parts = urlsplit(cell["href"])
    assert parts.path == "/c/m/room"
    assert parse_qs(parts.query) == {"uid": ["a b&c=d'<"]}
    assert "'" not in cell["href"]
    assert "<" not in cell["href"]


def test_one_nested_svg_per_z_level_with_rooms_at_their_coordinates() -> None:
    rooms = [room("a", 5, 3), room("b", 7, 3), room("c", 5, 4, 1), room("d", 6, 6, 1)]
    svg = draw_area_svg("ar", "Area", rooms, graph_of(rooms, []))
    root = parse(svg)
    levels = root.findall(f"{NS}svg")
    assert [e.get("data-z") for e in levels] == ["0", "1"]
    rects = list(levels[0].iter(f"{NS}rect"))
    xs = sorted(int(r.get("x") or 0) for r in rects)
    assert xs == [MARGIN - BOX // 2, MARGIN - BOX // 2 + 2 * PITCH]
    rects1 = list(levels[1].iter(f"{NS}rect"))
    ys = sorted(int(r.get("y") or 0) for r in rects1)
    assert ys[1] - ys[0] == 2 * PITCH
    assert len(list(root.iter(f"{NS}g"))) == 4


def test_lines_between_rooms_are_drawn_once() -> None:
    rooms = [room("a", 0, 0), room("b", 1, 0)]
    exits = [Exit("a", "e", "b"), Exit("b", "w", "a")]
    root = parse(draw_area_svg("ar", "", rooms, graph_of(rooms, exits)))
    links = [e for e in root.iter(f"{NS}line") if e.get("class") == "link"]
    assert len(links) == 1
    assert int(links[0].get("x2") or 0) - int(links[0].get("x1") or 0) in (PITCH, -PITCH)


def test_markers_and_classes() -> None:
    rooms = [
        room("cur", 0, 0),
        room("unexpl", 1, 0),
        room("np", 2, 0, flags=["noportal", "norecall"]),
        room("up", 0, 1, 0),
        room("hi", 0, 1, 1),
    ]
    exits = [
        Exit("unexpl", "n", "-1"),
        Exit("unexpl", "u", "-1"),
        Exit("cur", "w", "outside"),
        Exit("cur", "d", "outside"),
        Exit("cur", "enter portal", "outside"),
        Exit("up", "u", "hi"),
    ]
    root = parse(draw_area_svg("ar", "", rooms, graph_of(rooms, exits), current="cur"))
    found = classes(root)
    assert found["cur"] == ["room", "current"]
    assert found["unexpl"] == ["room", "unexplored"]
    assert found["np"] == ["room", "noportal", "norecall"]
    css = [e.get("class") for e in root.iter(f"{NS}line")]
    assert "unexplored-stub" in css
    assert "leaves" in css
    texts = [e.get("class") for e in root.iter(f"{NS}text")]
    assert "updown unexplored" in texts
    assert "updown leaves" in texts
    assert "updown" in texts
    assert [e.get("class") for e in root.iter(f"{NS}circle")] == ["leaves"]


def test_tooltips_and_links_are_escaped_and_the_svg_parses() -> None:
    hostile = "<script>alert('x')</script> & \"q\" \x1b[31m"
    rooms = [room("a<1>", 0, 0, name=hostile)]
    svg = draw_area_svg("ar&", hostile, rooms, graph_of(rooms, []), room_path="/c/m/room")
    root = parse(svg)
    assert "<script" not in svg
    assert "\x1b" not in svg
    title = root.find(f"{NS}g/{NS}title") or next(root.iter(f"{NS}title"))
    assert title is not None
    anchors = list(root.iter(f"{NS}a"))
    assert len(anchors) == 1
    link = anchors[0].get("href") or ""
    assert parse_qs(urlsplit(link).query) == {"uid": ["a<1>"]}
    tips = [t.text or "" for t in root.iter(f"{NS}title")]
    assert any("<script>alert('x')</script> & \"q\"" in t for t in tips)


def bare(uid: str, **coords: Any) -> dict[str, Any]:
    return {"uid": uid, "name": f"Room {uid}", "flags": [], **coords}


def drawn(svg: str) -> dict[str, tuple[int, int, int]]:
    """The grid cell (x, y, z) every room box is drawn at, relative to its level."""
    found: dict[str, tuple[int, int, int]] = {}
    for level in parse(svg).findall(f"{NS}svg"):
        z = int(level.get("data-z") or 0)
        for group in level.iter(f"{NS}g"):
            title = group.find(f"{NS}title")
            rect = group.find(f"{NS}rect")
            assert title is not None
            assert rect is not None
            x = (int(rect.get("x") or 0) - (MARGIN - BOX // 2)) // PITCH
            y = (int(rect.get("y") or 0) - (MARGIN + 22 - BOX // 2)) // PITCH
            found[(title.text or "").split()[0]] = (x, y, z)
    return found


def test_rooms_sharing_one_coordinate_are_laid_out_from_exits() -> None:
    rooms = [room("a", 30, 20), room("b", 30, 20), room("c", 30, 20)]
    exits = [Exit("a", "e", "b"), Exit("b", "s", "c")]
    cells = drawn(draw_area_svg("ar", "", rooms, graph_of(rooms, exits)))
    assert cells == {"a": (0, 0, 0), "b": (1, 0, 0), "c": (1, 1, 0)}


def test_rooms_without_coordinates_are_laid_out() -> None:
    absent = [bare("a"), bare("b")]
    nones = [bare("a", x=None, y=None), bare("b", x=None, y=None)]
    mixed = [room("a", 4, 4), bare("b", x=None, y=2)]
    for rooms in (absent, nones, mixed):
        graph = graph_of(rooms, [Exit("a", "n", "b")])
        assert drawn(draw_area_svg("ar", "", rooms, graph)) == {"a": (0, 1, 0), "b": (0, 0, 0)}


def test_a_collision_moves_the_room_to_the_nearest_free_cell() -> None:
    rooms = [room("a", 1, 1), room("b", 1, 1), room("c", 1, 1)]
    exits = [Exit("a", "e", "b"), Exit("a", "se", "c"), Exit("b", "s", "c")]
    pos = _positions(rooms, graph_of(rooms, exits), None)
    assert pos["a"] == (0, 0, 0)
    assert pos["b"] == (1, 0, 0)
    assert pos["c"] == (1, 1, 0)
    taken = [Exit("a", "e", "b"), Exit("c", "e", "b")]
    pos = _positions(rooms, graph_of(rooms, taken), None)
    assert len(set(pos.values())) == 3
    assert pos["b"] == (1, 0, 0)
    assert pos["c"] == (0, -1, 0)


def test_unconnected_parts_are_placed_side_by_side() -> None:
    rooms = [room("a", 0, 0), room("b", 0, 0), room("c", 0, 0), room("d", 0, 0)]
    exits = [Exit("a", "e", "b"), Exit("c", "e", "d")]
    pos = _positions(rooms, graph_of(rooms, exits), None)
    assert pos["a"] == (0, 0, 0)
    assert pos["b"] == (1, 0, 0)
    assert pos["c"] == (3, 0, 0)
    assert pos["d"] == (4, 0, 0)


def test_a_reverse_edge_alone_places_the_source() -> None:
    rooms = [room("a", 0, 0), room("b", 0, 0)]
    pos = _positions(rooms, graph_of(rooms, [Exit("b", "e", "a")]), None)
    assert pos["a"] == (0, 0, 0)
    assert pos["b"] == (-1, 0, 0)


def test_the_walk_starts_at_the_current_room_else_the_lowest_uid() -> None:
    rooms = [room("10", 0, 0), room("2", 0, 0), room("zz", 0, 0)]
    exits = [Exit("10", "e", "2"), Exit("2", "e", "zz")]
    graph = graph_of(rooms, exits)
    assert _positions(rooms, graph, None)["2"] == (0, 0, 0)
    assert _positions(rooms, graph, "zz")["zz"] == (0, 0, 0)
    assert _positions(rooms, graph, "elsewhere")["2"] == (0, 0, 0)


def test_distinct_coordinates_are_kept_including_one_x_y_on_two_levels() -> None:
    rooms = [room("a", 5, 3, 0), room("b", 7, 4, 0), room("c", 5, 3, 1)]
    graph = graph_of(rooms, [Exit("a", "w", "b")])
    assert _positions(rooms, graph, None) == {"a": (5, 3, 0), "b": (7, 4, 0), "c": (5, 3, 1)}


def test_up_and_down_exits_change_the_level() -> None:
    rooms = [room("a", 0, 0), room("b", 0, 0), room("c", 0, 0)]
    exits = [Exit("a", "u", "b"), Exit("a", "d", "c")]
    cells = drawn(draw_area_svg("ar", "", rooms, graph_of(rooms, exits)))
    assert cells["a"][2] == 0
    assert cells["b"][2] == 1
    assert cells["c"][2] == -1


def test_the_layout_is_deterministic() -> None:
    rooms = [room(u, 0, 0) for u in ("a", "b", "c", "d")]
    exits = [Exit("a", "e", "b"), Exit("a", "e", "c"), Exit("c", "n", "d"), Exit("d", "w", "a")]
    graph = graph_of(rooms, exits)
    first = draw_area_svg("ar", "", rooms, graph, current="c")
    assert draw_area_svg("ar", "", rooms, graph, current="c") == first
    assert _positions(list(reversed(rooms)), graph, "c") == _positions(rooms, graph, "c")


def test_stubs_and_custom_exits_do_not_place_rooms_but_stubs_are_drawn() -> None:
    rooms = [room("a", 0, 0), room("b", 0, 0)]
    exits = [
        Exit("a", "n", "-1"),
        Exit("a", "w", "outside"),
        Exit("a", "enter portal", "b"),
    ]
    graph = graph_of(rooms, exits)
    pos = _positions(rooms, graph, None)
    assert pos["a"] == (0, 0, 0)
    assert pos["b"] == (2, 0, 0)
    css = [e.get("class") for e in parse(draw_area_svg("ar", "", rooms, graph)).iter(f"{NS}line")]
    assert "unexplored-stub" in css
    assert "leaves" in css


def test_an_area_without_rooms_still_parses() -> None:
    root = parse(draw_area_svg("ar", "Empty", [], MapGraph()))
    assert root.findall(f"{NS}svg") == []


def _rows() -> list[list[Any]]:
    return [
        [{"text": "b", "href": "/x"}, "Beta", 10, 1],
        [{"text": "a", "href": "/x"}, "alpha", 2, 0],
        [{"text": "c", "href": "/x"}, "Gamma", None, 3],
    ]


def kwargs(**changes: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "sort": None,
        "descending": False,
        "filters": {},
        "offset": 0,
        "count": 50,
    }
    return base | changes


def test_page_rows_filter_sort_and_page() -> None:
    page, total = page_rows(_rows(), AREA_COLUMNS, **kwargs(sort="name"))
    assert (total, [r[1] for r in page]) == (3, ["alpha", "Beta", "Gamma"])
    page, _ = page_rows(_rows(), AREA_COLUMNS, **kwargs(sort="rooms", descending=True))
    assert [r[1] for r in page] == ["Beta", "alpha", "Gamma"]  # no number goes last
    page, _ = page_rows(_rows(), AREA_COLUMNS, **kwargs(sort="rooms"))
    assert [r[1] for r in page] == ["alpha", "Beta", "Gamma"]
    page, total = page_rows(_rows(), AREA_COLUMNS, **kwargs(filters={"uid": "A"}))
    assert (total, [r[1] for r in page]) == (1, ["alpha"])
    page, total = page_rows(_rows(), AREA_COLUMNS, **kwargs(filters={"unexplored": 3}))
    assert (total, [r[1] for r in page]) == (1, ["Gamma"])
    page, total = page_rows(_rows(), AREA_COLUMNS, **kwargs(offset=2, count=2))
    assert (total, len(page)) == (3, 1)
    page, total = page_rows(_rows(), AREA_COLUMNS, **kwargs(sort="nope", filters={"nope": "x"}))
    assert total == 3


def test_escape_rows_escapes_text_and_keeps_numbers_and_hrefs() -> None:
    rows = escape_rows(
        [[{"text": "a@b", "href": "/x"}, "c@d", 3, None]], lambda s: s.replace("@", "@@")
    )
    assert rows == [[{"text": "a@@b", "href": "/x"}, "c@@d", 3, None]]


# ---- labels, terrain colours and the details panel (#868) ----

HOSTILE = "<script>alert('x')</script> & \"q\" @rred"


def group_of(root: ET.Element, uid: str) -> ET.Element:
    for g in root.iter(f"{NS}g"):
        if (g.find(f"{NS}title").text or "").split()[0] == uid:  # type: ignore[union-attr]
            return g
    raise AssertionError(uid)


def text_of(group: ET.Element, css: str) -> str | None:
    for t in group.iter(f"{NS}text"):
        if t.get("class") == css:
            return t.text
    return None


def one_room(**extra: Any) -> tuple[list[dict[str, Any]], MapGraph]:
    rooms = [room("1", 0, 0, **extra)]
    return rooms, graph_of(rooms, [])


def test_the_grid_constants_leave_space_for_the_labels() -> None:
    assert (PITCH, BOX, LABEL) == (88, 32, 22)
    assert NAME_CHARS * 6 <= PITCH


def test_a_room_shows_its_uid_and_name_and_cuts_long_ones() -> None:
    rooms, graph = one_room(name="A very long room name indeed")
    rooms[0]["uid"] = "1234567"
    g = group_of(parse(draw_area_svg("ar", "Area", rooms, graph)), "1234567")
    assert text_of(g, "uid") == "1234…"
    assert len(text_of(g, "uid") or "") == NUMBER_CHARS
    name = text_of(g, "name") or ""
    assert name == "A very long r…"
    assert len(name) == NAME_CHARS
    short = one_room(name="Hall")
    g = group_of(parse(draw_area_svg("ar", "A", *short)), "1")
    assert (text_of(g, "uid"), text_of(g, "name")) == ("1", "Hall")


def test_markers_are_drawn_cut_and_non_strings_dropped() -> None:
    rooms, graph = one_room(markers=["A", 5, None, "BC", "DEFGH"])
    g = group_of(parse(draw_area_svg("ar", "A", rooms, graph)), "1")
    markers = text_of(g, "markers") or ""
    assert markers == "ABCD…"
    assert len(markers) == MARKER_CHARS
    extras: list[dict[str, Any]] = [{}, {"markers": []}, {"markers": [3]}]
    for extra in extras:
        rooms, graph = one_room(**extra)
        g = group_of(parse(draw_area_svg("ar", "A", rooms, graph)), "1")
        assert text_of(g, "markers") is None


def test_terrain_color_uses_the_adapter_mapping_then_a_stable_fallback() -> None:
    assert terrain_color("forest", {"forest": "#0a0"}) == "#0a0"
    assert terrain_color("forest", {"forest": "#00aa00"}) == "#00aa00"
    index = hashlib.sha256(b"forest").digest()[0] % len(FALLBACK_PALETTE)
    assert terrain_color("forest") == FALLBACK_PALETTE[index]
    assert terrain_color("forest", {"other": "#fff"}) == FALLBACK_PALETTE[index]
    assert terrain_color("forest", {"forest": "red"}) == FALLBACK_PALETTE[index]
    assert terrain_color("") == EMPTY_TERRAIN == "#222"
    assert terrain_color("", {"": "#123"}) == "#123"
    assert terrain_color("bad\udcff") in FALLBACK_PALETTE  # a lone surrogate does not raise


def test_valid_color() -> None:
    assert all(valid_color(c) for c in ("#fff", "#FfF", "#a1b2c3"))
    assert not any(valid_color(c) for c in ("fff", "#ffff", "#ggg", "#fff\n", "red", "", 5, None))


def test_text_color_follows_the_luminance() -> None:
    assert text_color("#fff") == "#000"
    assert text_color("#ffffff") == "#000"
    assert text_color("#000") == "#fff"
    assert text_color("#222") == "#fff"
    assert text_color("#ff0") == "#000"
    assert text_color("#00f") == "#fff"


def test_the_box_is_filled_by_attribute_and_the_css_never_sets_a_rect_fill() -> None:
    rooms, graph = one_room(terrain="forest")
    svg = draw_area_svg("ar", "A", rooms, graph, terrain_colors={"forest": "#0a0"})
    g = group_of(parse(svg), "1")
    assert g.find(f"{NS}rect").get("fill") == "#0a0"  # type: ignore[union-attr]
    assert [t.get("fill") for t in g.iter(f"{NS}text") if t.get("class") == "uid"] == ["#000"]
    style = svg.split("<style>")[1].split("</style>")[0]
    for rule in style.split("}"):
        if ".room" in rule and "rect" in rule:
            assert "fill" not in rule


def test_box_links_with_and_without_an_area_path() -> None:
    rooms, graph = one_room()
    root = parse(draw_area_svg("ar", "A", rooms, graph, area_path="/m/area", room_path="/m/room"))
    link = next(root.iter(f"{NS}a")).get("href") or ""
    assert urlsplit(link).path == "/m/area"
    assert parse_qs(urlsplit(link).query) == {"uid": ["ar"], "room": ["1"]}
    root = parse(draw_area_svg("ar", "A", rooms, graph, room_path="/m/room"))
    link = next(root.iter(f"{NS}a")).get("href") or ""
    assert (urlsplit(link).path, parse_qs(urlsplit(link).query)) == ("/m/room", {"uid": ["1"]})
    assert list(parse(draw_area_svg("ar", "A", rooms, graph)).iter(f"{NS}a")) == []


def test_the_selected_class_is_added_last_and_only_when_selected() -> None:
    rooms = [room("1", 0, 0), room("2", 1, 0)]
    graph = graph_of(rooms, [])
    root = parse(draw_area_svg("ar", "A", rooms, graph, current="1", selected="1"))
    assert group_of(root, "1").get("class") == "room current selected"
    assert group_of(root, "2").get("class") == "room"
    root = parse(draw_area_svg("ar", "A", rooms, graph, current="1"))
    assert group_of(root, "1").get("class") == "room current"


def panel_of(root: ET.Element) -> ET.Element | None:
    return next((e for e in root.iter(f"{NS}svg") if e.get("class") == "panel"), None)


def panel_lines(panel: ET.Element) -> list[str]:
    return [t.text or "" for t in panel.iter(f"{NS}text")]


def test_the_panel_shows_every_field_of_the_selected_room() -> None:
    rooms = [
        room(
            "1",
            3,
            4,
            2,
            area="ar",
            terrain="forest",
            flags=["noportal", "x"],
            markers=["Q", "!"],
            details={"b": 2, "a": "text", "c": {"k": {1}}},
            name="Cellar",
        ),
        room("2", 4, 4, 2, name="Hall"),
    ]
    graph = graph_of(
        rooms,
        [
            Exit("1", "e", "2", 3, {"l": 5}),
            Exit("1", "n", "-1"),
            Exit("1", "s", "99"),
        ],
    )
    root = parse(
        draw_area_svg("ar", "A", rooms, graph, selected="1", room_path="/m/room", area_path="/m/a")
    )
    panel = panel_of(root)
    assert panel is not None
    lines = panel_lines(panel)
    assert lines[:6] == [
        "room: 1 Cellar",
        "area: ar",
        "terrain: forest",
        "coords: 3 4 2",
        "flags: noportal, x",
        "markers: Q, !",
    ]
    assert lines.index("a: text") < lines.index("b: 2") < lines.index('c: {"k": "{1}"}')
    assert 'e -> 2 Hall (cost 3) requires {"l": 5}' in lines
    assert "n -> unexplored (cost 1)" in lines
    assert "s -> 99 (cost 1)" in lines
    assert lines.index('e -> 2 Hall (cost 3) requires {"l": 5}') < lines.index(
        "n -> unexplored (cost 1)"
    )
    link = panel.find(f"{NS}a")
    assert link is not None
    assert (link.find(f"{NS}text").text, urlsplit(link.get("href") or "").path) == (  # type: ignore[union-attr]
        "room page",
        "/m/room",
    )
    assert parse_qs(urlsplit(link.get("href") or "").query) == {"uid": ["1"]}
    assert {e.tag for e in panel.iter()} <= {f"{NS}svg", f"{NS}text", f"{NS}a"}


def test_the_panel_has_no_room_page_link_without_a_room_path_and_grows_the_root() -> None:
    rooms, graph = one_room()
    without = parse(draw_area_svg("ar", "A", rooms, graph))
    selected = parse(draw_area_svg("ar", "A", rooms, graph, selected="1"))
    panel = panel_of(selected)
    assert panel is not None and panel.find(f"{NS}a") is None
    assert int(selected.get("width") or 0) > int(without.get("width") or 0)
    assert int(selected.get("height") or 0) >= int(panel.get("height") or 0)


def test_a_long_panel_line_is_wrapped_without_losing_text() -> None:
    long = "w" * 100 + " " + "word " * 30
    rooms, graph = one_room(details={"note": long})
    panel = panel_of(parse(draw_area_svg("ar", "A", rooms, graph, selected="1")))
    assert panel is not None
    lines = panel_lines(panel)
    assert all(len(line) <= PANEL_CHARS for line in lines)
    joined = "".join("".join(line.split()) for line in lines)
    assert "".join(f"note: {long}".split()) in joined


def test_no_panel_for_an_unknown_selected_room() -> None:
    rooms, graph = one_room()
    for chosen in ("nope", "", None):
        assert panel_of(parse(draw_area_svg("ar", "A", rooms, graph, selected=chosen))) is None


def test_hostile_text_is_escaped_everywhere() -> None:
    rooms = [
        room(
            "1",
            0,
            0,
            name=HOSTILE,
            terrain=HOSTILE,
            area=HOSTILE,
            markers=[HOSTILE],
            flags=[HOSTILE],
            details={HOSTILE: HOSTILE},
        ),
        room("2", 1, 0, name=HOSTILE),
    ]
    graph = graph_of(rooms, [Exit("1", "e", "2", 1, {"k": HOSTILE})])
    svg = draw_area_svg(
        "ar",
        HOSTILE,
        rooms,
        graph,
        selected="1",
        room_path="/m/r",
        area_path="/m/a",
        terrain_colors={HOSTILE: "#fff"},
    )
    parse(svg)
    assert "<script" not in svg

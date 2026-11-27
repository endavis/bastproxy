"""Tests for the mapper web pages, served over http through the web core (#766)."""

import asyncio
import threading
import time
import xml.etree.ElementTree as ET
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from bastproxy.plugins.client.mapper import PLUGIN_DEPENDENCIES
from bastproxy.plugins.client.mapper.plugin import _mapper as mapper_module
from bastproxy.plugins.client.mapper.plugin._mapper import MapperPlugin
from bastproxy.plugins.core.web.libs._server import WebApp, WebServer
from bastproxy.plugins.core.web.libs._store import PageStore, RouteTable
from tests.plugins.core.web.conftest import get_request, http_get, to_html

from .conftest import OWNER, Harness

BASE = "/client/mapper"
SVG_NS = "{http://www.w3.org/2000/svg}"
HOSTILE = "<script>alert('x')</script> & \"q\" @rred"


class Cells(HTMLParser):
    """Collect the rows of the first table: each cell as (text, href or None)."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[tuple[str, str | None]]] = []
        self.heads: list[str] = []
        self._cell: list[str] | None = None
        self._href: str | None = None
        self._head = False
        self._row: list[tuple[str, str | None]] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            self._cell = []
            self._href = None
            self._head = tag == "th"
        elif tag == "a" and self._cell is not None:
            self._href = dict(attrs).get("href")

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._cell is not None:
            text = "".join(self._cell)
            if self._head:
                self.heads.append(text)
            elif self._row is not None:
                self._row.append((text, self._href))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None


def cells(document: str) -> Cells:
    parser = Cells()
    parser.feed(document)
    return parser


def query_of(href: str | None) -> dict[str, list[str]]:
    assert href is not None
    return parse_qs(urlsplit(href).query)


@dataclass
class Web:
    harness: Harness
    app: WebApp
    port: int
    sid: str
    results: dict[str, str | None]

    async def get(self, path: str, sid: bool = True) -> tuple[int, dict[str, str], str]:
        raw = f"GET {path} HTTP/1.1\r\nHost: x\r\n"
        if sid:
            raw += f"Cookie: bpsession={self.sid}\r\n"
        status, headers, body = await http_get(self.port, (raw + "\r\n").encode("latin-1"))
        return status, headers, body.decode()


def register(plugin: Any, routes: RouteTable, refuse: set[str] | None = None) -> dict[str, Any]:
    """Run the registration hook against a real route table."""
    added: dict[str, Any] = {}

    def add(
        owner: str,
        subpath: str,
        handler: Callable[..., Any],
        title: str,
        columns: Any,
        *,
        listed: bool = True,
    ) -> Any:
        if subpath in (refuse or set()):
            return None
        added[subpath] = title
        return routes.add(owner, subpath, handler, title, columns, listed=listed)

    plugin.api.table["plugins.core.web:web.route.add"] = add
    MapperPlugin._phook_add_web_routes(plugin)
    return added


@pytest.fixture
async def web(harness: Harness) -> AsyncIterator[Web]:
    plugin = harness.plugin
    plugin.web_paths = {}
    routes = RouteTable()
    app = WebApp(PageStore(), routes=routes, to_html=to_html)
    register(plugin, routes)
    server = WebServer()
    port = await server.start("127.0.0.1", 0, app, None)
    token = app.logins.issue()
    status, headers, _ = await http_get(port, get_request(f"/login/{token}"))
    assert status == 303
    sid = headers["set-cookie"].split(";")[0].split("=", 1)[1]
    yield Web(harness, app, port, sid, {})
    server.close()
    await server.wait_closed()


def seed(plugin: Any) -> None:
    """Two areas: 'ar' with a hostile name, 'other'; room 1 has an unexplored exit and a note."""
    plugin._api_area_add("ar", HOSTILE)
    plugin._api_area_add("other", "Other")
    plugin._api_room_add({"uid": "1", "name": HOSTILE, "area": "ar", "x": 0, "y": 0, "z": 0})
    plugin._api_room_add({"uid": "2", "name": "Cellar", "area": "ar", "x": 1, "y": 0, "z": 0})
    plugin._api_room_add({"uid": "3", "name": "Far Hall", "area": "other", "x": 0, "y": 0, "z": 0})
    plugin._api_exit_add("1", "e", "2")
    plugin._api_exit_add("1", "n", "-1")
    plugin._api_exit_add("1", "s", "3", 4, {"level": 5})
    plugin._api_exit_add("1", "w", "99")
    plugin._api_room_note_set("1", HOSTILE)


# ---- registration ----


def test_the_plugin_depends_on_the_web_plugin() -> None:
    assert "plugins.core.web" in PLUGIN_DEPENDENCIES


def test_four_routes_are_added_under_the_plugin_path(harness: Harness) -> None:
    plugin = harness.plugin
    routes = RouteTable()
    added = register(plugin, routes)
    assert sorted(added) == ["", "areamap", "find", "roominfo"]
    assert plugin.web_paths == {
        "": BASE,
        "areamap": f"{BASE}/areamap",
        "roominfo": f"{BASE}/roominfo",
        "find": f"{BASE}/find",
    }
    assert routes.count() == 4
    assert OWNER == "plugins.client.mapper"


def test_only_the_entry_pages_are_listed(harness: Harness) -> None:
    routes = RouteTable()
    register(harness.plugin, routes)
    listed = {
        sub: getattr(routes.match(path), "listed", None)
        for sub, path in harness.plugin.web_paths.items()
    }
    assert listed == {"": True, "areamap": False, "roominfo": False, "find": True}


async def test_the_index_leaves_out_the_pages_that_need_a_uid(web: Web) -> None:
    _, _, body = await web.get("/")
    assert f"href='{BASE}'" in body
    assert f"href='{BASE}/find'" in body
    assert f"{BASE}/areamap" not in body
    assert f"{BASE}/roominfo" not in body


def test_a_refused_route_does_not_raise_and_is_not_linked(harness: Harness) -> None:
    plugin = harness.plugin
    routes = RouteTable()
    register(plugin, routes, refuse={"roominfo"})
    assert "roominfo" not in plugin.web_paths
    assert routes.count() == 3
    assert plugin._web_link("roominfo", "1", uid="1") == "1"


# ---- access ----


@pytest.mark.parametrize(
    "path", [BASE, f"{BASE}/areamap?uid=ar", f"{BASE}/roominfo?uid=1", f"{BASE}/find"]
)
async def test_every_route_needs_a_session_and_get(web: Web, path: str) -> None:
    seed(web.harness.plugin)
    assert (await web.get(path, sid=False))[0] == 401
    raw = f"POST {path} HTTP/1.1\r\nCookie: bpsession={web.sid}\r\n\r\n".encode("latin-1")
    status, headers, _ = await http_get(web.port, raw)
    assert (status, headers["allow"]) == (405, "GET")
    status, headers, _ = await web.get(path)
    assert status == 200
    expected = "image/svg+xml; charset=utf-8" if "/areamap" in path else "text/html; charset=utf-8"
    assert headers["content-type"] == expected


# ---- pages ----


async def test_area_list(web: Web) -> None:
    seed(web.harness.plugin)
    _, _, body = await web.get(BASE)
    table = cells(body)
    assert table.heads == ["Area", "Name", "Rooms", "Unexplored"]
    first = table.rows[0]
    assert [c[0] for c in first] == ["ar", HOSTILE, "2", "1"]
    assert urlsplit(first[0][1] or "").path == f"{BASE}/areamap"
    assert query_of(first[0][1]) == {"uid": ["ar"]}
    assert [r[0][0] for r in table.rows] == ["ar", "other"]
    _, _, filtered = await web.get(f"{BASE}?f_uid=oth&sort=rooms&dir=desc")
    assert [r[0][0] for r in cells(filtered).rows] == ["other"]


async def test_area_map_draws_the_rooms_and_marks_the_current_room(web: Web) -> None:
    plugin = web.harness.plugin
    seed(plugin)
    plugin.current_room = "2"
    _, _, svg = await web.get(f"{BASE}/areamap?uid=ar")
    root = ET.fromstring(svg)
    groups = {
        (g.find(f"{SVG_NS}title").text or "").split()[0]: g.get("class")  # type: ignore[union-attr]
        for g in root.iter(f"{SVG_NS}g")
    }
    assert groups == {"1": "room unexplored", "2": "room current"}
    anchors = [query_of(a.get("href")) for a in root.iter(f"{SVG_NS}a")]
    hrefs = {urlsplit(a.get("href") or "").path for a in root.iter(f"{SVG_NS}a")}
    assert hrefs == {f"{BASE}/areamap"}
    assert all(a["uid"] == ["ar"] for a in anchors)
    assert sorted(a["room"][0] for a in anchors) == ["1", "2"]
    assert "<script" not in svg


def text_by_class(root: ET.Element, css: str) -> list[str]:
    return [t.text or "" for t in root.iter(f"{SVG_NS}text") if t.get("class") == css]


def panel_texts(root: ET.Element) -> list[str]:
    panel = next((e for e in root.iter(f"{SVG_NS}svg") if e.get("class") == "panel"), None)
    return [] if panel is None else [t.text or "" for t in panel.iter(f"{SVG_NS}text")]


async def test_area_map_shows_markers_and_terrain_colours(web: Web) -> None:
    plugin = web.harness.plugin
    seed(plugin)
    plugin._api_room_add({"uid": "1", "terrain": "forest"})
    plugin._api_room_marker_register("game", lambda r: ["M" + r["uid"]])
    plugin._api_terrain_color_register("game", {"forest": "#0a0"})
    _, _, svg = await web.get(f"{BASE}/areamap?uid=ar")
    root = ET.fromstring(svg)
    assert sorted(text_by_class(root, "markers")) == ["M1", "M2"]
    fills = {
        (g.find(f"{SVG_NS}title").text or "").split()[0]: g.find(f"{SVG_NS}rect").get("fill")  # type: ignore[union-attr]
        for g in root.iter(f"{SVG_NS}g")
    }
    assert fills["1"] == "#0a0"
    assert fills["2"] == "#222"


async def test_a_raising_marker_callback_still_serves_the_map(web: Web) -> None:
    plugin = web.harness.plugin
    seed(plugin)
    plugin._api_room_marker_register("game", lambda r: 1 / 0)
    status, _, svg = await web.get(f"{BASE}/areamap?uid=ar")
    assert status == 200
    assert text_by_class(ET.fromstring(svg), "markers") == []


async def test_the_room_query_shows_the_panel_of_a_room_of_the_area(web: Web) -> None:
    seed(web.harness.plugin)
    _, _, svg = await web.get(f"{BASE}/areamap?uid=ar&room=2")
    root = ET.fromstring(svg)
    lines = panel_texts(root)
    assert lines[0] == "room: 2 Cellar"
    assert "room page" in lines
    selected = [g for g in root.iter(f"{SVG_NS}g") if "selected" in (g.get("class") or "")]
    assert len(selected) == 1
    assert "<script" not in svg


async def test_a_room_of_another_area_or_none_shows_no_panel(web: Web) -> None:
    seed(web.harness.plugin)
    for query in ("room=3", "room=nope", "room=", ""):
        status, _, svg = await web.get(f"{BASE}/areamap?uid=ar&{query}")
        assert status == 200
        assert panel_texts(ET.fromstring(svg)) == []


async def test_an_area_with_only_an_area_row_is_empty_not_404(web: Web) -> None:
    web.harness.plugin._api_area_add("bare", "Bare")
    status, _, svg = await web.get(f"{BASE}/areamap?uid=bare")
    assert status == 200
    ET.fromstring(svg)


async def test_room_page(web: Web) -> None:
    seed(web.harness.plugin)
    status, _, body = await web.get(f"{BASE}/roominfo?uid=1")
    assert status == 200
    assert "&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt;" in body
    assert "<script>alert" not in body
    assert "@rred" in body  # the escaped colour code shows literally
    table = cells(body)
    rows = {r[0][0]: r for r in table.rows}
    assert set(rows) == {"e", "n", "s", "w"}
    assert rows["n"][1] == ("unexplored", None)
    assert query_of(rows["e"][1][1]) == {"uid": ["2"]}
    assert rows["e"][2][0] == "Cellar"
    assert rows["s"][3][0] == "4"
    assert rows["s"][4][0] == '{"level": 5}'
    assert rows["w"][1] == ("99", None)  # an exit to a room that is not stored has no link
    _, _, sorted_body = await web.get(f"{BASE}/roominfo?uid=1&sort=dir&dir=desc")
    assert [r[0][0] for r in cells(sorted_body).rows] == ["w", "s", "n", "e"]


async def test_find_page_filters_and_pages(web: Web) -> None:
    plugin = web.harness.plugin
    seed(plugin)
    for number in range(10, 70):
        plugin._api_room_add({"uid": str(number), "name": f"Hall {number}", "area": "other"})
    _, _, body = await web.get(f"{BASE}/find?name=hall&count=20")
    table = cells(body)
    assert len(table.rows) == 20
    assert "Page 1 of 4, 61 rows." in body
    assert "name=hall" in body  # the paging links keep the search
    _, _, second = await web.get(f"{BASE}/find?name=hall&count=20&page=4")
    assert len(cells(second).rows) == 1
    _, _, filtered = await web.get(f"{BASE}/find?name=hall&f_area=oth&f_uid=12")
    assert [r[0][0] for r in cells(filtered).rows] == ["12"]
    first = cells(body).rows[0]
    assert urlsplit(first[0][1] or "").path == f"{BASE}/roominfo"
    assert urlsplit(first[2][1] or "").path == f"{BASE}/areamap"
    assert query_of(first[2][1]) == {"uid": ["other"]}
    _, _, none = await web.get(f"{BASE}/find?name=%27+OR+1%3D1+--")
    assert cells(none).rows == []
    _, _, everything = await web.get(f"{BASE}/find")
    assert "63 rows" in everything


async def test_find_rejects_a_long_name_and_a_bad_filter(web: Web) -> None:
    assert (await web.get(f"{BASE}/find?name={'a' * 201}"))[0] == 400
    assert (await web.get(f"{BASE}/find?f_nope=1"))[0] == 400


@pytest.mark.parametrize(
    "path", [f"{BASE}/areamap", f"{BASE}/roominfo", f"{BASE}/areamap?uid=", f"{BASE}/roominfo?uid="]
)
async def test_a_missing_uid_is_400(web: Web, path: str) -> None:
    assert (await web.get(path))[0] == 400


@pytest.mark.parametrize("path", [f"{BASE}/areamap?uid=nope", f"{BASE}/roominfo?uid=nope"])
async def test_an_unknown_uid_is_404(web: Web, path: str) -> None:
    seed(web.harness.plugin)
    status, _, body = await web.get(path)
    assert status == 404
    assert "nope" in body


async def test_a_hostile_uid_in_the_error_message_is_escaped(web: Web) -> None:
    status, _, body = await web.get(f"{BASE}/roominfo?uid=%3Cscript%3E")
    assert status == 404
    assert "<script>" not in body


async def test_every_page_escapes_hostile_names(web: Web) -> None:
    seed(web.harness.plugin)
    for path in [BASE, f"{BASE}/roominfo?uid=1", f"{BASE}/find?name=script"]:
        _, _, body = await web.get(path)
        assert "<script>alert" not in body
        assert "&lt;script&gt;" in body
    _, _, svg = await web.get(f"{BASE}/areamap?uid=ar")
    assert "<script>" not in svg
    assert "&lt;script&gt;" in svg


# ---- the event loop ----


async def test_a_large_area_is_drawn_off_the_loop(
    web: Web, monkeypatch: pytest.MonkeyPatch
) -> None:
    plugin = web.harness.plugin
    plugin._api_area_add("big", "Big")
    plugin.store.write_batch(
        None,
        [
            {"uid": f"r{n}", "name": f"Room {n}", "area": "big", "x": n % 50, "y": n // 50}
            for n in range(2000)
        ],
        None,
        None,
        True,
    )
    plugin.graph = plugin.store.load_graph()
    real = mapper_module.draw_area_svg
    threads: list[int] = []

    def slow(*args: Any, **kwargs: Any) -> str:
        threads.append(threading.get_ident())
        time.sleep(0.4)
        return real(*args, **kwargs)

    monkeypatch.setattr(mapper_module, "draw_area_svg", slow)
    ticks = 0
    done = asyncio.Event()

    async def ticker() -> None:
        nonlocal ticks
        while not done.is_set():
            ticks += 1
            await asyncio.sleep(0.02)

    task = asyncio.create_task(ticker())
    status, _, svg = await web.get(f"{BASE}/areamap?uid=big")
    done.set()
    await task
    assert status == 200
    assert threads
    assert threads[0] != threading.get_ident()
    assert ticks >= 5  # the loop kept running while the worker slept
    root = ET.fromstring(svg)
    assert len(list(root.iter(f"{SVG_NS}g"))) == 2000

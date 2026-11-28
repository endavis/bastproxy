"""Table routes: query validation, rendering, paging and a bound sqlite handler (#424)."""

import re
import sqlite3
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from bastproxy.plugins.core.web.libs._http import Request

from .test_routes import Env
from .test_routes import env as env  # reason: reuse the fixture

COLUMNS = [
    {"name": "name", "label": "Name", "type": "text"},
    {"name": "level", "label": "Level", "type": "int"},
]
INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc=\"/static/table.js\")", re.IGNORECASE)
ORDER = {"name": "name", "level": "level"}
FILTER_TEXT = {"name": "name LIKE ?"}
FILTER_INT = {"level": "level = ?"}


def make_db() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE mobs (name TEXT, level INTEGER)")
    db.executemany(
        "INSERT INTO mobs VALUES (?, ?)",
        [(f"mob{i:03}", i) for i in range(1, 121)] + [("x' OR 1=1 --", 5)],
    )
    return db


def db_handler(db: sqlite3.Connection, seen: list[Request] | None = None) -> Any:
    def handler(request: Request) -> dict[str, Any]:
        assert request.table is not None
        if seen is not None:
            seen.append(request)
        query = request.table
        where: list[str] = []
        args: list[Any] = []
        for name, value in query.filters.items():
            if name in FILTER_TEXT:
                where.append(FILTER_TEXT[name])
                args.append(f"%{value}%")
            else:
                where.append(FILTER_INT[name])
                args.append(value)
        clause = f" WHERE {' AND '.join(where)}" if where else ""  # fragments are fixed above
        count_sql = "SELECT COUNT(*) FROM mobs" + clause
        total = db.execute(count_sql, args).fetchone()[0]
        order = (
            f" ORDER BY {ORDER[query.sort]} {'DESC' if query.descending else 'ASC'}"
            if query.sort
            else ""
        )
        rows_sql = (
            "SELECT name, level FROM mobs" + clause + order + " LIMIT ? OFFSET ?"
        )  # fixed fragments
        rows = db.execute(rows_sql, [*args, query.count, query.offset]).fetchall()
        return {"kind": "table", "title": "Mobs <b>", "rows": rows, "total": total}

    return handler


async def get(env: Env, path: str, sid: str) -> tuple[int, dict[str, str], str]:
    status, headers, body = await env.get(path, sid)
    return status, headers, body.decode()


async def test_sort_both_directions_reaches_the_handler_validated(env: Env) -> None:
    seen: list[Request] = []
    env.app.routes.add("plugins.test.web", "mobs", db_handler(make_db(), seen), "Mobs", COLUMNS)
    sid = await env.login()
    for direction in ("asc", "desc"):
        status, _, _ = await get(env, f"/test/web/mobs?sort=level&dir={direction}", sid)
        assert status == 200
    assert [(r.table.sort, r.table.descending) for r in seen if r.table] == [
        ("level", False),
        ("level", True),
    ]


async def test_rows_come_back_sorted_and_cells_are_escaped(env: Env) -> None:
    env.app.routes.add("plugins.test.web", "mobs", db_handler(make_db()), "Mobs", COLUMNS)
    sid = await env.login()
    _, _, page = await get(env, "/test/web/mobs?sort=level&dir=desc&count=2", sid)
    assert "<td>mob120</td><td>120</td>" in page
    assert "<title>Mobs &lt;b&gt;</title>" in page
    _, _, page = await get(env, "/test/web/mobs?f_name=OR&count=5", sid)
    assert "x&#x27; OR 1=1 --" in page


async def test_a_sql_looking_filter_is_bound_and_matches_nothing(env: Env) -> None:
    env.app.routes.add("plugins.test.web", "mobs", db_handler(make_db()), "Mobs", COLUMNS)
    sid = await env.login()
    status, _, page = await get(env, "/test/web/mobs?f_name=" + "x%27%20OR%201%3D1%20--%20z", sid)
    assert status == 200
    assert "<td>" not in page
    assert "0 rows" in page


@pytest.mark.parametrize(
    "query",
    [
        "sort=nope",
        "f_nope=1",
        "dir=sideways",
        "page=0",
        "count=9999",
        "f_level=abc",
        "f_name=" + "a" * 201,
    ],
)
async def test_bad_queries_are_400_and_skip_the_handler(env: Env, query: str) -> None:
    seen: list[Request] = []
    env.app.routes.add("plugins.test.web", "mobs", db_handler(make_db(), seen), "Mobs", COLUMNS)
    sid = await env.login()
    assert (await get(env, f"/test/web/mobs?{query}", sid))[0] == 400
    assert seen == []


async def test_a_table_route_still_needs_a_session(env: Env) -> None:
    env.app.routes.add("plugins.test.web", "mobs", db_handler(make_db()), "Mobs", COLUMNS)
    assert (await env.get("/test/web/mobs"))[0] == 401


async def test_a_table_result_from_a_route_without_columns_is_500(env: Env) -> None:
    env.add(lambda request: {"kind": "table", "title": "t", "rows": [], "total": 0})
    sid = await env.login()
    assert (await get(env, "/test/web/page", sid))[0] == 500


async def test_a_row_of_the_wrong_width_is_500(env: Env) -> None:
    env.app.routes.add(
        "plugins.test.web",
        "t",
        lambda r: {"kind": "table", "title": "t", "rows": [["a"]], "total": 1},
        "T",
        COLUMNS,
    )
    sid = await env.login()
    assert (await get(env, "/test/web/t", sid))[0] == 500


async def test_paging_links_keep_the_filters_and_data_pages_is_right(env: Env) -> None:
    env.app.routes.add("plugins.test.web", "mobs", db_handler(make_db()), "Mobs", COLUMNS)
    sid = await env.login()
    _, _, page = await get(env, "/test/web/mobs?f_name=mob&sort=name&dir=desc&count=50&page=2", sid)
    assert "data-pages='3'" in page
    assert "Page 2 of 3, 120 rows." in page
    nav = {
        label: link.replace("&amp;", "&")
        for link, label in re.findall(r"<a href='([^']*)'>(previous|next)</a>", page)
    }
    assert set(nav) == {"previous", "next"}
    expected_page = {"previous": "1", "next": "3"}
    for label, link in nav.items():
        parts = urlsplit(link)
        assert parts.path == "/test/web/mobs"
        params = parse_qs(parts.query)
        assert params["page"] == [expected_page[label]]
        assert params["f_name"] == ["mob"]
        assert params["sort"] == ["name"]
        assert params["dir"] == ["desc"]
    _, _, first = await get(env, "/test/web/mobs?count=50", sid)
    assert "previous" not in first
    assert "next" in first
    _, _, last = await get(env, "/test/web/mobs?f_name=mob&count=50&page=3", sid)
    assert "next" not in last
    assert last.count("<tr>") == 1 + 20


async def test_headers_toggle_the_direction_and_the_form_has_a_box_per_column(env: Env) -> None:
    env.app.routes.add("plugins.test.web", "mobs", db_handler(make_db()), "Mobs", COLUMNS)
    sid = await env.login()
    _, _, page = await get(env, "/test/web/mobs?sort=level&dir=asc&f_name=a%26b", sid)
    head = re.findall(r"<th data-type='(\w+)'><a href='([^']*)'>(\w+)</a></th>", page)
    assert [(kind, label) for kind, _, label in head] == [("text", "Name"), ("int", "Level")]
    level = parse_qs(urlsplit(head[1][1].replace("&amp;", "&")).query)
    assert level["sort"] == ["level"]
    assert level["dir"] == ["desc"]
    assert level["f_name"] == ["a&b"]
    name = parse_qs(urlsplit(head[0][1].replace("&amp;", "&")).query)
    assert name["dir"] == ["asc"]
    assert "<input type='text' name='f_name' value='a&amp;b'>" in page
    assert "<input type='text' name='f_level' value=''>" in page
    assert "<input type='hidden' name='sort' value='level'>" in page
    assert "<input type='hidden' name='count' value='50'>" in page
    assert "<form method='get' action='/test/web/mobs'>" in page


async def test_only_table_pages_load_the_script_and_no_page_has_an_inline_script(env: Env) -> None:
    env.app.routes.add("plugins.test.web", "mobs", db_handler(make_db()), "Mobs", COLUMNS)
    env.add(
        lambda r: {"kind": "html", "title": "<script>x</script>", "lines": ["<script>y</script>"]},
        "doc",
    )
    sid = await env.login()
    tag = '<script src="/static/table.js" defer></script>'
    _, _, table_page = await get(env, "/test/web/mobs", sid)
    _, _, plain = await get(env, "/test/web/doc", sid)
    _, _, index = await get(env, "/", sid)
    _, _, data_index = await get(env, "/data/", sid)
    assert tag in table_page
    assert tag not in plain
    assert tag not in index
    assert tag not in data_index
    for page in (table_page, plain, index, data_index):
        assert not INLINE_SCRIPT.search(page)
    assert "<script" not in plain


async def test_a_table_may_carry_intro_lines(env: Env) -> None:
    env.app.routes.add(
        "plugins.test.web",
        "t",
        lambda r: {"kind": "table", "title": "t", "lines": ["@rhello"], "rows": [], "total": 0},
        "T",
        COLUMNS,
    )
    sid = await env.login()
    _, _, page = await get(env, "/test/web/t", sid)
    assert "<pre><span style='color:#cd0000'>hello</span></pre>" in page


async def test_non_table_keys_are_kept_by_every_link_and_the_form(env: Env) -> None:
    env.app.routes.add("plugins.test.web", "mobs", db_handler(make_db()), "Mobs", COLUMNS)
    sid = await env.login()
    _, _, page = await get(
        env, "/test/web/mobs?area=foo&sort=level&count=50&page=2&f_name=mob", sid
    )
    links = [link.replace("&amp;", "&") for link in re.findall(r"<a href='([^']*)'", page)]
    assert len(links) == 4  # two headers, previous and next
    for link in links:
        params = parse_qs(urlsplit(link).query)
        assert params["area"] == ["foo"]
        assert params["f_name"] == ["mob"]
    assert "<input type='hidden' name='area' value='foo'>" in page
    assert page.count("name='sort'") == 1


async def test_a_kept_value_is_escaped_in_the_hidden_input_and_links(env: Env) -> None:
    env.app.routes.add("plugins.test.web", "mobs", db_handler(make_db()), "Mobs", COLUMNS)
    sid = await env.login()
    _, _, page = await get(env, "/test/web/mobs?area=%22%3C%3E%26&count=50", sid)
    assert "<input type='hidden' name='area' value='&quot;&lt;&gt;&amp;'>" in page
    for link in re.findall(r"<a href='([^']*)'", page):
        assert parse_qs(urlsplit(link.replace("&amp;", "&")).query)["area"] == ['"<>&']
    assert "\"<>&'" not in page


async def test_long_names_render_in_the_header_and_sorting_works_for_both_kinds(env: Env) -> None:
    columns = [
        {"name": "name", "label": "Name", "type": "text"},
        {"name": "level", "label": "Lvl", "type": "int", "long": "Level"},
    ]
    env.app.routes.add("plugins.test.web", "mobs", db_handler(make_db()), "Mobs", columns)
    sid = await env.login()
    _, _, page = await get(env, "/test/web/mobs?sort=level&dir=asc", sid)
    assert "<span class='long'>Level</span> <span class='short'>[Lvl]</span></a></th>" in page
    assert re.search(r"<a href='[^']*sort=name[^']*'>Name</a>", page)
    for sort in ("name", "level"):
        status, _, body = await get(env, f"/test/web/mobs?sort={sort}&dir=desc", sid)
        assert status == 200
        assert "<tbody><tr>" in body

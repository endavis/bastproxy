"""Data providers in the route table and over HTTP (#840)."""

import logging
from typing import Any

import pytest

from bastproxy.plugins.core.web.libs._http import Request
from bastproxy.plugins.core.web.libs._store import ProviderListeners, RouteTable, run_snapshot

from .conftest import http_get
from .test_routes import OWNER, Env  # reason: reuse the fixture
from .test_routes import env as env

COLUMNS = [{"name": "name", "label": "Name"}, {"name": "level", "label": "Level", "type": "int"}]


def snap() -> list[list[Any]]:
    return [["Orc", 5], ["elf", 10], ["gnome", 1]]


def escape(text: str) -> str:
    return text.replace("@", "@@")


def noop(request: Request) -> dict[str, Any]:
    return {"kind": "json", "data": {}}


def add(
    table: RouteTable,
    name: str = "mobs",
    *,
    owner: str = OWNER,
    kind: str = "json",
    columns: list[dict[str, str]] | None = None,
    event: str | None = None,
) -> str:
    return table.add_provider(owner, name, snap, columns, kind, event, escape)


def add_env(env: Env, name: str = "mobs", **kwargs: Any) -> str:
    return add(env.app.routes, name, **kwargs)


# ---- the route table ----


def test_topic_is_the_path_with_dots() -> None:
    table = RouteTable()
    assert add(table, "cp/mobsleft", owner="plugins.aardwolf.cp") == "aardwolf.cp.cp.mobsleft"
    assert table.match("/data/aardwolf/cp/cp/mobsleft") is not None


def test_a_provider_counts_apart_from_routes() -> None:
    table = RouteTable()
    add(table)
    assert table.count() == 0
    assert table.provider_count() == 1
    assert table.provider(OWNER, "mobs") is not None
    assert table.provider(OWNER, "other") is None


@pytest.mark.parametrize(
    ("name", "kind", "columns"),
    [
        ("", "json", None),
        ("Bad Name", "json", None),
        ("mobs", "xml", None),
        ("mobs", "table", None),
        ("mobs", "json", COLUMNS),
        ("mobs", "table", [{"name": "A!", "label": "A"}]),
    ],
)
def test_bad_providers_are_refused(name: str, kind: str, columns: Any) -> None:
    table = RouteTable()
    with pytest.raises(ValueError):
        add(table, name, kind=kind, columns=columns)
    assert table.provider_count() == 0


def test_a_reserved_prefix_is_refused() -> None:
    with pytest.raises(ValueError, match="reserved"):
        add(RouteTable(), owner="plugins.p")


def test_a_route_and_a_provider_of_one_name_coexist_in_either_order() -> None:
    table = RouteTable()
    table.add(OWNER, "mobs", noop, "Mobs")
    add(table)
    other = RouteTable()
    add(other)
    other.add(OWNER, "mobs", noop, "Mobs")
    for each in (table, other):
        route = each.match("/test/web/mobs")
        found = each.match("/data/test/web/mobs")
        assert route is not None
        assert route.provider is None
        assert found is not None
        assert found.provider is not None
        assert each.count() == 1
        assert each.provider_count() == 1


def test_a_provider_is_served_under_data_only() -> None:
    table = RouteTable()
    add(table)
    assert table.match("/test/web/mobs") is None
    assert table.match("/data/test/web/mobs") is not None


def test_the_data_segment_is_reserved_for_routes_and_providers() -> None:
    with pytest.raises(ValueError, match="reserved"):
        add(RouteTable(), owner="plugins.data")
    with pytest.raises(ValueError, match="reserved"):
        RouteTable().add("plugins.data.sub", "x", noop, "X")


def test_two_providers_of_different_owners_are_refused() -> None:
    table = RouteTable()
    add(table)
    with pytest.raises(ValueError, match="already served"):
        table.add_provider("plugins.test", "web/mobs", snap, None, "json", None, escape)
    assert table.provider_count() == 1


def test_remove_drops_a_route_and_a_provider_of_one_name() -> None:
    table = RouteTable()
    table.add(OWNER, "mobs", noop, "Mobs")
    add(table)
    assert table.remove(OWNER) == 2
    assert table.match("/test/web/mobs") is None
    assert table.match("/data/test/web/mobs") is None


def test_by_owner_lists_pages_before_providers() -> None:
    table = RouteTable()
    add(table, "a")
    table.add(OWNER, "z", noop, "Z")
    assert [r.path for r in table.by_owner()[OWNER]] == ["/test/web/z", "/data/test/web/a"]


def test_another_owner_is_refused_and_the_same_owner_replaces() -> None:
    table = RouteTable()
    add(table, event="ev_a")
    with pytest.raises(ValueError, match="already served"):
        table.add_provider("plugins.test", "web/mobs", snap, None, "json", None, escape)
    add(table, event="ev_b")
    assert table.provider_count() == 1
    assert table.provider_events() == {"ev_b"}


def test_remove_drops_providers_and_their_events() -> None:
    table = RouteTable()
    add(table, "a", event="ev_a")
    add(table, "b", event="ev_a")
    add(table, "c")
    assert table.topics_for_event("ev_a") == ["test.web.a", "test.web.b"]
    assert table.remove(OWNER) == 3
    assert table.provider_events() == set()
    assert table.providers() == []


# ---- listeners ----


def test_listeners_are_told_and_can_be_removed() -> None:
    seen: list[str] = []
    listeners = ProviderListeners()
    listeners.add(seen.append)
    listeners.add(seen.append)
    listeners.notify("a.b")
    assert seen == ["a.b"]
    listeners.remove(seen.append)
    listeners.remove(seen.append)
    listeners.notify("a.b")
    assert seen == ["a.b"]


def test_a_raising_listener_is_logged_and_skipped(caplog: pytest.LogCaptureFixture) -> None:
    seen: list[str] = []

    def bad(topic: str) -> None:
        raise RuntimeError(topic)

    listeners = ProviderListeners()
    listeners.add(bad)
    listeners.add(seen.append)
    with caplog.at_level(logging.ERROR):
        listeners.notify("x")
    assert seen == ["x"]
    assert any("provider listener failed" in r.getMessage() for r in caplog.records)


# ---- over http ----


async def test_a_json_provider_needs_a_session(env: Env) -> None:
    add_env(env)
    status, _, _ = await env.get("/data/test/web/mobs")
    assert status == 401
    sid = await env.login()
    status, headers, body = await env.get("/data/test/web/mobs", sid)
    assert status == 200
    assert headers["content-type"] == "application/json"
    assert body == b'[["Orc", 5], ["elf", 10], ["gnome", 1]]'


async def test_an_async_snapshot_is_awaited(env: Env) -> None:
    async def later() -> dict[str, int]:
        return {"n": 1}

    env.app.routes.add_provider(OWNER, "later", later, None, "json", None, escape)
    sid = await env.login()
    status, _, body = await env.get("/data/test/web/later", sid)
    assert (status, body) == (200, b'{"n": 1}')


async def test_unknown_and_removed_providers_are_404_and_post_is_405(env: Env) -> None:
    add_env(env)
    sid = await env.login()
    assert (await env.get("/data/test/web/none", sid))[0] == 404
    env.app.routes.remove(OWNER)
    assert (await env.get("/data/test/web/mobs", sid))[0] == 404


async def test_a_provider_is_not_served_at_its_old_path(env: Env) -> None:
    add_env(env)
    sid = await env.login()
    assert (await env.get("/test/web/mobs", sid))[0] == 404
    assert (await env.get("/data/test/web/mobs", sid))[0] == 200


async def test_a_route_and_a_provider_of_one_name_are_both_served(env: Env) -> None:
    env.app.routes.add(OWNER, "mobs", lambda request: {"kind": "json", "data": {"page": 1}}, "Mobs")
    add_env(env)
    sid = await env.login()
    page = await env.get("/test/web/mobs", sid)
    data = await env.get("/data/test/web/mobs", sid)
    assert page[0] == 200
    assert data[0] == 200
    assert page[2] != data[2]


async def test_a_post_is_405(env: Env) -> None:
    add_env(env)
    raw = b"POST /data/test/web/mobs HTTP/1.1\r\nHost: x\r\nContent-Length: 0\r\n\r\n"
    assert (await http_get(env.port, raw))[0] == 405


async def test_a_raising_snapshot_is_500(env: Env) -> None:
    def boom() -> None:
        raise RuntimeError("no")

    env.app.routes.add_provider(OWNER, "boom", boom, None, "json", None, escape)
    sid = await env.login()
    assert (await env.get("/data/test/web/boom", sid))[0] == 500


async def test_a_table_provider_sorts_filters_and_pages(env: Env) -> None:
    add_env(env, kind="table", columns=COLUMNS)
    sid = await env.login()
    status, headers, body = await env.get("/data/test/web/mobs?sort=level&dir=desc&count=2", sid)
    assert status == 200
    assert headers["content-type"].startswith("text/html")
    text = body.decode()
    assert text.index("elf") < text.index("Orc")
    assert "gnome" not in text
    assert "Page 1 of 2, 3 rows" in text
    status, _, body = await env.get("/data/test/web/mobs?f_name=NOM", sid)
    assert b"gnome" in body
    assert b"Orc" not in body


async def test_a_table_provider_bad_query_is_400(env: Env) -> None:
    add_env(env, kind="table", columns=COLUMNS)
    sid = await env.login()
    assert (await env.get("/data/test/web/mobs?sort=nope", sid))[0] == 400


async def test_table_cells_are_escaped_before_the_colour_converter(env: Env) -> None:
    env.app.routes.add_provider(OWNER, "t", lambda: [["@Rred", 1]], COLUMNS, "table", None, escape)
    sid = await env.login()
    _, _, body = await env.get("/data/test/web/t", sid)
    assert b"@Rred" in body


async def test_the_index_links_to_data_and_omits_providers(env: Env) -> None:
    add_env(env)
    env.app.routes.add(OWNER, "page", noop, "Page")
    sid = await env.login()
    _, _, body = await env.get("/", sid)
    assert b"/data/test/web/mobs" not in body
    assert b"/test/web/page" in body
    assert b"href='/data/'" in body


def test_pages_and_providers_by_owner_filter_and_sort() -> None:
    table = RouteTable()
    add(table, "zeta")
    add(table, "alpha", kind="table", columns=COLUMNS)
    table.add(OWNER, "b", noop, "B")
    table.add(OWNER, "a", noop, "A")
    add(table, "only", owner="other.owner")
    assert [r.path for r in table.pages_by_owner()[OWNER]] == ["/test/web/a", "/test/web/b"]
    assert "other.owner" not in table.pages_by_owner()
    assert [r.provider.topic for r in table.providers_by_owner()[OWNER] if r.provider] == [
        "test.web.alpha",
        "test.web.zeta",
    ]
    assert set(table.providers_by_owner()) == {OWNER, "other.owner"}


async def test_the_data_index_lists_owners_topics_kinds_and_links(env: Env) -> None:
    add_env(env, "mobs")
    add_env(env, "rows", kind="table", columns=COLUMNS)
    env.app.routes.add(OWNER, "page", noop, "Page")
    sid = await env.login()
    status, headers, body = await env.get("/data/", sid)
    text = body.decode()
    assert status == 200
    assert headers["content-type"].startswith("text/html")
    assert OWNER in text
    assert "<a href='/data/test/web/mobs'>test.web.mobs</a> (json)" in text
    assert "<a href='/data/test/web/rows'>test.web.rows</a> (table)" in text
    assert "/test/web/page" not in text
    assert "<script" not in text.lower()


def test_the_data_index_escapes_owner_and_topic() -> None:
    from bastproxy.plugins.core.web.libs._render import render_data_index
    from bastproxy.plugins.core.web.libs._store import Provider, Route

    route = Route(
        "<b>o</b>", "/data/x'y", "n", noop, "t", None, True, Provider("n", "<i>t</i>", "<k>")
    )
    text = render_data_index({"<b>o</b>": [route]})
    assert "<b>o" not in text
    assert "<i>t" not in text
    assert "<k>" not in text
    assert "&lt;b&gt;o&lt;/b&gt;" in text
    assert "&#x27;" in text


async def test_the_data_index_needs_a_session(env: Env) -> None:
    add_env(env)
    assert (await env.get("/data/"))[0] == 401


async def test_the_data_index_with_no_providers_says_so(env: Env) -> None:
    sid = await env.login()
    status, _, body = await env.get("/data/", sid)
    assert status == 200
    assert b"No data providers are registered" in body


async def test_data_without_the_slash_is_404(env: Env) -> None:
    add_env(env)
    assert (await env.get("/data", await env.login()))[0] == 404


def test_topics_are_sorted_and_leave_out_plain_routes() -> None:
    table = RouteTable()
    table.add_provider(OWNER, "zeta", snap, None, "json", None, escape)
    table.add_provider(OWNER, "alpha", snap, None, "json", None, escape)
    table.add(OWNER, "page", noop, "Page")
    assert table.topics() == ["test.web.alpha", "test.web.zeta"]


def test_provider_for_topic() -> None:
    table = RouteTable()
    table.add_provider(OWNER, "mobs", snap, None, "json", None, escape)
    table.add(OWNER, "page", noop, "Page")
    route = table.provider_for_topic("test.web.mobs")
    assert route is not None
    assert route.provider is not None
    assert route.provider.snapshot is snap
    assert table.provider_for_topic("test.web.other") is None
    assert table.provider_for_topic("test.web.page") is None
    assert table.provider_for_topic("") is None
    table.remove(OWNER)
    assert table.provider_for_topic("test.web.mobs") is None


async def test_run_snapshot_awaits_async_snapshots() -> None:
    async def later() -> int:
        return 3

    assert await run_snapshot(later) == 3
    assert await run_snapshot(lambda: 4) == 4


# ---- title, lines, unavailable and colour columns (#876) ----

TEXT_COLUMNS = [{"name": "name", "label": "Name"}, {"name": "note", "label": "Note"}]


def add_table(env: Env, name: str, snapshot: Any, **kwargs: Any) -> str:
    columns = kwargs.pop("columns", COLUMNS)
    return env.app.routes.add_provider(
        OWNER, name, snapshot, columns, "table", None, escape, **kwargs
    )


async def test_a_title_is_the_heading_the_title_tag_and_the_index_entry(env: Env) -> None:
    add_table(env, "t", snap, title="Mobs <left>")
    sid = await env.login()
    _, _, body = await env.get("/data/test/web/t", sid)
    text = body.decode()
    assert "<title>Mobs &lt;left&gt;</title>" in text
    assert "<h1>Mobs &lt;left&gt;</h1>" in text
    _, _, index = await env.get("/data/", sid)
    assert "<a href='/data/test/web/t'>Mobs &lt;left&gt;</a> test.web.t (table)" in index.decode()


async def test_without_a_title_the_topic_is_shown(env: Env) -> None:
    add_table(env, "t", snap)
    sid = await env.login()
    _, _, body = await env.get("/data/test/web/t", sid)
    assert "<h1>test.web.t</h1>" in body.decode()
    _, _, index = await env.get("/data/", sid)
    assert "<a href='/data/test/web/t'>test.web.t</a> (table)" in index.decode()


def test_a_title_that_is_not_text_is_refused() -> None:
    with pytest.raises(ValueError, match="title"):
        RouteTable().add_provider(OWNER, "t", snap, COLUMNS, "table", None, escape, title=5)


async def test_rows_and_lines_show_the_lines_above_the_table(env: Env) -> None:
    add_table(env, "t", lambda: {"rows": snap(), "lines": ["@Rintro", "second"]})
    sid = await env.login()
    status, _, body = await env.get("/data/test/web/t?sort=level&dir=desc&count=2", sid)
    text = body.decode()
    assert status == 200
    assert text.index("intro") < text.index("<table")
    assert "@Rintro" not in text
    assert text.index("elf") < text.index("Orc")
    assert "gnome" not in text


async def test_lines_may_be_a_string(env: Env) -> None:
    add_table(env, "t", lambda: {"rows": snap(), "lines": "just text"})
    sid = await env.login()
    _, _, body = await env.get("/data/test/web/t", sid)
    assert "just text" in body.decode()


async def test_a_plain_list_gives_the_handler_no_lines() -> None:
    table = RouteTable()
    add_table_to(table, snap)
    route = table.provider_for_topic("test.web.t")
    assert route is not None
    result = await route.handler(_table_request())
    assert "lines" not in result
    assert result["kind"] == "table"


def add_table_to(table: RouteTable, snapshot: Any, **kwargs: Any) -> str:
    return table.add_provider(OWNER, "t", snapshot, COLUMNS, "table", None, escape, **kwargs)


def _table_request() -> Request:
    from bastproxy.plugins.core.web.libs._table import TableQuery

    return Request("GET", "/data/test/web/t", table=TableQuery())


async def test_an_unavailable_snapshot_shows_the_lines_and_message_not_a_table(env: Env) -> None:
    add_table(env, "t", lambda: {"lines": ["Levels 1-10"], "unavailable": "No database."})
    sid = await env.login()
    status, _, body = await env.get("/data/test/web/t", sid)
    text = body.decode()
    assert status == 200
    assert "Levels 1-10" in text
    assert "No database." in text
    assert "<table" not in text


@pytest.mark.parametrize(
    "bad",
    [
        {"rows": [], "extra": 1},
        {"rows": [], "unavailable": ""},
        {"rows": [], "unavailable": 3},
        {"lines": ["x"]},
        {"rows": [], "lines": 5},
        {"rows": [], "lines": [1]},
        {"rows": "abc"},
    ],
)
async def test_a_malformed_snapshot_mapping_is_500(env: Env, bad: dict[str, Any]) -> None:
    add_table(env, "t", lambda: bad)
    sid = await env.login()
    assert (await env.get("/data/test/web/t", sid))[0] == 500


async def test_a_colour_column_keeps_colour_and_others_stay_escaped(env: Env) -> None:
    add_table(
        env,
        "t",
        lambda: [["@Rplain", "@Gnote"]],
        columns=[
            {"name": "name", "label": "Name"},
            {"name": "note", "label": "Note", "colour": True},
        ],
    )
    sid = await env.login()
    _, _, body = await env.get("/data/test/web/t", sid)
    text = body.decode()
    assert "@Rplain" in text
    assert "@Gnote" not in text
    assert "<span style='color:#00ff00'>note</span>" in text


async def test_a_colour_column_escapes_markup_beside_colour_codes(env: Env) -> None:
    add_table(
        env,
        "t",
        lambda: [["n", "@G<b>x</b>&<script>y</script>"]],
        columns=[
            {"name": "name", "label": "Name"},
            {"name": "note", "label": "Note", "colour": True},
        ],
    )
    sid = await env.login()
    _, _, body = await env.get("/data/test/web/t", sid)
    text = body.decode()
    assert "<b>" not in text
    assert "<script>y" not in text
    assert "&lt;b&gt;" in text
    assert "&amp;" in text
    assert "<span style='color:#00ff00'>" in text


async def test_a_colour_column_link_cell_keeps_its_href(env: Env) -> None:
    add_table(
        env,
        "t",
        lambda: [[{"text": "@Glink", "href": "/x"}, "n"]],
        columns=[
            {"name": "name", "label": "Name", "colour": True},
            {"name": "note", "label": "Note"},
        ],
    )
    sid = await env.login()
    _, _, body = await env.get("/data/test/web/t", sid)
    text = body.decode()
    assert "href='/x'" in text or 'href="/x"' in text
    assert "@Glink" not in text


@pytest.mark.parametrize(
    "columns",
    [
        [{"name": "a", "label": "A", "colour": "yes"}],
        [{"name": "a", "label": "A", "type": "int", "colour": True}],
    ],
)
def test_a_bad_colour_column_is_refused(columns: list[dict[str, Any]]) -> None:
    with pytest.raises(ValueError, match="colour"):
        RouteTable().add_provider(OWNER, "t", snap, columns, "table", None, escape)


def test_read_table_snapshot_reads_a_list_and_a_mapping() -> None:
    from bastproxy.plugins.core.web.libs._store import read_table_snapshot

    assert read_table_snapshot([[1]]).unavailable is None
    assert read_table_snapshot([[1]]).lines == ""
    read = read_table_snapshot({"rows": [[1]], "lines": "x"})
    assert (read.rows, read.lines) == ([[1]], "x")
    assert read_table_snapshot({"unavailable": "m"}).rows == []


def test_socket_fields_only_changes_an_unavailable_table() -> None:
    from bastproxy.plugins.core.web.libs._store import Provider, socket_fields

    table = Provider("n", "t", "table")
    assert socket_fields(table, {"unavailable": "m"}) == {"data": None, "unavailable": "m"}
    assert socket_fields(table, [[1]]) == {"data": [[1]]}
    assert socket_fields(table, {"rows": []}) == {"data": {"rows": []}}
    assert socket_fields(Provider("n", "t", "json"), {"unavailable": "m"}) == {
        "data": {"unavailable": "m"}
    }
    with pytest.raises(ValueError, match="unknown"):
        socket_fields(table, {"bogus": 1})


async def test_a_table_provider_with_long_renders_the_two_line_header(env: Env) -> None:
    columns = [
        {"name": "name", "label": "Name"},
        {"name": "level", "label": "Lvl", "long": "Level"},
    ]
    add_env(env, "longs", kind="table", columns=columns)
    sid = await env.login()
    status, _, body = await env.get("/data/test/web/longs", sid)
    assert status == 200
    assert b"<span class='long'>Level</span> <span class='short'>[Lvl]</span>" in body

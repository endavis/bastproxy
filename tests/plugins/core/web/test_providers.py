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


async def test_the_index_lists_providers(env: Env) -> None:
    add_env(env)
    sid = await env.login()
    _, _, body = await env.get("/", sid)
    assert b"/data/test/web/mobs" in body


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

"""Routes, login links and sessions in the stores and the dispatcher (#424)."""

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest

from bastproxy.plugins.core.web.libs import _http
from bastproxy.plugins.core.web.libs._http import Request
from bastproxy.plugins.core.web.libs._server import WebApp, WebServer
from bastproxy.plugins.core.web.libs._store import (
    LoginTokens,
    PageStore,
    RouteTable,
    SessionStore,
)

from .conftest import get_request, http_get, to_html


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def noop(request: Request) -> dict[str, Any]:
    return {"kind": "json", "data": {}}


# ---- stores ----


def test_login_token_works_once() -> None:
    logins = LoginTokens()
    token = logins.issue()
    assert logins.consume(token)
    assert not logins.consume(token)
    assert not logins.consume("unknown")


def test_login_token_expires_after_300_seconds() -> None:
    clock = Clock()
    logins = LoginTokens(clock=clock)
    token = logins.issue()
    clock.now = 299
    assert logins.consume(token)
    other = logins.issue()
    clock.now = 299 + 300
    assert not logins.consume(other)


def test_login_tokens_are_capped() -> None:
    logins = LoginTokens(cap=2)
    first, second, third = logins.issue(), logins.issue(), logins.issue()
    assert not logins.consume(first)
    assert logins.consume(second)
    assert logins.consume(third)


def test_session_lifecycle_and_clear() -> None:
    clock = Clock()
    sessions = SessionStore(clock=clock)
    sid = sessions.create(100)
    assert len(sid) >= 43
    assert sessions.is_valid(sid)
    assert not sessions.is_valid("forged")
    assert not sessions.is_valid(None)
    clock.now = 100
    assert not sessions.is_valid(sid)
    sessions.create(100)
    sessions.create(100)
    assert sessions.clear() == 2
    assert sessions.count() == 0


def test_session_cap_drops_the_oldest() -> None:
    sessions = SessionStore(cap=3)
    ids = [sessions.create(100) for _ in range(4)]
    assert sessions.count() == 3
    assert not sessions.is_valid(ids[0])
    assert sessions.is_valid(ids[3])


def test_route_path_comes_from_the_owner_id() -> None:
    table = RouteTable()
    assert RouteTable.prefix_for("plugins.aardwolf.mapper") == "aardwolf/mapper"
    assert table.add("plugins.aardwolf.mapper", "area", noop, "Area") == "/aardwolf/mapper/area"
    assert table.add("plugins.aardwolf.mapper", "", noop, "Home") == "/aardwolf/mapper"
    route = table.match("/aardwolf/mapper/area")
    assert route is not None
    assert route.subpath == "area"
    assert table.match("/aardwolf/mapper/other") is None
    assert table.match("/aardwolf/mapper/area/") is None


@pytest.mark.parametrize(
    "subpath", ["Area", "a b", "../x", "/a", "a/", "a//b", "-a", "a?b=1", "a\n", "é"]
)
def test_a_bad_subpath_is_refused(subpath: str) -> None:
    with pytest.raises(ValueError, match="invalid subpath"):
        RouteTable().add("plugins.aardwolf.mapper", subpath, noop, "t")


@pytest.mark.parametrize(
    "owner", ["plugins.p.x", "plugins.login.x", "plugins.static", "p.x", "plugins.data.x"]
)
def test_a_reserved_first_segment_is_refused(owner: str) -> None:
    with pytest.raises(ValueError, match="reserved"):
        RouteTable().add(owner, "a", noop, "t")


def test_another_owner_cannot_take_a_path() -> None:
    table = RouteTable()
    table.add("plugins.a.b", "c", noop, "t")
    # plugins.a.b.c with an empty subpath is the same url as plugins.a.b + c
    with pytest.raises(ValueError, match="already served"):
        table.add("plugins.a.b.c", "", noop, "t")


def test_remove_and_by_owner() -> None:
    table = RouteTable()
    table.add("plugins.a.one", "y", noop, "Y")
    table.add("plugins.a.one", "x", noop, "X")
    table.add("plugins.a.two", "z", noop, "Z")
    grouped = table.by_owner()
    assert [r.path for r in grouped["plugins.a.one"]] == ["/a/one/x", "/a/one/y"]
    assert table.remove("plugins.a.one") == 2
    assert table.remove("plugins.a.one") == 0
    assert list(table.by_owner()) == ["plugins.a.two"]
    assert table.match("/a/one/x") is None
    assert table.count() == 1


# ---- dispatcher over a real listener ----

OWNER = "plugins.test.web"
CIRCULAR: list[Any] = []
CIRCULAR.append(CIRCULAR)  # json.dumps cannot dump this


class Env:
    """A started plain-http server with its stores and flags."""

    def __init__(self, app: WebApp, server: WebServer, port: int) -> None:
        self.app = app
        self.server = server
        self.port = port
        self.secure = False
        self.hours = 12

    async def get(self, path: str, cookie: str | None = None) -> tuple[int, dict[str, str], bytes]:
        raw = f"GET {path} HTTP/1.1\r\nHost: x\r\n"
        if cookie is not None:
            raw += f"Cookie: bpsession={cookie}\r\n"
        return await http_get(self.port, (raw + "\r\n").encode("latin-1"))

    async def login(self) -> str:
        """Log in through a login link and return the session id."""
        token = self.app.logins.issue()
        status, headers, _ = await self.get(f"/login/{token}")
        assert status == 303
        return headers["set-cookie"].split(";")[0].split("=", 1)[1]

    def add(
        self,
        handler: Callable[..., Any],
        subpath: str = "page",
        title: str = "Page",
        listed: bool = True,
    ) -> str:
        return self.app.routes.add(OWNER, subpath, handler, title, listed=listed)


@pytest.fixture
async def env() -> AsyncIterator[Env]:
    holder: list[Env] = []
    app = WebApp(
        PageStore(),
        to_html=to_html,
        login_command=lambda: "#bp.core.web.login",
        secure_cookie=lambda: holder[0].secure,
        session_seconds=lambda: holder[0].hours * 3600,
    )
    server = WebServer()
    port = await server.start("127.0.0.1", 0, app, None)
    holder.append(Env(app, server, port))
    yield holder[0]
    server.close()
    await server.wait_closed()


async def test_a_route_is_served_with_a_session_and_gets_its_subpath(env: Env) -> None:
    seen: list[Request] = []

    def handler(request: Request) -> dict[str, Any]:
        seen.append(request)
        return {"kind": "json", "data": {"q": request.query}}

    path = env.add(handler, "sub/page")
    assert path == "/test/web/sub/page"
    sid = await env.login()
    status, headers, body = await env.get(f"{path}?a=1", sid)
    assert status == 200
    assert headers["content-type"] == "application/json"
    assert body == b'{"q": {"a": "1"}}'
    assert seen[0].subpath == "sub/page"
    assert seen[0].query == {"a": "1"}
    assert seen[0].method == "GET"


@pytest.mark.parametrize("path", ["/", "/test/web/page"])
async def test_no_session_forged_or_expired_session_is_401_with_the_hint(
    env: Env, path: str
) -> None:
    env.add(noop)
    status, _, body = await env.get(path)
    assert status == 401
    assert "#bp.core.web.login" in body.decode()
    assert (await env.get(path, "forged-session-id"))[0] == 401
    sid = await env.login()
    assert (await env.get(path, sid))[0] == 200
    env.app.sessions._clock = lambda: time.monotonic() + 13 * 3600  # reason: expire the session
    assert (await env.get(path, sid))[0] == 401


async def test_an_unknown_path_is_404_with_or_without_a_session(env: Env) -> None:
    env.add(noop)
    sid = await env.login()
    for path in ["/nope", "/test/web/other", "/test/web/page/", "/static/x", "/p/"]:
        assert (await env.get(path))[0] == 404
        assert (await env.get(path, sid))[0] == 404


async def test_post_to_a_route_is_405(env: Env) -> None:
    env.add(noop)
    sid = await env.login()
    raw = f"POST /test/web/page HTTP/1.1\r\nCookie: bpsession={sid}\r\n\r\n".encode()
    status, headers, _ = await http_get(env.port, raw)
    assert status == 405
    assert headers["allow"] == "GET"


async def test_html_kind_escapes_and_converts_colours(env: Env) -> None:
    env.add(
        lambda request: {
            "kind": "html",
            "title": "<b>T</b>",
            "lines": ["@rred <script>alert(1)</script>", "a & b"],
        }
    )
    sid = await env.login()
    status, headers, body = await env.get("/test/web/page", sid)
    text = body.decode()
    assert status == 200
    assert headers["content-type"] == "text/html; charset=utf-8"
    assert "<title>&lt;b&gt;T&lt;/b&gt;</title>" in text
    assert "<span style='color:#cd0000'>red &lt;script&gt;alert(1)&lt;/script&gt;</span>" in text
    assert "a &amp; b" in text
    assert "<script" not in text
    assert headers["content-security-policy"] == _http.CSP


async def test_svg_kind_is_served_as_svg(env: Env) -> None:
    svg = "<svg xmlns='http://www.w3.org/2000/svg'><text>x</text></svg>"
    env.add(lambda request: {"kind": "svg", "svg": svg})
    sid = await env.login()
    status, headers, body = await env.get("/test/web/page", sid)
    assert status == 200
    assert headers["content-type"] == "image/svg+xml; charset=utf-8"
    assert body == svg.encode()
    assert headers["x-content-type-options"] == "nosniff"


async def test_json_kind_uses_default_str(env: Env) -> None:
    env.add(lambda request: {"kind": "json", "data": {"set": {1}, "b": b"x"}})
    sid = await env.login()
    status, _, body = await env.get("/test/web/page", sid)
    assert status == 200
    assert body == b'{"set": "{1}", "b": "b\'x\'"}'


@pytest.mark.parametrize(
    "result",
    [
        "text",
        None,
        {"kind": "table"},
        {"kind": "html"},
        {"kind": "svg", "svg": 5},
        {"kind": "json", "data": CIRCULAR},
        {"kind": "json"},
    ],
)
async def test_any_other_result_is_500(env: Env, result: Any) -> None:
    env.add(lambda request: result)
    sid = await env.login()
    assert (await env.get("/test/web/page", sid))[0] == 500


async def test_a_raising_handler_is_500_and_logged_without_a_traceback_in_the_page(
    env: Env, caplog: pytest.LogCaptureFixture
) -> None:
    def boom(request: Request) -> dict[str, Any]:
        msg = "secret detail"
        raise RuntimeError(msg)

    env.add(boom)
    sid = await env.login()
    with caplog.at_level(logging.ERROR):
        status, _, body = await env.get("/test/web/page", sid)
    assert status == 500
    assert b"secret detail" not in body
    assert any(r.exc_info for r in caplog.records)


async def test_a_handler_that_times_out_is_504(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_http, "HANDLER_TIMEOUT", 0.05)

    async def slow(request: Request) -> dict[str, Any]:
        await asyncio.sleep(5)
        return {"kind": "json", "data": 1}

    env.add(slow)
    sid = await env.login()
    assert (await env.get("/test/web/page", sid))[0] == 504


async def test_an_async_handler_works(env: Env) -> None:
    async def handler(request: Request) -> dict[str, Any]:
        await asyncio.sleep(0)
        return {"kind": "json", "data": [1]}

    env.add(handler)
    sid = await env.login()
    assert (await env.get("/test/web/page", sid))[2] == b"[1]"


async def test_a_slow_handler_does_not_block_other_requests(env: Env) -> None:
    async def slow(request: Request) -> dict[str, Any]:
        await asyncio.to_thread(time.sleep, 0.5)
        return {"kind": "json", "data": "slow"}

    env.add(slow)
    sid = await env.login()
    token = env.app.pages.add("plugins.x", "t", b"fast")
    order: list[str] = []

    async def run_slow() -> None:
        status, _, _ = await env.get("/test/web/page", sid)
        assert status == 200
        order.append("slow")

    async def run_fast() -> None:
        await asyncio.sleep(0.1)  # reason: start while the slow handler is running
        status, _, body = await env.get(f"/p/{token}")
        assert (status, body) == (200, b"fast")
        order.append("fast")

    await asyncio.gather(run_slow(), run_fast())
    assert order == ["fast", "slow"]


async def test_login_redirects_and_sets_the_cookie(env: Env) -> None:
    token = env.app.logins.issue()
    status, headers, body = await env.get(f"/login/{token}")
    assert status == 303
    assert headers["location"] == "/"
    assert body == b""
    cookie = [part.strip() for part in headers["set-cookie"].split(";")]
    assert cookie[0].startswith("bpsession=")
    assert len(cookie[0].split("=", 1)[1]) >= 43
    assert "HttpOnly" in cookie
    assert "SameSite=Strict" in cookie
    assert "Path=/" in cookie
    assert f"Max-Age={12 * 3600}" in cookie
    assert "Secure" not in cookie


async def test_login_cookie_is_secure_when_the_flag_is_on(env: Env) -> None:
    env.secure = True
    env.hours = 2
    token = env.app.logins.issue()
    _, headers, _ = await env.get(f"/login/{token}")
    cookie = [part.strip() for part in headers["set-cookie"].split(";")]
    assert "Secure" in cookie
    assert "Max-Age=7200" in cookie


async def test_a_login_link_works_once(env: Env) -> None:
    token = env.app.logins.issue()
    assert (await env.get(f"/login/{token}"))[0] == 303
    assert (await env.get(f"/login/{token}"))[0] == 404
    assert (await env.get("/login/"))[0] == 404
    assert (await env.get("/login/unknown"))[0] == 404


async def test_a_login_link_expires(env: Env) -> None:
    clock = Clock()
    env.app.logins._clock = clock
    token = env.app.logins.issue()
    clock.now = 300
    assert (await env.get(f"/login/{token}"))[0] == 404


async def test_the_index_lists_routes_by_owner_and_title_escaped(env: Env) -> None:
    env.add(noop, "one", "<i>One</i>")
    env.add(noop, "two", "Two")
    sid = await env.login()
    status, _, body = await env.get("/", sid)
    text = body.decode()
    assert status == 200
    assert f"<h2>{OWNER}</h2>" in text
    assert "<a href='/test/web/one'>&lt;i&gt;One&lt;/i&gt;</a>" in text
    assert "<a href='/test/web/two'>Two</a>" in text
    assert "<i>" not in text


def test_a_route_is_listed_unless_added_unlisted() -> None:
    table = RouteTable()
    table.add(OWNER, "a", noop, "A")
    table.add(OWNER, "b", noop, "B", listed=False)
    assert getattr(table.match("/test/web/a"), "listed", None) is True
    assert getattr(table.match("/test/web/b"), "listed", None) is False


def test_remove_and_count_include_unlisted_routes() -> None:
    table = RouteTable()
    table.add(OWNER, "a", noop, "A")
    table.add(OWNER, "b", noop, "B", listed=False)
    assert table.count() == 2
    assert table.remove(OWNER) == 2
    assert table.match("/test/web/b") is None


async def test_the_index_skips_unlisted_routes_but_they_are_served(env: Env) -> None:
    env.add(noop, "one", "One")
    env.add(noop, "two", "Two", listed=False)
    sid = await env.login()
    text = (await env.get("/", sid))[2].decode()
    assert "/test/web/one" in text
    assert "/test/web/two" not in text
    assert (await env.get("/test/web/two", sid))[0] == 200
    assert (await env.get("/test/web/two"))[0] == 401


async def test_an_owner_with_only_unlisted_routes_has_no_heading(env: Env) -> None:
    env.add(noop, "one", "One")
    env.app.routes.add("plugins.test.hidden", "", noop, "Hidden", listed=False)
    text = (await env.get("/", await env.login()))[2].decode()
    assert f"<h2>{OWNER}</h2>" in text
    assert "<h2>plugins.test.hidden</h2>" not in text


async def test_the_index_with_only_unlisted_routes_says_so(env: Env) -> None:
    env.add(noop, "one", "One", listed=False)
    assert b"No pages are registered" in (await env.get("/", await env.login()))[2]


async def test_the_index_with_no_routes_says_so(env: Env) -> None:
    sid = await env.login()
    body = (await env.get("/", sid))[2]
    assert b"No pages are registered" in body
    assert b"href='/data/'" in body


async def test_ending_all_sessions_gives_401_again(env: Env) -> None:
    env.add(noop)
    first, second = await env.login(), await env.login()
    assert env.app.sessions.clear() == 2
    for sid in (first, second):
        assert (await env.get("/test/web/page", sid))[0] == 401


async def test_a_removed_route_is_404(env: Env) -> None:
    env.add(noop)
    sid = await env.login()
    assert (await env.get("/test/web/page", sid))[0] == 200
    env.app.routes.remove(OWNER)
    assert (await env.get("/test/web/page", sid))[0] == 404


async def test_page_links_still_need_no_session(env: Env) -> None:
    token = env.app.pages.add("plugins.x", "t", b"body")
    assert (await env.get(f"/p/{token}"))[2] == b"body"
    assert (await http_get(env.port, get_request(f"/p/{token}")))[0] == 200


# ---- the error kind and link cells (#766) ----


@pytest.mark.parametrize("status", [400, 404])
async def test_error_kind_serves_the_status_with_an_escaped_message(env: Env, status: int) -> None:
    env.add(lambda request: {"kind": "error", "status": status, "message": "no <b>room</b> & co"})
    sid = await env.login()
    code, headers, body = await env.get("/test/web/page", sid)
    assert code == status
    assert headers["content-type"] == "text/html; charset=utf-8"
    assert "no &lt;b&gt;room&lt;/b&gt; &amp; co" in body.decode()
    assert "<b>room</b>" not in body.decode()


@pytest.mark.parametrize("status", [200, 401, 500, 418, "404", None])
async def test_error_kind_with_another_status_is_a_500(env: Env, status: object) -> None:
    env.add(lambda request: {"kind": "error", "status": status, "message": "m"})
    sid = await env.login()
    assert (await env.get("/test/web/page", sid))[0] == 500


async def test_a_bad_link_cell_is_a_500_and_a_good_one_is_served(env: Env) -> None:
    columns = [{"name": "a", "label": "A"}]

    def table(href: str) -> Callable[[Request], dict[str, Any]]:
        def handler(request: Request) -> dict[str, Any]:
            return {
                "kind": "table",
                "title": "T",
                "rows": [[{"text": "go", "href": href}]],
                "total": 1,
            }

        return handler

    env.app.routes.add(OWNER, "bad", table("//evil.example/"), "Bad", columns)
    env.app.routes.add(OWNER, "good", table("/test/web/good?x=1"), "Good", columns)
    sid = await env.login()
    assert (await env.get("/test/web/bad", sid))[0] == 500
    status, _, body = await env.get("/test/web/good", sid)
    assert status == 200
    assert "<a href='/test/web/good?x=1'>go</a>" in body.decode()

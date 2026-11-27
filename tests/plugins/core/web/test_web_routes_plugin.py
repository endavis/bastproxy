"""The web plugin's route api, login and logout commands, and status (#424)."""

import asyncio
import json
import logging
from types import SimpleNamespace
from typing import Any

import pytest
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from bastproxy import __version__
from bastproxy.plugins.core.web.plugin._web import WebPlugin

from .conftest import get_request, http_get
from .test_web_plugin import status_text
from .test_web_plugin import stub as stub  # reason: reuse the fixture

OWNER = "plugins.test.caller"


def handler(request: Any) -> dict[str, Any]:
    return {"kind": "json", "data": 1}


def add(stub: Any, owner: str = OWNER, subpath: str = "area", **kwargs: Any) -> str | None:
    result: str | None = WebPlugin._api_web_route_add(
        stub, owner, subpath, handler, "Area", **kwargs
    )
    return result


def test_a_route_is_added_under_the_owner_prefix(stub: Any) -> None:
    assert add(stub) == "/test/caller/area"
    assert stub.routes.match("/test/caller/area") is not None


def test_listed_defaults_to_true_and_can_be_turned_off(stub: Any) -> None:
    assert add(stub, subpath="one") == "/test/caller/one"
    assert add(stub, subpath="two", listed=False) == "/test/caller/two"
    assert stub.routes.match("/test/caller/one").listed is True
    assert stub.routes.match("/test/caller/two").listed is False


def test_unload_removes_unlisted_routes_too(stub: Any) -> None:
    add(stub, subpath="one", listed=False)
    stub.unloaded = OWNER
    WebPlugin._eventcb_plugin_unloaded(stub)
    assert stub.routes.count() == 0


def test_the_owner_must_be_the_caller(stub: Any, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR):
        assert add(stub, owner="plugins.other.plugin") is None
    assert stub.routes.count() == 0
    assert any("not the calling plugin" in r.getMessage() for r in caplog.records)


def test_an_invalid_plugin_id_is_refused(stub: Any) -> None:
    stub.caller = "not-a-plugin"
    assert add(stub, owner="not-a-plugin") is None
    assert stub.routes.count() == 0


@pytest.mark.parametrize("subpath", ["Bad Path", "../x", "a//b"])
def test_a_bad_subpath_is_refused_and_logged(
    stub: Any, caplog: pytest.LogCaptureFixture, subpath: str
) -> None:
    with caplog.at_level(logging.ERROR):
        assert add(stub, subpath=subpath) is None
    assert any("invalid subpath" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("segment", ["p", "login", "static"])
def test_a_reserved_first_segment_is_refused(stub: Any, segment: str) -> None:
    stub.caller = f"plugins.{segment}.x"
    assert add(stub, owner=stub.caller) is None


def test_route_remove_returns_the_count(stub: Any) -> None:
    add(stub, subpath="one")
    add(stub, subpath="two")
    assert WebPlugin._api_web_route_remove(stub, OWNER) == 2
    assert WebPlugin._api_web_route_remove(stub, OWNER) == 0


def test_unload_removes_only_that_owners_routes(stub: Any) -> None:
    add(stub)
    stub.caller = "plugins.test.keeper"
    add(stub, owner="plugins.test.keeper")
    stub.unloaded = OWNER
    WebPlugin._eventcb_plugin_unloaded(stub)
    assert list(stub.routes.by_owner()) == ["plugins.test.keeper"]


async def test_init_keeps_routes_and_sessions_across_a_reload() -> None:
    plugin = SimpleNamespace()
    WebPlugin._phook_init_plugin(plugin)
    assert set(plugin.attributes_to_save_on_reload) == {"pages", "routes", "sessions", "logins"}
    for name in plugin.attributes_to_save_on_reload:
        assert hasattr(plugin, name)


def test_sessionhours_setting(stub: Any) -> None:
    WebPlugin._phook_initialize(stub)
    assert stub.added["sessionhours"] == 12
    validator = next(
        kwargs["validator"]
        for name, args, kwargs in stub.calls
        if name == "plugins.core.settings:setting.add" and args[1] == "sessionhours"
    )
    assert validator(1) == ""
    assert validator(720) == ""
    for bad in (0, 721, "x", True):
        assert validator(bad) != ""


async def test_login_command_gives_a_working_link_and_is_hidden_from_history(stub: Any) -> None:
    await stub._restart(0)
    result = WebPlugin._command_login(stub)
    assert result.success
    (line,) = result.message
    base = f"http://127.0.0.1:{stub.settings['port']}/login/"
    assert line.startswith(f"Login link: {base}")
    token = line.rsplit("/", 1)[1]
    status, headers, _ = await http_get(stub.port, get_request(f"/login/{token}"))
    assert status == 303
    assert headers["location"] == "/"
    assert stub.sessions.count() == 1
    assert (await http_get(stub.port, get_request(f"/login/{token}")))[0] == 404
    kwargs = WebPlugin._command_login.command_data.command["kwargs"]
    assert kwargs["show_in_history"] is False


async def test_login_link_uses_publicurl_and_escapes_colour_codes(stub: Any) -> None:
    stub.settings["publicurl"] = "https://x.ts.net/"
    result = WebPlugin._command_login(stub)
    assert result.message[0].startswith("Login link: https://x.ts.net/login/")
    stub.settings["publicurl"] = "https://x.ts.net/@r"
    assert "https://x.ts.net/@@r/login/" in WebPlugin._command_login(stub).message[0]


def test_login_command_says_so_when_the_server_is_disabled(stub: Any) -> None:
    stub.settings["enabled"] = False
    result = WebPlugin._command_login(stub)
    assert result.success
    assert "not enabled" in result.message[0]
    assert stub.logins._tokens == {}


async def test_login_cookie_is_secure_with_an_https_publicurl_on_plain_http(stub: Any) -> None:
    # Setup B: a reverse proxy ends TLS, the listener stays plain http on loopback
    stub.settings["publicurl"] = "https://x.ts.net"
    await stub._restart(0)
    assert not stub.server.tls
    token = stub.logins.issue()
    _, headers, _ = await http_get(stub.port, get_request(f"/login/{token}"))
    cookie = [part.strip() for part in headers["set-cookie"].split(";")]
    assert "Secure" in cookie
    assert f"Max-Age={12 * 3600}" in cookie


async def test_login_cookie_is_not_secure_on_plain_http_without_publicurl(stub: Any) -> None:
    await stub._restart(0)
    token = stub.logins.issue()
    _, headers, _ = await http_get(stub.port, get_request(f"/login/{token}"))
    assert "Secure" not in [part.strip() for part in headers["set-cookie"].split(";")]


async def test_session_lifetime_follows_the_setting(stub: Any) -> None:
    stub.settings["sessionhours"] = 3
    await stub._restart(0)
    token = stub.logins.issue()
    _, headers, _ = await http_get(stub.port, get_request(f"/login/{token}"))
    assert f"Max-Age={3 * 3600}" in [part.strip() for part in headers["set-cookie"].split(";")]


async def test_a_registered_route_is_served_after_login_and_logout_ends_it(stub: Any) -> None:
    await stub._restart(0)
    add(stub)
    token = stub.logins.issue()
    _, headers, _ = await http_get(stub.port, get_request(f"/login/{token}"))
    sid = headers["set-cookie"].split(";")[0].split("=", 1)[1]
    raw = f"GET /test/caller/area HTTP/1.1\r\nCookie: bpsession={sid}\r\n\r\n".encode()
    assert (await http_get(stub.port, raw))[0] == 200
    status, _, body = await http_get(stub.port, get_request("/test/caller/area"))
    assert status == 401
    assert b"#bp.core.web.login" in body
    result = WebPlugin._command_logout(stub)
    assert result.message == ["ended 1 web session"]
    assert (await http_get(stub.port, raw))[0] == 401
    assert WebPlugin._command_logout(stub).message == ["ended 0 web sessions"]


async def test_status_shows_routes_by_owner_and_sessions(stub: Any) -> None:
    await stub._restart(0)
    add(stub, subpath="one")
    add(stub, subpath="two")
    stub.caller = "plugins.test.other"
    add(stub, owner="plugins.test.other", subpath="x")
    stub.sessions.create(100)
    text = status_text(stub)
    assert "Routes        : 3 - plugins.test.caller (2), plugins.test.other (1)" in text
    assert "Sessions      : 1" in text


async def test_status_counts_unlisted_routes(stub: Any) -> None:
    add(stub, subpath="one")
    add(stub, subpath="two", listed=False)
    assert "Routes        : 2 - plugins.test.caller (2)" in status_text(stub)


async def test_status_with_no_routes(stub: Any) -> None:
    text = status_text(stub)
    assert "Routes        : 0" in text.splitlines()
    assert "Sessions      : 0" in text.splitlines()


async def _login_sid(stub: Any) -> str:
    token = stub.logins.issue()
    _, headers, _ = await http_get(stub.port, get_request(f"/login/{token}"))
    return str(headers["set-cookie"].split(";")[0].split("=", 1)[1])


async def _open_socket(stub: Any, sid: str, origin: str) -> Any:
    return await connect(
        f"ws://127.0.0.1:{stub.port}/ws",
        origin=origin,  # type: ignore[arg-type]
        additional_headers={"Cookie": f"bpsession={sid}"},
        open_timeout=5,
    )


async def test_logout_closes_sockets_and_the_reply_is_unchanged(stub: Any) -> None:
    await stub._restart(0)
    stub.settings["publicurl"] = f"http://127.0.0.1:{stub.port}"
    sid = await _login_sid(stub)
    conn = await _open_socket(stub, sid, f"http://127.0.0.1:{stub.port}")
    assert json.loads(await conn.recv())["type"] == "hello"
    assert "Sockets       : 1" in status_text(stub)
    result = WebPlugin._command_logout(stub)
    assert result.message == ["ended 1 web session"]
    with pytest.raises(ConnectionClosed):
        await conn.recv()
    assert (conn.close_code, conn.close_reason) == (4001, "session ended")


async def test_status_shows_zero_sockets(stub: Any) -> None:
    await stub._restart(0)
    assert "Sockets       : 0" in status_text(stub)


async def test_unload_closes_sockets_with_1001(stub: Any) -> None:
    await stub._restart(0)
    stub.settings["publicurl"] = f"http://127.0.0.1:{stub.port}"
    sid = await _login_sid(stub)
    conn = await _open_socket(stub, sid, f"http://127.0.0.1:{stub.port}")
    await conn.recv()
    WebPlugin._phook_close_server(stub)
    with pytest.raises(ConnectionClosed):
        await conn.recv()
    assert conn.close_code == 1001


async def test_the_allowed_origin_follows_publicurl(stub: Any) -> None:
    stub.settings["publicurl"] = "https://Proxy.example.net:443/"
    await stub._restart(0)
    sid = await _login_sid(stub)
    with pytest.raises(InvalidStatus) as info:
        await _open_socket(stub, sid, f"http://127.0.0.1:{stub.port}")
    assert info.value.response.status_code == 403
    conn = await _open_socket(stub, sid, "https://proxy.example.net")
    assert json.loads(await conn.recv())["proxy"] == __version__
    await conn.close()


def test_viewlogin_is_hidden_from_history_and_says_so_when_disabled(stub: Any) -> None:
    kwargs = WebPlugin._command_viewlogin.command_data.command["kwargs"]
    assert kwargs["show_in_history"] is False
    stub.settings["enabled"] = False
    result = WebPlugin._command_viewlogin(stub)
    assert "not enabled" in result.message[0]
    assert stub.logins._tokens == {}


async def test_viewlogin_link_starts_a_view_only_socket_and_login_a_full_one(stub: Any) -> None:
    await stub._restart(0)
    origin = f"http://127.0.0.1:{stub.port}"
    stub.settings["publicurl"] = origin
    views = {}
    for command in (WebPlugin._command_viewlogin, WebPlugin._command_login):
        (line,) = command(stub).message
        assert line.startswith(
            "View-only login link: " if command.__name__ == "_command_viewlogin" else "Login link: "
        )
        token = line.rsplit("/", 1)[1]
        _, headers, _ = await http_get(stub.port, get_request(f"/login/{token}"))
        sid = str(headers["set-cookie"].split(";")[0].split("=", 1)[1])
        conn = await _open_socket(stub, sid, origin)
        assert json.loads(await conn.recv())["type"] == "hello"
        views[command.__name__] = stub.sessions.is_view_only(sid)
        (server_side,) = [c for c in stub.server.sockets.connections() if c.id]
        assert server_side.view_only is views[command.__name__]
        await conn.close()
        for _ in range(200):
            if stub.server.sockets.count() == 0:
                break
            await asyncio.sleep(0.01)
    assert views == {"_command_viewlogin": True, "_command_login": False}

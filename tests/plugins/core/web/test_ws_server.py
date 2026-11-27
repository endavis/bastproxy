"""The /ws endpoint on the listener: handshake refusals, messages, limits and closing (#842)."""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidMessage, InvalidStatus

from bastproxy.plugins.core.web.libs import _ws
from bastproxy.plugins.core.web.libs._http import CSP, MAX_CONNECTIONS
from bastproxy.plugins.core.web.libs._server import WebApp, WebServer
from bastproxy.plugins.core.web.libs._store import PageStore, SessionStore

from .conftest import MakeCert, get_request, http_get, needs_openssl

OPEN_TIMEOUT = 5


class Env:
    """A listener with a session store and one logged-in session."""

    def __init__(self, server: WebServer, sessions: SessionStore, port: int) -> None:
        self.server = server
        self.sessions = sessions
        self.port = port
        self.sid = sessions.create(3600)

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    async def open(
        self, *, sid: str | None = "", origin: str | None = "", **kwargs: Any
    ) -> ClientConnection:
        headers = {}
        cookie = self.sid if sid == "" else sid
        if cookie is not None:
            headers["Cookie"] = f"bpsession={cookie}"
        return await connect(
            f"ws://127.0.0.1:{self.port}/ws",
            origin=self.origin if origin == "" else origin,  # type: ignore[arg-type]
            additional_headers=headers,
            open_timeout=OPEN_TIMEOUT,
            **kwargs,
        )


@pytest.fixture
async def env() -> AsyncIterator[Env]:
    sessions = SessionStore()
    server = WebServer()
    holder: dict[str, Env] = {}
    app = WebApp(
        PageStore(),
        sessions=sessions,
        allowed_origins=lambda: [holder["env"].origin + "/"],
        proxy_version="9.9.9",
    )
    port = await server.start("127.0.0.1", 0, app, None)
    holder["env"] = Env(server, sessions, port)
    yield holder["env"]
    server.close()
    await server.wait_closed()


async def recv_json(conn: ClientConnection) -> dict[str, Any]:
    async with asyncio.timeout(OPEN_TIMEOUT):
        data = json.loads(await conn.recv())
    assert isinstance(data, dict)
    return data


async def closed_with(conn: ClientConnection) -> tuple[int, str]:
    async with asyncio.timeout(OPEN_TIMEOUT):
        with pytest.raises(ConnectionClosed):
            await conn.recv()
    assert conn.close_code is not None
    return conn.close_code, conn.close_reason or ""


async def wait_for(condition: Any) -> None:
    for _ in range(OPEN_TIMEOUT * 100):
        if condition():
            return
        await asyncio.sleep(0.01)
    pytest.fail("the condition did not become true")


async def refused(env: Env, **kwargs: Any) -> InvalidStatus:
    with pytest.raises(InvalidStatus) as info:
        await env.open(**kwargs)
    return info.value


async def test_hello_carries_a_connection_id_and_no_session_id(env: Env) -> None:
    async with await env.open() as conn:
        hello = await recv_json(conn)
        assert hello["v"] == 1
        assert hello["type"] == "hello"
        assert hello["protocol"] == 1
        assert hello["proxy"] == "9.9.9"
        assert isinstance(hello["connection"], str)
        assert hello["connection"] != env.sid
        assert env.sid not in json.dumps(hello)
        assert set(hello) == {"v", "type", "protocol", "proxy", "connection", "topics"}
        assert hello["topics"] == []
        assert env.server.sockets.count() == 1
    await wait_for(lambda: env.server.sockets.count() == 0)


@pytest.mark.parametrize("sid", [None, "forged"])
async def test_no_or_forged_session_is_401(env: Env, sid: str | None) -> None:
    error = await refused(env, sid=sid)
    assert error.response.status_code == 401
    assert env.server.sockets.count() == 0


async def test_refused_responses_carry_the_security_headers(env: Env) -> None:
    error = await refused(env, origin="http://evil.example")
    headers = error.response.headers
    assert error.response.status_code == 403
    assert headers["Content-Security-Policy"] == CSP
    assert headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.parametrize("origin", ["http://evil.example", "null", None])
async def test_a_foreign_or_missing_origin_is_403(env: Env, origin: str | None) -> None:
    assert (await refused(env, origin=origin)).response.status_code == 403


async def test_the_origin_is_compared_normalised(env: Env) -> None:
    async with await env.open(origin=f"HTTP://127.0.0.1:{env.port}"):
        pass


async def test_a_repeated_origin_is_403(env: Env) -> None:
    raw = (
        f"GET /ws HTTP/1.1\r\nHost: x\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
        f"Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nSec-WebSocket-Version: 13\r\n"
        f"Cookie: bpsession={env.sid}\r\nOrigin: {env.origin}\r\nOrigin: {env.origin}\r\n\r\n"
    ).encode()
    assert (await http_get(env.port, raw))[0] == 403


def upgrade_request(env: Env, *, key: bool = True, connection: bool = True) -> bytes:
    lines = ["GET /ws HTTP/1.1", "Host: x", "Upgrade: websocket"]
    if connection:
        lines.append("Connection: Upgrade")
    if key:
        lines.append("Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==")
    lines += [
        "Sec-WebSocket-Version: 13",
        f"Cookie: bpsession={env.sid}",
        f"Origin: {env.origin}",
    ]
    return ("\r\n".join(lines) + "\r\n\r\n").encode()


async def test_a_missing_key_is_400_and_a_missing_connection_header_is_426(env: Env) -> None:
    status, headers, _ = await http_get(env.port, upgrade_request(env, key=False))
    assert status == 400
    assert headers["content-security-policy"] == CSP
    status, headers, _ = await http_get(env.port, upgrade_request(env, connection=False))
    assert status == 426
    assert headers["upgrade"] == "websocket"


async def test_ws_without_an_upgrade_is_404(env: Env) -> None:
    assert (await http_get(env.port, get_request("/ws")))[0] == 404


async def test_pages_are_unchanged_with_a_socket_open(env: Env) -> None:
    async with await env.open() as conn:
        await recv_json(conn)
        raw = f"GET / HTTP/1.1\r\nCookie: bpsession={env.sid}\r\n\r\n".encode()
        status, headers, _ = await http_get(env.port, raw)
        assert status == 200
        assert headers["content-security-policy"] == CSP


async def test_unknown_type_gives_an_error_and_the_socket_stays_open(env: Env) -> None:
    async with await env.open() as conn:
        await recv_json(conn)
        await conn.send(json.dumps({"v": 1, "type": "nope"}))
        error = await recv_json(conn)
        assert error == {
            "v": 1,
            "type": "error",
            "code": "unknown_type",
            "message": "unknown message type 'nope'",
            "for": "nope",
        }
        await conn.send("{not json")
        assert (await recv_json(conn))["code"] == "bad_json"
        await conn.send(json.dumps({"v": 2, "type": "x"}))
        assert (await recv_json(conn))["code"] == "version"
        await conn.send("[]")
        assert (await recv_json(conn))["code"] == "bad_message"


async def test_sync_and_async_handlers_run_and_a_raising_one_gives_internal(env: Env) -> None:
    hub = env.server.sockets

    def sync(conn: _ws.SocketConnection, message: dict[str, Any]) -> None:
        conn.send({"v": 1, "type": "echo", "n": message["n"]})

    async def slow(conn: _ws.SocketConnection, message: dict[str, Any]) -> None:
        await asyncio.sleep(0)
        conn.send({"v": 1, "type": "late"})

    def boom(conn: _ws.SocketConnection, message: dict[str, Any]) -> None:
        raise RuntimeError

    hub.register("sync", sync)
    hub.register("slow", slow)
    hub.register("boom", boom)
    async with await env.open() as conn:
        await recv_json(conn)
        await conn.send(json.dumps({"v": 1, "type": "sync", "n": 3}))
        assert await recv_json(conn) == {"v": 1, "type": "echo", "n": 3}
        await conn.send(json.dumps({"v": 1, "type": "slow"}))
        assert (await recv_json(conn))["type"] == "late"
        await conn.send(json.dumps({"v": 1, "type": "boom"}))
        error = await recv_json(conn)
        assert error["code"] == "internal"
        assert error["for"] == "boom"
        await conn.send(json.dumps({"v": 1, "type": "sync", "n": 4}))
        assert (await recv_json(conn))["n"] == 4


async def test_a_handler_that_times_out_gives_internal(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("bastproxy.plugins.core.web.libs._http.HANDLER_TIMEOUT", 0.05)

    async def hang(conn: _ws.SocketConnection, message: dict[str, Any]) -> None:
        await asyncio.sleep(10)

    env.server.sockets.register("hang", hang)
    async with await env.open() as conn:
        await recv_json(conn)
        await conn.send(json.dumps({"v": 1, "type": "hang"}))
        assert (await recv_json(conn))["code"] == "internal"


async def test_a_binary_frame_closes_with_1003_and_the_listener_survives(env: Env) -> None:
    async with await env.open() as conn:
        await recv_json(conn)
        await conn.send(b"\x00")
        assert (await closed_with(conn))[0] == 1003
    assert (await http_get(env.port, get_request("/nothing")))[0] == 404


async def test_an_oversized_message_closes_with_1009(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_ws, "MAX_MESSAGE", 100)
    async with await env.open() as conn:
        await recv_json(conn)
        await conn.send("x" * 500)
        assert (await closed_with(conn))[0] == 1009
    assert (await http_get(env.port, get_request("/nothing")))[0] == 404


async def test_a_full_send_queue_closes_with_1008(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_ws, "SEND_QUEUE_LIMIT", 2)
    async with await env.open() as conn:
        await recv_json(conn)
        (server_side,) = list(env.server.sockets._connections)
        results = [server_side.send({"v": 1, "type": "x"}) for _ in range(10)]
        assert False in results
        code, reason = await closed_with(conn)
        assert (code, reason) == (1008, "send queue full")


async def test_no_traffic_closes_with_1011(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_ws, "PING_INTERVAL", 0.05)
    monkeypatch.setattr(_ws, "PING_TIMEOUT", 0.05)
    monkeypatch.setattr(_ws, "CLOSE_TIMEOUT", 0.1)  # the raw client never answers the close
    # a raw client never answers the pings (a websockets client would pong)
    reader, writer = await asyncio.open_connection("127.0.0.1", env.port)
    writer.write(upgrade_request(env))
    await writer.drain()
    async with asyncio.timeout(OPEN_TIMEOUT):
        data = await reader.read()
    writer.close()
    assert b"101 Switching Protocols" in data
    assert b"\x88" in data
    assert (1011).to_bytes(2, "big") + b"keepalive timeout" in data


async def test_an_ended_session_closes_with_4001(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_ws, "PING_INTERVAL", 0.05)
    async with await env.open() as conn:
        await recv_json(conn)
        env.sessions.clear()
        assert await closed_with(conn) == (4001, "session ended")


async def test_a_live_client_stays_connected_across_keepalive_ticks(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_ws, "PING_INTERVAL", 0.05)
    monkeypatch.setattr(_ws, "PING_TIMEOUT", 0.05)
    async with await env.open() as conn:
        await recv_json(conn)
        await asyncio.sleep(0.4)
        await conn.send(json.dumps({"v": 1, "type": "nope"}))
        assert (await recv_json(conn))["code"] == "unknown_type"


async def test_sockets_count_against_the_connection_cap(env: Env) -> None:
    conns = [await env.open() for _ in range(MAX_CONNECTIONS)]
    try:
        for conn in conns:
            await recv_json(conn)
        with pytest.raises((OSError, ConnectionClosed, InvalidMessage)):
            await env.open()
    finally:
        for conn in conns:
            await conn.close()


async def test_server_close_sends_1001(env: Env) -> None:
    async with await env.open() as conn:
        await recv_json(conn)
        env.server.close()
        assert await closed_with(conn) == (1001, "server shutting down")


@needs_openssl
async def test_a_socket_over_tls(tmp_path: Any, make_cert: MakeCert) -> None:
    import ssl

    from bastproxy.plugins.core.web.libs._tls import CertManager

    certfile, keyfile = make_cert("localhost")
    manager = CertManager(certfile, keyfile)
    manager.load()
    sessions = SessionStore()
    sid = sessions.create(60)
    server = WebServer()
    app = WebApp(
        PageStore(),
        sessions=sessions,
        allowed_origins=lambda: ["https://localhost"],
        proxy_version="1",
    )
    port = await server.start("127.0.0.1", 0, app, manager)
    context = ssl.create_default_context(cafile=str(certfile))
    try:
        async with connect(
            f"wss://localhost:{port}/ws",
            origin="https://localhost",  # type: ignore[arg-type]
            additional_headers={"Cookie": f"bpsession={sid}"},
            ssl=context,
            open_timeout=OPEN_TIMEOUT,
        ) as conn:
            assert (await recv_json(conn))["type"] == "hello"
    finally:
        server.close()
        await server.wait_closed()

"""Tests for the window size sent to the MUD over NAWS (#308)."""

import asyncio
import inspect
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
import telnetlib3
from telnetlib3 import open_connection
from telnetlib3.telopt import DO, IAC, NAWS

from bastproxy.libs.net.mud import MudTelnetClient
from bastproxy.libs.net.naws import (
    DEFAULT_COLS,
    DEFAULT_ROWS,
    NAWS_MAX,
    WINDOW_SIZE,
    naws_frame,
)
from tests.libs.net.clients import (
    ProxyServer,
    ScriptedMud,
    naws_frames,
    proxy_server,
    sb_frame,
    scripted_mud,
    wait_until,
)


class FakeConn:
    """The attributes of a ClientConnection that the forwarder reads."""

    def __init__(
        self,
        uuid: str,
        cols: int = 100,
        rows: int = 30,
        *,
        reported: bool = True,
        view_only: bool = False,
    ) -> None:
        self.uuid = uuid
        self.cols = cols
        self.rows = rows
        self.naws_reported = reported
        self.view_only = view_only
        self.connected = True


class FakeOption:
    def __init__(self, on: bool) -> None:
        self.on = on

    def enabled(self, _opt: bytes) -> bool:
        return self.on


class FakeWriter:
    def __init__(self, naws_on: bool = True) -> None:
        self.local_option = FakeOption(naws_on)
        self.closing = False
        self.frames: list[bytes] = []

    def is_closing(self) -> bool:
        return self.closing

    def send_iac(self, buf: bytes) -> None:
        self.frames.append(buf)

    @property
    def sizes(self) -> list[tuple[int, int]]:
        return naws_frames(b"".join(self.frames))


def _writer() -> FakeWriter:
    writer = FakeWriter()
    WINDOW_SIZE.mud_reply()  # the reply to DO NAWS, which comes before the shell runs
    WINDOW_SIZE.mud_connected(writer)
    return writer


# frame and defaults ------------------------------------------------------------


def test_frame_packs_big_endian_and_escapes_iac() -> None:
    assert naws_frame(255, 40) == IAC + b"\xfa" + NAWS + b"\x00\xff\xff\x00\x28" + IAC + b"\xf0"
    assert naws_frame(70000, 70000) == naws_frame(NAWS_MAX, NAWS_MAX)
    assert naws_frames(naws_frame(255, 255)) == [(255, 255)]


def test_defaults_match_telnetlib3() -> None:
    params = inspect.signature(telnetlib3.open_connection).parameters
    assert params["cols"].default == DEFAULT_COLS
    assert params["rows"].default == DEFAULT_ROWS


# the active-client rule --------------------------------------------------------


def test_one_client_login_sends_once() -> None:
    writer = _writer()
    a = FakeConn("a", 120, 40)
    WINDOW_SIZE.client_ready(a)
    WINDOW_SIZE.client_ready(a)
    WINDOW_SIZE.client_resized(a)
    assert writer.sizes == [(120, 40)]


def test_most_recently_active_client_wins() -> None:
    writer = _writer()
    a, b = FakeConn("a", 100, 30), FakeConn("b", 150, 50)
    WINDOW_SIZE.client_ready(a)
    WINDOW_SIZE.client_ready(b)
    WINDOW_SIZE.client_input(a)
    assert writer.sizes == [(100, 30), (150, 50), (100, 30)]
    WINDOW_SIZE.client_input(b)
    assert writer.sizes[-1] == (150, 50)
    # a resize of the inactive client sends nothing until it is active again
    a.cols = 90
    WINDOW_SIZE.client_resized(a)
    assert writer.sizes[-1] == (150, 50)
    count = len(writer.sizes)
    WINDOW_SIZE.client_input(a)
    assert writer.sizes[count:] == [(90, 30)]


def test_resize_of_the_active_client_is_forwarded() -> None:
    writer = _writer()
    a = FakeConn("a")
    WINDOW_SIZE.client_ready(a)
    a.cols, a.rows = 200, 60
    WINDOW_SIZE.client_resized(a)
    assert writer.sizes == [(100, 30), (200, 60)]


def test_ineligible_clients_never_change_the_size() -> None:
    writer = _writer()
    base = FakeConn("base", 100, 30)
    WINDOW_SIZE.client_ready(base)
    viewer = FakeConn("v", 10, 10, view_only=True)
    silent = FakeConn("s", 11, 11, reported=False)
    zero = FakeConn("z", 0, 0)
    for conn in (viewer, silent, zero):
        WINDOW_SIZE.client_ready(conn)
        WINDOW_SIZE.client_input(conn)
        WINDOW_SIZE.client_resized(conn)
    assert writer.sizes == [(100, 30)]


def test_fallback_when_the_active_client_goes() -> None:
    writer = _writer()
    a, b = FakeConn("a", 100, 30), FakeConn("b", 150, 50)
    WINDOW_SIZE.client_ready(a)
    WINDOW_SIZE.client_ready(b)
    WINDOW_SIZE.client_gone(b)
    assert writer.sizes[-1] == (100, 30)
    count = len(writer.sizes)
    a.connected = False
    WINDOW_SIZE.client_gone(a)
    assert len(writer.sizes) == count
    assert WINDOW_SIZE.target() == (100, 30)


def test_input_from_an_unknown_client_is_ignored() -> None:
    writer = _writer()
    WINDOW_SIZE.client_input(FakeConn("never"))
    assert writer.sizes == []


# modes -------------------------------------------------------------------------


def test_modes(caplog: pytest.LogCaptureFixture) -> None:
    writer = _writer()
    a = FakeConn("a", 100, 30)
    WINDOW_SIZE.client_ready(a)
    WINDOW_SIZE.set_mode("off")
    assert writer.sizes[-1] == (80, 25)
    WINDOW_SIZE.client_input(a)
    assert writer.sizes[-1] == (80, 25)
    WINDOW_SIZE.set_mode("120x40")
    assert writer.sizes[-1] == (120, 40)
    WINDOW_SIZE.set_mode("client")
    assert writer.sizes[-1] == (100, 30)
    for bad in ("bogus", "0x10", "70000x10"):
        with caplog.at_level(logging.WARNING):
            WINDOW_SIZE.set_mode(bad)
        assert WINDOW_SIZE.target() == (100, 30)
    assert "using client" in caplog.text


def test_nothing_is_sent_while_the_link_cannot_take_it() -> None:
    a = FakeConn("a")
    WINDOW_SIZE.client_ready(a)  # before mud_connected
    off = FakeWriter(naws_on=False)
    WINDOW_SIZE.mud_connected(off)
    closing = FakeWriter()
    closing.closing = True
    WINDOW_SIZE.mud_connected(closing)
    assert off.frames == []
    assert closing.frames == []


def test_mud_reply_is_rows_cols_and_prevents_a_duplicate() -> None:
    WINDOW_SIZE.client_ready(FakeConn("a", 120, 40))
    assert WINDOW_SIZE.mud_reply() == (40, 120)
    writer = FakeWriter()
    WINDOW_SIZE.mud_connected(writer)
    assert writer.frames == []
    WINDOW_SIZE.mud_disconnected()
    assert WINDOW_SIZE.mud_reply() == (40, 120)


# the real links ----------------------------------------------------------------


@asynccontextmanager
async def mud_link() -> AsyncIterator[tuple[ScriptedMud, Any]]:
    """Connect a ``MudTelnetClient`` to a scripted MUD that asks for NAWS."""
    done = asyncio.Event()

    async def script(mud: ScriptedMud, writer: asyncio.StreamWriter) -> None:
        writer.write(IAC + DO + NAWS)
        await writer.drain()
        await mud.wait_for(lambda: bool(naws_frames(bytes(mud.received))))
        await done.wait()

    async with scripted_mud(script) as mud:
        _reader, writer = await asyncio.wait_for(
            open_connection(
                "127.0.0.1",
                mud.port,
                client_factory=MudTelnetClient,
                compression=False,
                connect_maxwait=0.5,
                encoding="utf8",
            ),
            5,
        )
        WINDOW_SIZE.mud_connected(writer)
        try:
            yield mud, writer
        finally:
            done.set()
            writer.close()
            WINDOW_SIZE.mud_disconnected()


def _pack(cols: int, rows: int) -> bytes:
    return sb_frame(NAWS, cols.to_bytes(2, "big") + rows.to_bytes(2, "big"))


async def _client(proxy: ProxyServer, size: tuple[int, int] | None) -> Any:
    """Connect one scripted client; ``None`` is a client that refuses NAWS."""
    before = len(proxy.connections)
    if size is None:
        client = await proxy.connect()
    else:
        client = await proxy.connect(agree={NAWS}, after_answer={NAWS: _pack(*size)})
    await wait_until(lambda: len(proxy.connections) > before)
    return client


async def _clients(proxy: ProxyServer, sizes: list[tuple[int, int] | None]) -> list[Any]:
    """Connect one scripted client per entry."""
    return [await _client(proxy, size) for size in sizes]


def _last(mud: ScriptedMud) -> tuple[int, int]:
    return naws_frames(bytes(mud.received))[-1]


async def test_first_reply_is_the_default_then_login_sends_the_client_size() -> None:
    async with proxy_server(connections=True) as proxy, mud_link() as (mud, _w):
        [client] = await _clients(proxy, [(132, 43)])
        await mud.wait_for(lambda: bool(naws_frames(bytes(mud.received))))
        assert naws_frames(bytes(mud.received)) == [(80, 25)]
        proxy.login(0)
        await mud.wait_for(lambda: _last(mud) == (132, 43))
        # a resize from the logged-in client is forwarded
        client.send(_pack(160, 50))
        await mud.wait_for(lambda: _last(mud) == (160, 50))


async def test_two_clients_follow_the_most_recent_input() -> None:
    async with proxy_server(connections=True) as proxy, mud_link() as (mud, _w):
        _a, b = await _clients(proxy, [(100, 30), (150, 50)])
        proxy.login(0)
        proxy.login(1)
        await mud.wait_for(lambda: _last(mud) == (150, 50))
        WINDOW_SIZE.client_input(proxy.connections[0])
        await mud.wait_for(lambda: _last(mud) == (100, 30))
        # client 1 resizes while client 0 is active: the MUD does not hear it
        b.send(_pack(170, 60))
        await wait_until(lambda: proxy.connections[1].cols == 170)
        await asyncio.sleep(0.2)
        assert _last(mud) == (100, 30)
        WINDOW_SIZE.client_input(proxy.connections[1])
        await mud.wait_for(lambda: _last(mud) == (170, 60))
        proxy.logout(1)
        await mud.wait_for(lambda: _last(mud) == (100, 30))


async def test_client_refusing_naws_sends_nothing() -> None:
    async with proxy_server(connections=True) as proxy, mud_link() as (mud, _w):
        await _clients(proxy, [None])
        proxy.login(0)
        WINDOW_SIZE.client_input(proxy.connections[0])
        await asyncio.sleep(0.2)
        assert naws_frames(bytes(mud.received)) == [(80, 25)]


async def test_view_only_client_sends_nothing() -> None:
    async with proxy_server(connections=True) as proxy, mud_link() as (mud, _w):
        await _clients(proxy, [(90, 20)])
        proxy.login(0, view_only=True)
        WINDOW_SIZE.client_input(proxy.connections[0])
        await asyncio.sleep(0.2)
        assert naws_frames(bytes(mud.received)) == [(80, 25)]


async def test_first_reply_carries_a_size_known_before_the_mud_asked() -> None:
    WINDOW_SIZE.client_ready(FakeConn("a", 111, 33))
    async with mud_link() as (mud, _w):
        await mud.wait_for(lambda: bool(naws_frames(bytes(mud.received))))
        assert naws_frames(bytes(mud.received)) == [(111, 33)]


async def test_connection_sets_the_server_hook() -> None:
    async with proxy_server(connections=True) as proxy:
        await _clients(proxy, [(100, 30)])
        assert proxy.protocol_of(0).on_naws_cb == proxy.connections[0]._on_naws

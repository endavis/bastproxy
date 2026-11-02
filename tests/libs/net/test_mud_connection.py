"""Tests for the MUD-side telnetlib3 client behavior (#39)."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import pytest
from telnetlib3 import open_connection
from telnetlib3.telopt import DO, DONT, GMCP, IAC, MCCP2_COMPRESS, WILL

from bastproxy.libs.net.mud import (
    MudConnection,
    MudTelnetClient,
    unicode_readline_monkeypatch,
)

Handler = Callable[[asyncio.StreamReader, asyncio.StreamWriter], Awaitable[None]]

TIMEOUT = 5


@asynccontextmanager
async def raw_server(handler: Handler) -> AsyncIterator[int]:
    """Run a raw TCP server on an ephemeral port and yield the port."""
    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        yield port
    finally:
        server.close()
        await server.wait_closed()


async def _connect(port: int) -> tuple:
    return await asyncio.wait_for(
        open_connection(
            "127.0.0.1",
            port,
            client_factory=MudTelnetClient,
            compression=False,
            connect_maxwait=0.5,
            encoding="utf8",
        ),
        TIMEOUT,
    )


@pytest.mark.parametrize(
    "separator",
    [b"\r\n", b"\n\r", b"\r\x00", b"\r", b"\n"],
)
async def test_patched_readline_splits_on_separator(separator: bytes) -> None:
    async def handler(_r: asyncio.StreamReader, w: asyncio.StreamWriter) -> None:
        w.write(b"one" + separator + b"two" + separator + b"three")
        await w.drain()
        w.close()

    async with raw_server(handler) as port:
        reader, writer = await _connect(port)
        reader.readline = unicode_readline_monkeypatch.__get__(reader)
        lines = [await asyncio.wait_for(reader.readline(), TIMEOUT) for _ in range(3)]
        writer.close()

    expected_sep = "\r" if separator == b"\r\x00" else separator.decode()
    assert lines == ["one" + expected_sep, "two" + expected_sep, "three"]


async def _negotiate_and_collect(offer: bytes) -> bytes:
    """Offer an option to the client and return all bytes the server received."""
    received = bytearray()

    async def handler(r: asyncio.StreamReader, w: asyncio.StreamWriter) -> None:
        w.write(IAC + WILL + offer)
        await w.drain()
        try:
            while data := await asyncio.wait_for(r.read(4096), 1.0):
                received.extend(data)
        except TimeoutError:
            pass
        w.close()

    async with raw_server(handler) as port:
        _, writer = await _connect(port)
        await asyncio.sleep(1.2)
        writer.close()
    return bytes(received)


async def test_gmcp_is_declined() -> None:
    received = await _negotiate_and_collect(GMCP)
    assert IAC + DO + GMCP not in received
    assert b"Core.Hello" not in received
    assert IAC + DONT + GMCP in received


async def test_mccp2_is_refused() -> None:
    received = await _negotiate_and_collect(MCCP2_COMPRESS)
    assert IAC + DO + MCCP2_COMPRESS not in received
    assert IAC + DONT + MCCP2_COMPRESS in received


async def test_client_never_announces_gmcp() -> None:
    received = await _negotiate_and_collect(b"\x01")
    assert IAC + WILL + GMCP not in received


async def test_connect_to_mud_uses_parity_options(monkeypatch: pytest.MonkeyPatch) -> None:
    """connect_to_mud passes the MUD client factory and refuses MCCP."""
    from bastproxy.libs.net import mud

    calls: list[dict] = []

    async def fake_open_connection(*args: object, **kwargs: object) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(mud, "open_connection", fake_open_connection)
    await mud.MudConnection("127.0.0.1", "4000").connect_to_mud()

    assert len(calls) == 1
    assert calls[0]["client_factory"] is MudTelnetClient
    assert calls[0]["compression"] is False


def _make_recorder(calls: list[list[str]]) -> Callable[..., Callable[[], None]]:
    def factory(data: object) -> Callable[[], None]:
        def run() -> None:
            calls.append([str(line) for line in data])  # type: ignore[attr-defined]

        return run

    return factory


async def _run_mud_read(
    monkeypatch: pytest.MonkeyPatch, payload: bytes
) -> tuple[MudConnection, list[list[str]]]:
    from telnetlib3.stream_reader import TelnetReaderUnicode

    from bastproxy.libs.net import mud

    calls: list[list[str]] = []
    monkeypatch.setattr(mud, "ProcessDataToClient", _make_recorder(calls))
    conn = MudConnection("127.0.0.1", "4000")
    reader = TelnetReaderUnicode(fn_encoding=lambda **_kw: "utf8")
    if payload:
        reader.feed_data(payload)
    reader.feed_eof()
    conn.reader = reader
    conn.connected = True
    await asyncio.wait_for(conn.mud_read(), TIMEOUT)
    return conn, calls


@pytest.mark.asyncio
async def test_mud_read_processes_data_read_with_eof(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lines read in the same pass as EOF are delivered (#64)."""
    conn, calls = await _run_mud_read(monkeypatch, b"Goodbye!\r\nConnection closed.\r\n")
    assert conn.connected is False
    flat = [line for call in calls for line in call]
    assert len(flat) == 2
    assert "Goodbye!" in flat[0]
    assert "Connection closed." in flat[1]


@pytest.mark.asyncio
async def test_mud_read_eof_without_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """EOF with nothing read does not call ProcessDataToClient."""
    conn, calls = await _run_mud_read(monkeypatch, b"")
    assert conn.connected is False
    assert calls == []

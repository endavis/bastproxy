"""Tests for the option, idle, line and byte details of the client and mud links (#422)."""

import asyncio
import zlib
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from telnetlib3.telopt import GA, IAC, WILL, name_option

from bastproxy.libs.net import client as client_mod
from bastproxy.libs.net import mud as mud_module
from bastproxy.libs.net.client import ClientConnection
from bastproxy.libs.net.mud import MudConnection, MudTelnetClient, MudTelnetReader
from bastproxy.libs.net.negotiation import option_names
from bastproxy.libs.records import NetworkDataLine
from bastproxy.libs.records.enums import LineType
from tests.libs.net.clients import (
    ScriptedClient,
    ScriptedMud,
    proxy_server,
    scripted_mud,
    wait_until,
)
from tests.libs.net.test_mccp import START2, _connect_keeping_protocol, _offer_m2

TIMEOUT = 5


def _timedelta_api(calls: list[tuple[Any, Any]] | None = None) -> Callable[[str], Any]:
    def api(_name: str) -> Callable[[Any, Any], str]:
        def to_string(start: Any, end: Any) -> str:
            if calls is not None:
                calls.append((start, end))
            return "formatted"

        return to_string

    return api


# option_names -------------------------------------------------------------


def test_option_names_keeps_enabled_sorted_and_names_unknown_bytes() -> None:
    options = {bytes([200]): True, bytes([201]): False, bytes([1]): True, bytes([3]): None}
    assert option_names(options) == sorted([name_option(bytes([200])), name_option(bytes([1]))])
    assert name_option(bytes([200])) in option_names(options)
    assert option_names({}) == []


# ClientConnection ----------------------------------------------------------


def _writer() -> MagicMock:
    writer = MagicMock()
    writer.protocol = None
    writer.connection_closed = False
    writer.drain = AsyncMock()
    writer.get_extra_info.return_value = ("127.0.0.1", 5555)
    return writer


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> ClientConnection:
    monkeypatch.setattr(client_mod, "API", lambda owner_id: MagicMock())
    return ClientConnection("127.0.0.1", "5555", "telnet", MagicMock(), _writer())


def test_client_telnet_options_come_from_the_writer() -> None:
    conn = object.__new__(ClientConnection)
    conn.writer = SimpleNamespace(  # type: ignore[assignment]
        local_option={bytes([1]): True, bytes([3]): False},
        remote_option={bytes([200]): True},
    )
    local, remote = conn.telnet_options()
    assert local == [name_option(bytes([1]))]
    assert remote == [name_option(bytes([200]))]


def test_client_bytes_read_the_server_counters() -> None:
    conn = object.__new__(ClientConnection)
    conn.telnet_server = SimpleNamespace(tx_bytes=5, rx_bytes=9)  # type: ignore[assignment]
    assert (conn.bytes_sent, conn.bytes_received) == (5, 9)
    conn.telnet_server = None
    assert (conn.bytes_sent, conn.bytes_received) == (0, 0)


async def test_client_byte_counters_are_live_on_a_real_link() -> None:
    async with proxy_server(connections=True) as proxy:
        scripted = ScriptedClient()
        await scripted.connect(proxy.port)
        await scripted.wait_for(lambda: len(proxy.connections) > 0)
        conn = proxy.connections[0]
        await wait_until(lambda: conn.bytes_sent > 0)
        await asyncio.sleep(0.5)
        before = conn.bytes_received
        scripted.send(b"hello\r\n")
        await wait_until(lambda: conn.bytes_received > before)
        await asyncio.sleep(0.2)
        assert conn.bytes_received - before == 7
        await scripted.close()


async def test_client_read_counts_lines_not_eof(client: ClientConnection) -> None:
    client.process_data_from_not_logged_in_client = MagicMock()  # type: ignore[method-assign]
    client.reader.readline = AsyncMock(side_effect=["a\r\n", "b\r\n", ""])  # type: ignore[method-assign]
    await client.client_read()
    assert client.lines_received == 2


async def test_client_write_counts_io_lines_only(client: ClientConnection) -> None:
    io_line = NetworkDataLine("hello\r\n")
    empty = NetworkDataLine("")
    cmd = NetworkDataLine(IAC + GA, line_type=LineType.COMMAND_TELNET)
    for line in (io_line, empty, cmd):
        client.send_queue.put_nowait(line)
    task = asyncio.create_task(client.client_write())
    try:
        await wait_until(lambda: cmd.was_sent)
    finally:
        client.connected = False
        task.cancel()
    assert client.lines_sent == 1


# MudConnection --------------------------------------------------------------


def test_mud_connection_without_a_link() -> None:
    conn = MudConnection("127.0.0.1", "4000")
    assert (conn.bytes_sent, conn.bytes_received) == (0, 0)
    assert conn.idle == "-"
    assert conn.telnet_options() == ([], [])
    assert (conn.lines_sent, conn.lines_received) == (0, 0)


def test_mud_connection_reads_the_protocol_and_writer() -> None:
    calls: list[tuple[Any, Any]] = []
    conn = MudConnection("127.0.0.1", "4000")
    conn.api = _timedelta_api(calls)  # type: ignore[assignment]
    conn.protocol = SimpleNamespace(idle=12.0, tx_bytes=5, rx_bytes=9)  # type: ignore[assignment]
    conn.writer = SimpleNamespace(  # type: ignore[assignment]
        local_option={bytes([1]): True}, remote_option={bytes([200]): True, bytes([3]): False}
    )
    assert (conn.bytes_sent, conn.bytes_received) == (5, 9)
    assert conn.idle == "formatted"
    start, end = calls[0]
    assert (end - start).total_seconds() == 12.0
    assert conn.telnet_options() == ([name_option(bytes([1]))], [name_option(bytes([200]))])


async def test_mud_read_counts_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mud_module, "ProcessDataToClient", lambda data: lambda: None)
    conn = MudConnection("127.0.0.1", "4000")
    reader = MudTelnetReader(fn_encoding=lambda **_kw: "utf8")
    reader.feed_data(b"one\r\ntwo\r\n")
    reader.feed_eof()
    conn.reader = reader
    conn.connected = True
    await asyncio.wait_for(conn.mud_read(), TIMEOUT)
    assert conn.lines_received == 2


async def test_mud_write_counts_io_lines_only() -> None:
    conn = MudConnection("127.0.0.1", "4000")
    writes: list[str] = []

    class FakeWriter:
        connection_closed = False
        remote_option = SimpleNamespace(enabled=lambda _opt: False)

        def write(self, line: str) -> None:
            writes.append(line)

        def send_iac(self, line: bytes) -> None:
            conn.connected = False

    io_line = SimpleNamespace(
        is_io=True, is_command_telnet=False, line="look\r\n", was_sent=False, mask_log=False
    )
    empty = SimpleNamespace(
        is_io=True, is_command_telnet=False, line="", was_sent=False, mask_log=False
    )
    cmd = SimpleNamespace(is_io=False, is_command_telnet=True, line=IAC + GA, was_sent=False)
    conn.writer = FakeWriter()  # type: ignore[assignment]
    conn.connected = True
    for msg in (io_line, empty, cmd):
        conn.send_queue.put_nowait(msg)  # type: ignore[arg-type]
    await asyncio.wait_for(conn.mud_write(), TIMEOUT)
    assert writes == ["look\r\n"]
    assert conn.lines_sent == 1


# MudTelnetClient byte counters ------------------------------------------------


async def test_mud_plain_link_counts_both_directions() -> None:
    payload = IAC + WILL + bytes([200]) + b"one\r\ntwo\r\n"

    async def script(mud: ScriptedMud, w: asyncio.StreamWriter) -> None:
        w.write(payload)
        await w.drain()
        await mud.wait_for(lambda: b"look\r\n" in mud.received)

    async with scripted_mud(script) as mud:
        _reader, writer, protocol = await _connect_keeping_protocol(mud.port)
        await wait_until(lambda: protocol.rx_bytes >= len(payload))
        assert protocol.rx_bytes == len(payload)
        before = protocol.tx_bytes
        writer.write("look\r\n")
        await wait_until(lambda: b"look\r\n" in mud.received)
        assert protocol.tx_bytes - before == 6
        writer.close()


async def test_mud_mccp2_counts_the_inflated_stream_once() -> None:
    body = b"hello\r\nworld\r\n" * 40
    plain_before = IAC + WILL + bytes([200])

    async def script(_mud: ScriptedMud, w: asyncio.StreamWriter) -> None:
        c = zlib.compressobj()
        # the activating chunk mixes plain bytes, the SB and the compressed stream
        w.write(plain_before + START2 + c.compress(body) + c.flush(zlib.Z_SYNC_FLUSH))
        await w.drain()

    async with scripted_mud(_offer_m2(script)) as mud:
        _reader, writer, protocol = await _connect_keeping_protocol(mud.port)
        await wait_until(lambda: protocol.rx_bytes >= len(body))
        await asyncio.sleep(0.2)
        # the offer's WILL MCCP2 (3 bytes) arrived before the chunk
        expected = 3 + len(plain_before) + len(START2) + len(body)
        assert protocol.rx_bytes == expected
        writer.close()


def test_telnetlib3_hooks_exist() -> None:
    """Pin the private telnetlib3 names MudTelnetClient relies on."""
    from telnetlib3.client_base import BaseClient

    assert hasattr(BaseClient, "_trace_recv")
    assert MudTelnetClient._tx_bytes == 0

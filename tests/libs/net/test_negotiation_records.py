"""Tests for the telnet negotiation records made on the MUD and client links (#83)."""

import asyncio
import logging
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock

import pytest
from telnetlib3 import open_connection
from telnetlib3.telopt import (
    BINARY,
    DO,
    DONT,
    ECHO,
    GMCP,
    IAC,
    NAWS,
    NEW_ENVIRON,
    SB,
    SE,
    TTYPE,
    WILL,
    WONT,
)

from bastproxy.libs.net import negotiation as neg_mod
from bastproxy.libs.net.client import ClientConnection
from bastproxy.libs.net.mud import MudTelnetClient
from bastproxy.libs.net.negotiation import RecordingTelnetWriter, parse_iac
from bastproxy.libs.net.server import CustomTelnetServer, create_server
from bastproxy.libs.records import RMANAGER, TelnetNegotiation

IS = b"\x00"
SEND = b"\x01"
TIMEOUT = 5


@pytest.fixture(autouse=True)
def isolated_manager(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Give each test an empty record store."""
    monkeypatch.setattr(RMANAGER, "record_instances", {})
    monkeypatch.setattr(RMANAGER, "records", {})
    yield


def _records(link: str | None = None) -> list[TelnetNegotiation]:
    recs: list[TelnetNegotiation] = list(RMANAGER.records.get("TelnetNegotiation", {}).values())
    return [r for r in recs if link is None or r.link == link]


def _seen(link: str | None = None) -> set[tuple[str, str, str, bytes]]:
    return {(str(r.direction), r.command, r.option, r.data) for r in _records(link)}


# parse_iac ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("verb", "name"), [(DO, "DO"), (DONT, "DONT"), (WILL, "WILL"), (WONT, "WONT")]
)
def test_parse_each_verb(verb: bytes, name: str) -> None:
    assert parse_iac(IAC + verb + TTYPE) == [(name, TTYPE, b"", IAC + verb + TTYPE)]


def test_parse_several() -> None:
    buf = IAC + DO + NAWS + b"text" + IAC + WILL + BINARY
    assert [(c, o) for c, o, _d, _r in parse_iac(buf)] == [("DO", NAWS), ("WILL", BINARY)]


def test_parse_sb_unescapes_iac() -> None:
    raw = IAC + SB + NAWS + b"\x00" + IAC + IAC + IAC + SE
    assert parse_iac(raw) == [("SB", NAWS, b"\x00\xff", raw)]


def test_parse_sb_without_se_gives_partial() -> None:
    assert parse_iac(IAC + SB + TTYPE + IS + b"xt") == [
        ("SB", TTYPE, IS + b"xt", IAC + SB + TTYPE + IS + b"xt")
    ]


def test_parse_ignores_noise() -> None:
    assert parse_iac(IAC + SE) == []
    assert parse_iac(IAC + b"\xf9" + b"data" + IAC + b"\xef") == []
    assert parse_iac(b"") == []
    assert parse_iac(IAC + DO) == []


# MUD link ----------------------------------------------------------------


async def test_mud_link_records() -> None:
    async def handler(r: asyncio.StreamReader, w: asyncio.StreamWriter) -> None:
        w.write(IAC + DO + TTYPE + IAC + SB + TTYPE + SEND + IAC + SE + IAC + WILL + GMCP)
        await w.drain()
        await asyncio.sleep(0.5)
        w.close()

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        _reader, writer = await asyncio.wait_for(
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
        await asyncio.sleep(0.3)
        assert isinstance(writer, RecordingTelnetWriter)
        writer.close()
    finally:
        server.close()
        await server.wait_closed()
    seen = _seen("mud")
    assert ("received", "DO", "TTYPE", b"") in seen
    assert ("sent", "WILL", "TTYPE", b"") in seen
    assert ("received", "SB", "TTYPE", SEND) in seen
    assert any(
        d == "sent" and c == "SB" and o == "TTYPE" and p.startswith(IS) for d, c, o, p in seen
    )
    assert ("received", "WILL", "GMCP", b"") in seen
    assert ("sent", "DO", "GMCP", b"") in seen
    assert {r.link for r in _records()} == {"mud"}


# Client links ------------------------------------------------------------


async def _serve_clients(clients: int, script: Any) -> tuple[list[str], list[tuple[Any, bytes]]]:
    """Run a server and `clients` scripted raw clients; return writer link ids and raw data."""
    link_ids: list[str] = []
    done = asyncio.Event()

    async def shell(_reader: Any, writer: Any) -> None:
        link_ids.append(writer.link_id)
        writer.iac(WILL, ECHO)
        if len(link_ids) == clients:
            done.set()
        await asyncio.sleep(0.3)
        writer.close()

    srv = await create_server(
        host="127.0.0.1",
        port=0,
        shell=shell,
        encoding="utf8",
        compression=False,
        force_binary=True,
        connect_maxwait=0.3,
    )
    port = srv.sockets[0].getsockname()[1]
    raws: list[tuple[Any, bytes]] = []

    async def one() -> None:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        buf = b""
        for _ in range(8):
            try:
                chunk = await asyncio.wait_for(reader.read(4096), 0.15)
            except TimeoutError:
                continue
            if not chunk:
                break
            buf += chunk
            writer.write(script(chunk))
            await writer.drain()
        raws.append((None, buf))
        writer.close()

    try:
        await asyncio.wait_for(asyncio.gather(*(one() for _ in range(clients))), TIMEOUT)
        await asyncio.wait_for(done.wait(), TIMEOUT)
    finally:
        srv.close()
        await srv.wait_closed()
    return link_ids, raws


def _client_script(chunk: bytes) -> bytes:
    out = b""
    if IAC + DO + TTYPE in chunk:
        out += IAC + WILL + TTYPE
    if IAC + DO + NAWS in chunk:
        out += IAC + WILL + NAWS + IAC + SB + NAWS + b"\x00\x50\x00\x18" + IAC + SE
    if IAC + SB + TTYPE + SEND in chunk:
        out += IAC + SB + TTYPE + IS + b"xterm" + IAC + SE
    if IAC + DO + NEW_ENVIRON in chunk:
        out += IAC + WONT + NEW_ENVIRON
    return out


async def test_client_link_records() -> None:
    link_ids, _ = await _serve_clients(1, _client_script)
    seen = _seen(link_ids[0])
    assert ("sent", "DO", "NAWS", b"") in seen
    assert ("sent", "WILL", "BINARY", b"") in seen
    assert ("sent", "DO", "NEW_ENVIRON", b"") in seen
    assert ("sent", "SB", "TTYPE", SEND) in seen
    assert ("received", "WILL", "TTYPE", b"") in seen
    assert ("received", "SB", "TTYPE", IS + b"xterm") in seen
    assert ("received", "SB", "NAWS", b"\x00\x50\x00\x18") in seen
    assert ("sent", "WILL", "ECHO", b"") in seen
    assert {r.link for r in _records()} == {link_ids[0]}


async def test_concurrent_clients_have_distinct_links() -> None:
    link_ids, _ = await _serve_clients(2, _client_script)
    assert len(set(link_ids)) == 2
    assert {r.link for r in _records()} == set(link_ids)
    for link in link_ids:
        assert ("sent", "DO", "NAWS", b"") in _seen(link)


# ClientConnection ----------------------------------------------------------


def test_client_connection_adopts_link_id() -> None:
    writer = MagicMock()
    writer.link_id = "a" * 32
    conn = ClientConnection("h", "1", "telnet", MagicMock(), writer)
    assert conn.uuid == "a" * 32


def test_client_connection_mock_writer_gets_hex_uuid() -> None:
    conn = ClientConnection("h", "1", "telnet", MagicMock(), MagicMock())
    assert isinstance(conn.uuid, str)
    assert len(conn.uuid) == 32
    int(conn.uuid, 16)


# Robustness and wiring -----------------------------------------------------


async def test_record_failure_does_not_break_negotiation(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def boom(*_a: Any, **_k: Any) -> None:
        msg = "records broke"
        raise RuntimeError(msg)

    monkeypatch.setattr(neg_mod, "TelnetNegotiation", boom)
    with caplog.at_level(logging.ERROR):
        link_ids, raws = await _serve_clients(1, _client_script)
    assert link_ids
    assert IAC + DO + NAWS in raws[0][1]
    assert any("Could not record" in r.getMessage() for r in caplog.records)


def test_mud_client_uses_recording_writer() -> None:
    assert MudTelnetClient._writer_factory_encoding is RecordingTelnetWriter


async def test_server_defaults_to_recording_writer() -> None:
    assert CustomTelnetServer()._writer_factory_encoding is RecordingTelnetWriter


async def test_explicit_writer_factory_wins() -> None:
    class Other(RecordingTelnetWriter):
        pass

    server = CustomTelnetServer(writer_factory_encoding=Other)
    assert server._writer_factory_encoding is Other

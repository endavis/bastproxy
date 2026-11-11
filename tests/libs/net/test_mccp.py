"""Tests for MCCP2/MCCP3 on the MUD link and MCCP2 on the client links (#58, ADR-0001)."""

import asyncio
import logging
import zlib
from collections.abc import Iterator
from typing import Any

import pytest
from telnetlib3 import open_connection
from telnetlib3.telopt import (
    CMD_EOR,
    DO,
    DONT,
    GA,
    IAC,
    MCCP2_COMPRESS,
    MCCP3_COMPRESS,
    SB,
    SE,
    WILL,
    WONT,
)

from bastproxy.libs.net import mud as mud_module
from bastproxy.libs.net import server as server_module
from bastproxy.libs.net.client import ClientConnection
from bastproxy.libs.net.mud import MudLine, MudTelnetClient
from bastproxy.libs.records import RMANAGER, TelnetNegotiation
from tests.libs.net.clients import (
    TIMEOUT,
    ScriptedMud,
    proxy_server,
    scripted_mud,
)

START2 = IAC + SB + MCCP2_COMPRESS + IAC + SE
START3 = IAC + SB + MCCP3_COMPRESS + IAC + SE


@pytest.fixture(autouse=True)
def isolated_manager(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Give each test an empty record store."""
    monkeypatch.setattr(RMANAGER, "record_instances", {})
    monkeypatch.setattr(RMANAGER, "records", {})
    yield


def _seen(link: str) -> set[tuple[str, str, str, bytes]]:
    recs: list[TelnetNegotiation] = list(RMANAGER.records.get("TelnetNegotiation", {}).values())
    return {(str(r.direction), r.command, r.option, r.data) for r in recs if r.link == link}


# MUD link ----------------------------------------------------------------


async def _connect(port: int) -> tuple[Any, Any]:
    return await asyncio.wait_for(
        open_connection(
            "127.0.0.1",
            port,
            client_factory=MudTelnetClient,
            compression=True,
            connect_maxwait=0.3,
            encoding="utf8",
            force_binary=True,
        ),
        TIMEOUT,
    )


async def _lines(reader: Any, count: int) -> list[MudLine]:
    return [await asyncio.wait_for(reader.read_mud_line(), TIMEOUT) for _ in range(count)]


async def _text(reader: Any, size: int) -> str:
    """Read lines until ``size`` characters arrived; a split chunk may split a line."""
    out = ""
    while len(out) < size:
        rec = await asyncio.wait_for(reader.read_mud_line(), TIMEOUT)
        assert rec.text
        out += rec.text
    return out


def _offer_m2(script: Any) -> Any:
    """A MUD script that offers MCCP2, waits for the DO, then runs ``script``."""

    async def run(mud: ScriptedMud, w: asyncio.StreamWriter) -> None:
        w.write(IAC + WILL + MCCP2_COMPRESS)
        await w.drain()
        await mud.wait_for(lambda: IAC + DO + MCCP2_COMPRESS in mud.received)
        await script(mud, w)
        await asyncio.sleep(0.3)

    return run


async def test_mud_stream_is_decompressed_and_prompt_marked() -> None:
    async def script(_mud: ScriptedMud, w: asyncio.StreamWriter) -> None:
        c = zlib.compressobj()
        w.write(
            START2
            + c.compress(b"hello\r\nworld\r\nprompt> " + IAC + GA)
            + c.flush(zlib.Z_SYNC_FLUSH)
        )
        await w.drain()

    async with scripted_mud(_offer_m2(script)) as mud:
        reader, writer = await _connect(mud.port)
        got = await _lines(reader, 3)
        writer.close()
    assert got == [
        MudLine("hello\r\n", True, False),
        MudLine("world\r\n", True, False),
        MudLine("prompt> ", False, True),
    ]
    assert ("received", "WILL", "MCCP2_COMPRESS", b"") in _seen("mud")
    assert ("sent", "DO", "MCCP2_COMPRESS", b"") in _seen("mud")
    assert ("received", "SB", "MCCP2_COMPRESS", b"") in _seen("mud")


async def test_mud_eor_inside_compressed_stream_marks_prompt() -> None:
    async def script(_mud: ScriptedMud, w: asyncio.StreamWriter) -> None:
        c = zlib.compressobj()
        w.write(START2 + c.compress(b"hp> " + IAC + CMD_EOR) + c.flush(zlib.Z_SYNC_FLUSH))
        await w.drain()

    async with scripted_mud(_offer_m2(script)) as mud:
        reader, writer = await _connect(mud.port)
        got = await _lines(reader, 1)
        writer.close()
    assert got == [MudLine("hp> ", False, True)]


@pytest.mark.parametrize("offset", [1, 2, 4, 5, 6, 9, 14])
async def test_mud_stream_split_across_writes(offset: int) -> None:
    async def script(_mud: ScriptedMud, w: asyncio.StreamWriter) -> None:
        c = zlib.compressobj()
        data = START2 + c.compress(b"alpha\r\nbeta\r\n") + c.flush(zlib.Z_SYNC_FLUSH)
        w.write(data[:offset])
        await w.drain()
        await asyncio.sleep(0.1)
        w.write(data[offset:])
        await w.drain()

    async with scripted_mud(_offer_m2(script)) as mud:
        reader, writer = await _connect(mud.port)
        got = await _text(reader, len("alpha\r\nbeta\r\n"))
        writer.close()
    assert got == "alpha\r\nbeta\r\n"


@pytest.mark.parametrize("same_chunk", [True, False])
async def test_mud_clean_end_continues_plain_and_restarts(same_chunk: bool) -> None:
    async def script(_mud: ScriptedMud, w: asyncio.StreamWriter) -> None:
        c = zlib.compressobj()
        first = START2 + c.compress(b"one\r\n") + c.flush(zlib.Z_FINISH)
        if same_chunk:
            w.write(first + b"plain\r\n")
        else:
            w.write(first)
            await w.drain()
            await asyncio.sleep(0.1)
            w.write(b"plain\r\n")
        await w.drain()
        await asyncio.sleep(0.1)
        c2 = zlib.compressobj()
        w.write(START2 + c2.compress(b"again\r\n") + c2.flush(zlib.Z_SYNC_FLUSH))
        await w.drain()

    async with scripted_mud(_offer_m2(script)) as mud:
        reader, writer = await _connect(mud.port)
        got = await _text(reader, len("one\r\nplain\r\nagain\r\n"))
        writer.close()
    assert got == "one\r\nplain\r\nagain\r\n"


async def test_mud_broken_stream_closes_the_link(caplog: pytest.LogCaptureFixture) -> None:
    async def script(_mud: ScriptedMud, w: asyncio.StreamWriter) -> None:
        c = zlib.compressobj()
        w.write(START2 + c.compress(b"hello\r\n") + c.flush(zlib.Z_SYNC_FLUSH))
        await w.drain()
        await asyncio.sleep(0.2)
        w.write(b"\x00\xff\x13garbagegarbage")
        await w.drain()
        await asyncio.sleep(0.2)
        # a later, otherwise valid, chunk must not reach the reader either
        w.write(c.compress(b"later\r\n") + c.flush(zlib.Z_SYNC_FLUSH))
        await w.drain()

    caplog.set_level(logging.ERROR)
    async with scripted_mud(_offer_m2(script)) as mud:
        reader, writer = await _connect(mud.port)
        protocol = writer.protocol
        got = await _lines(reader, 2)
        await asyncio.sleep(0.4)
        eof = reader.at_eof()
        writer.close()
    assert got[0] == MudLine("hello\r\n", True, False)
    assert got[1].text == ""
    assert eof
    assert protocol.mccp2_failed is True
    assert any("MCCP2 decompression error" in r.message for r in caplog.records)
    everything = "".join(x.text for x in got)
    assert "�" not in everything
    assert "garbage" not in everything
    assert "later" not in everything


async def test_mud_chunk_over_the_inflation_limit_closes_the_link(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mud_module, "MCCP2_MAX_INFLATED_CHUNK", 1000)

    async def script(_mud: ScriptedMud, w: asyncio.StreamWriter) -> None:
        c = zlib.compressobj()
        w.write(START2 + c.compress(b"hello\r\n") + c.flush(zlib.Z_SYNC_FLUSH))
        await w.drain()
        await asyncio.sleep(0.2)
        w.write(c.compress(b"A" * 5000 + b"\r\n") + c.flush(zlib.Z_SYNC_FLUSH))
        await w.drain()

    caplog.set_level(logging.ERROR)
    async with scripted_mud(_offer_m2(script)) as mud:
        reader, writer = await _connect(mud.port)
        protocol = writer.protocol
        got = await _lines(reader, 2)
        await asyncio.sleep(0.4)
        eof = reader.at_eof()
        writer.close()
    assert got[0] == MudLine("hello\r\n", True, False)
    assert eof
    assert protocol.mccp2_failed is True
    assert any("inflation limit" in r.message for r in caplog.records)
    assert "A" not in "".join(x.text for x in got)


async def test_mud_chunk_under_the_inflation_limit_decodes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mud_module, "MCCP2_MAX_INFLATED_CHUNK", 1000)
    body = "B" * 900 + "\r\n"

    async def script(_mud: ScriptedMud, w: asyncio.StreamWriter) -> None:
        c = zlib.compressobj()
        w.write(START2 + c.compress(body.encode()) + c.flush(zlib.Z_SYNC_FLUSH))
        await w.drain()

    async with scripted_mud(_offer_m2(script)) as mud:
        reader, writer = await _connect(mud.port)
        got = await _text(reader, len(body))
        writer.close()
    assert got == body


async def test_mud_raw_deflate_on_first_chunk_decodes() -> None:
    async def script(_mud: ScriptedMud, w: asyncio.StreamWriter) -> None:
        c = zlib.compressobj(wbits=-zlib.MAX_WBITS)
        w.write(START2 + c.compress(b"raw\r\n") + c.flush(zlib.Z_SYNC_FLUSH))
        await w.drain()

    async with scripted_mud(_offer_m2(script)) as mud:
        reader, writer = await _connect(mud.port)
        got = await _lines(reader, 1)
        writer.close()
    assert got[0].text == "raw\r\n"


async def test_mud_garbage_on_first_chunk_closes_the_link() -> None:
    async def script(_mud: ScriptedMud, w: asyncio.StreamWriter) -> None:
        w.write(START2 + b"\x00\xff\x13garbagegarbage")
        await w.drain()

    async with scripted_mud(_offer_m2(script)) as mud:
        reader, writer = await _connect(mud.port)
        protocol = writer.protocol
        got = await _lines(reader, 1)
        writer.close()
    assert got[0].text == ""
    assert protocol.mccp2_failed is True


async def test_mud_mccp3_compresses_writes_until_wont() -> None:
    async def script(mud: ScriptedMud, w: asyncio.StreamWriter) -> None:
        w.write(IAC + WILL + MCCP3_COMPRESS)
        await w.drain()
        await mud.wait_for(lambda: START3 in mud.received)
        await mud.wait_for(lambda: bytes(mud.received).endswith(b"\x00\x00\xff\xff"))
        w.write(IAC + WONT + MCCP3_COMPRESS)
        await w.drain()
        await mud.wait_for(lambda: b"plain\r\n" in mud.received)

    async with scripted_mud(script) as mud:
        _reader, writer = await _connect(mud.port)
        await mud.wait_for(lambda: START3 in mud.received)
        writer.write("look\r\n")
        await mud.wait_for(lambda: len(mud.received) > mud.received.find(START3) + len(START3))
        await asyncio.sleep(0.5)
        writer.write("plain\r\n")
        await mud.wait_for(lambda: b"plain\r\n" in mud.received)
        writer.close()
    assert IAC + DO + MCCP3_COMPRESS in mud.received
    rest = bytes(mud.received)[bytes(mud.received).find(START3) + len(START3) :]
    inflater = zlib.decompressobj()
    assert inflater.decompress(rest) == b"look\r\n"
    assert inflater.eof
    assert inflater.unused_data == b"plain\r\n"


# Client links ------------------------------------------------------------


async def test_server_offers_mccp2_and_mccp3() -> None:
    async with proxy_server() as proxy:
        client = await proxy.connect()
        raw = bytes(client.raw)
        await client.close()
    assert IAC + WILL + MCCP2_COMPRESS in raw
    assert IAC + WILL + MCCP3_COMPRESS in raw


async def test_do_mccp3_is_answered_wont_when_compression_off() -> None:
    async with proxy_server(compression=False) as proxy:
        client = await proxy.connect()
        assert IAC + WILL + MCCP3_COMPRESS not in bytes(client.raw)
        client.send(IAC + DO + MCCP3_COMPRESS)
        await client.wait_for(lambda: IAC + WONT + MCCP3_COMPRESS in client.raw)
        await client.close()


async def test_clients_negotiate_independently() -> None:
    async with proxy_server() as proxy:
        accepting = await proxy.connect({MCCP2_COMPRESS})
        refusing = await proxy.connect()
        for queue in proxy.queues:
            queue.put_nowait("the same text\r\n")
        await accepting.wait_for(lambda: b"the same text" in accepting.text)
        await refusing.wait_for(lambda: b"the same text" in refusing.text)
        active = [w.mccp2_active for w in proxy.writers]
        for_record = ClientConnection.__new__(ClientConnection)
        for_record.writer = proxy.writers[0]
        record_active = for_record.mccp2_active
        accepting_raw = bytes(accepting.raw)
        refusing_raw = bytes(refusing.raw)
        starts = (accepting.mccp2_starts, refusing.mccp2_starts)
        await accepting.close()
        await refusing.close()
    assert starts == (1, 0)
    assert b"the same text" not in accepting_raw
    assert b"the same text" in refusing_raw
    assert START2 not in refusing_raw
    assert active == [True, False]
    assert record_active is True


async def test_dont_mid_session_ends_only_that_stream() -> None:
    async with proxy_server() as proxy:
        a = await proxy.connect({MCCP2_COMPRESS})
        b = await proxy.connect()
        proxy.queues[0].put_nowait("one\r\n")
        proxy.queues[1].put_nowait("one\r\n")
        await a.wait_for(lambda: b"one" in a.text)

        a.send(IAC + DONT + MCCP2_COMPRESS)
        await a.wait_for(lambda: a.stream_ends == 1)
        assert proxy.writers[0].mccp2_active is False
        proxy.queues[0].put_nowait("two plain\r\n")
        proxy.queues[1].put_nowait("two plain\r\n")
        await a.wait_for(lambda: b"two plain" in a.text)
        assert b"two plain" in bytes(a.raw)

        a.send(IAC + DO + MCCP2_COMPRESS)
        await a.wait_for(lambda: a.mccp2_starts == 2)
        proxy.queues[0].put_nowait("three\r\n")
        proxy.queues[1].put_nowait("three\r\n")
        await a.wait_for(lambda: b"three" in a.text)
        await b.wait_for(lambda: b"three" in b.text)
        a_raw = bytes(a.raw)
        b_text = bytes(b.text)
        b_starts = b.mccp2_starts
        a_active = proxy.writers[0].mccp2_active
        await a.close()
        await b.close()
    assert b"three" not in a_raw
    assert a_active is True
    assert b_starts == 0
    assert b"one\r\n" in b_text
    assert b"two plain\r\n" in b_text
    assert b"three\r\n" in b_text


# Client links: MCCP3 from the client (#329) ----------------------------------


def _stream(*chunks: bytes, finish: bool = False) -> bytes:
    """Compress ``chunks`` as one zlib stream, sync-flushed or finished."""
    c = zlib.compressobj()
    out = b"".join(c.compress(x) for x in chunks)
    return out + c.flush(zlib.Z_FINISH if finish else zlib.Z_SYNC_FLUSH)


async def _line(proxy: Any, index: int = 0) -> str:
    return await asyncio.wait_for(proxy.readers[index].readline(), TIMEOUT)


def _sb_mccp3_recorded(proxy: Any, index: int = 0) -> bool:
    link = proxy.writers[index].link_id
    return any(c == "SB" and "MCCP3" in o and d == "received" for d, c, o, _ in _seen(link))


async def test_client_mccp3_agreed_is_inflated_and_recorded() -> None:
    async with proxy_server() as proxy:
        client = await proxy.connect({MCCP3_COMPRESS})
        client.send(START3 + _stream(b"look\r\n"))
        got = await _line(proxy)
        recorded = _sb_mccp3_recorded(proxy)
        do_recorded = any(
            c == "DO" and "MCCP3" in o and d == "received"
            for d, c, o, _ in _seen(proxy.writers[0].link_id)
        )
        await client.close()
    assert got == "look\r\n"
    assert recorded
    assert do_recorded


@pytest.mark.parametrize(
    ("head", "tail"),
    [
        (START3[:-1], START3[-1:]),
        (START3[:-2], START3[-2:]),
    ],
)
async def test_client_mccp3_start_split_across_writes(head: bytes, tail: bytes) -> None:
    async with proxy_server() as proxy:
        client = await proxy.connect({MCCP3_COMPRESS})
        client.send(head)
        await asyncio.sleep(0.2)
        client.send(tail + _stream(b"look\r\n"))
        got = await _line(proxy)
        await client.close()
    assert got == "look\r\n"


@pytest.mark.parametrize("offset", [1, 3, 7])
async def test_client_mccp3_data_split_across_writes(offset: int) -> None:
    data = _stream(b"look north\r\n")
    async with proxy_server() as proxy:
        client = await proxy.connect({MCCP3_COMPRESS})
        client.send(START3 + data[:offset])
        await asyncio.sleep(0.2)
        client.send(data[offset:])
        got = await _line(proxy)
        await client.close()
    assert got == "look north\r\n"


@pytest.mark.parametrize("server_compression", [True, False])
async def test_client_mccp3_not_agreed_stays_plain(
    server_compression: bool, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="bastproxy.libs.net.negotiation")
    async with proxy_server(compression=server_compression) as proxy:
        client = await proxy.connect()
        client.send(START3 + b"look\r\n")
        got = await _line(proxy)
        writer = proxy.writers[0]
        active = writer.mccp3_active
        inflater = writer.protocol._mccp3_decompressor
        own = writer.protocol._mccp3_inflater
        recorded = _sb_mccp3_recorded(proxy)
        await client.close()
    assert got == "look\r\n"
    assert active is False
    assert inflater is None
    assert own is None
    assert recorded
    assert any("Dropped an SB MCCP3" in r.message for r in caplog.records)


async def test_client_mccp3_after_dont_stays_plain() -> None:
    async with proxy_server() as proxy:
        client = await proxy.connect({MCCP3_COMPRESS})
        client.send(IAC + DONT + MCCP3_COMPRESS)
        await asyncio.sleep(0.2)
        client.send(START3 + b"look\r\n")
        got = await _line(proxy)
        writer = proxy.writers[0]
        active = writer.mccp3_active
        inflater = writer.protocol._mccp3_decompressor
        await client.close()
    assert got == "look\r\n"
    assert active is False
    assert inflater is None


@pytest.mark.parametrize("same_write", [True, False])
async def test_client_mccp3_clean_end_continues_plain_and_restarts(same_write: bool) -> None:
    async with proxy_server() as proxy:
        client = await proxy.connect({MCCP3_COMPRESS})
        first = START3 + _stream(b"one\r\n", finish=True)
        if same_write:
            client.send(first + b"plain\r\n")
        else:
            client.send(first)
            await asyncio.sleep(0.2)
            client.send(b"plain\r\n")
        lines = [await _line(proxy), await _line(proxy)]
        client.send(START3 + _stream(b"again\r\n"))
        lines.append(await _line(proxy))
        await client.close()
    assert lines == ["one\r\n", "plain\r\n", "again\r\n"]


async def test_client_mccp3_broken_stream_closes_only_that_link(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.ERROR)
    async with proxy_server() as proxy:
        bad = await proxy.connect({MCCP3_COMPRESS})
        protocol = proxy.protocol_of(0)
        good = await proxy.connect({MCCP3_COMPRESS})
        bad.send(START3 + b"this is not a zlib stream\r\n")
        await bad.wait_for(lambda: proxy.writers[0].is_closing())
        rx_before = protocol.rx_bytes
        protocol.data_received(b"later\r\n")
        rx_after = protocol.rx_bytes
        good.send(START3 + _stream(b"fine\r\n"))
        got = await _line(proxy, 1)
        good_open = not proxy.writers[1].is_closing()
        await bad.close()
        await good.close()
    assert protocol.mccp3_failed is True
    assert rx_after == rx_before
    assert got == "fine\r\n"
    assert good_open
    assert any("MCCP3 decompression error" in r.message for r in caplog.records)


async def test_client_mccp3_chunk_over_the_bound_closes_the_link(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(server_module, "MCCP3_MAX_INFLATED_CHUNK", 1000)
    caplog.set_level(logging.ERROR)
    c = zlib.compressobj()
    async with proxy_server() as proxy:
        client = await proxy.connect({MCCP3_COMPRESS})
        protocol = proxy.protocol_of(0)
        client.send(START3 + c.compress(b"hello\r\n") + c.flush(zlib.Z_SYNC_FLUSH))
        first = await _line(proxy)
        client.send(c.compress(b"A" * 5000 + b"\r\n") + c.flush(zlib.Z_SYNC_FLUSH))
        await client.wait_for(lambda: proxy.writers[0].is_closing())
        rx_before = protocol.rx_bytes
        protocol.data_received(b"later\r\n")
        rx_after = protocol.rx_bytes
        await client.close()
    assert first == "hello\r\n"
    assert protocol.mccp3_failed is True
    assert rx_after == rx_before
    assert any("inflation limit" in r.message for r in caplog.records)


async def test_client_mccp3_chunk_under_the_bound_decodes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server_module, "MCCP3_MAX_INFLATED_CHUNK", 1000)
    body = "B" * 500 + "\r\n"
    async with proxy_server() as proxy:
        client = await proxy.connect({MCCP3_COMPRESS})
        client.send(START3 + _stream(body.encode()))
        got = await _line(proxy)
        await client.close()
    assert got == body

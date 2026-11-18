"""The proxy does not offer BINARY to clients (#573); utf8 comes from force_binary (#63)."""

import asyncio
from typing import Any

from telnetlib3.telopt import BINARY, DO, IAC, NAWS, SB, SE, TTYPE, WILL

from bastproxy.libs.net.server import create_server
from tests.libs.net.test_client_negotiation import _parse

TEXT = "na\u00efve r\u00e9sum\u00e9 \u2603"
IS = b"\x00"
SEND = b"\x01"


async def _exchange(client_sends: bytes) -> bytes:
    """Connect a raw client, send ``client_sends`` and return what the server wrote back.

    The client answers the TTYPE exchange: telnetlib3 calls ``begin_advanced_negotiation``
    only once it has finished.
    """
    done = asyncio.Event()

    async def shell(_reader: Any, writer: Any) -> None:
        await asyncio.sleep(0.3)
        writer.write(TEXT + "\r\n")
        await writer.drain()
        done.set()
        await asyncio.sleep(0.1)
        writer.close()

    srv = await create_server(
        host="127.0.0.1",
        port=0,
        shell=shell,
        encoding="utf8",
        compression=False,
        force_binary=True,
        encoding_errors="replace",
        connect_maxwait=0.3,
    )
    port = srv.sockets[0].getsockname()[1]
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    raw = b""
    try:
        if client_sends:
            writer.write(client_sends)
            await writer.drain()
        while True:
            try:
                chunk = await asyncio.wait_for(reader.read(4096), 1.0)
            except TimeoutError:
                break
            if not chunk:
                break
            raw += chunk
            reply = b""
            if IAC + DO + TTYPE in chunk:
                reply += IAC + WILL + TTYPE
            if IAC + SB + TTYPE + SEND in chunk:
                reply += IAC + SB + TTYPE + IS + b"xterm" + IAC + SE
            if reply:
                writer.write(reply)
                await writer.drain()
    finally:
        writer.close()
        srv.close()
        await srv.wait_closed()
    return raw


async def test_unasked_client_gets_no_binary_and_utf8_output() -> None:
    raw = await _exchange(b"")
    cmds, _subs, _ga = _parse(raw)
    assert (WILL, BINARY) not in cmds
    assert (DO, BINARY) not in cmds
    assert (DO, NAWS) in cmds
    assert TEXT.encode("utf8") in raw


async def test_client_do_binary_gets_will_binary() -> None:
    raw = await _exchange(IAC + DO + BINARY)
    cmds, _subs, _ga = _parse(raw)
    assert (WILL, BINARY) in cmds
    assert TEXT.encode("utf8") in raw


async def test_client_will_binary_gets_do_binary() -> None:
    raw = await _exchange(IAC + WILL + BINARY)
    cmds, _subs, _ga = _parse(raw)
    assert (DO, BINARY) in cmds
    assert TEXT.encode("utf8") in raw

"""Tests for the MTTS and MNES answers on the MUD link, over a real socket (#547)."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from telnetlib3 import open_connection
from telnetlib3.stream_writer import _decode_env_buf
from telnetlib3.telopt import DO, DONT, IAC, NEW_ENVIRON, TTYPE, WILL

import bastproxy
from bastproxy.libs.net import mtts
from bastproxy.libs.net.mud import MudTelnetClient
from bastproxy.libs.net.negotiation import parse_iac
from tests.libs.net.clients import ScriptedMud, sb_frame, scripted_mud

IS = b"\x00"
SEND = b"\x01"
VAR = b"\x00"
TTYPE_SEND = sb_frame(TTYPE, SEND)


def _ttype_answers(mud: ScriptedMud) -> list[str]:
    return [
        data[1:].decode()
        for cmd, opt, data, _raw in parse_iac(bytes(mud.received))
        if cmd == "SB" and opt == TTYPE
    ]


def _env_answers(mud: ScriptedMud) -> list[dict[str, str]]:
    return [
        _decode_env_buf(data[1:])
        for cmd, opt, data, _raw in parse_iac(bytes(mud.received))
        if cmd == "SB" and opt == NEW_ENVIRON
    ]


def _send_env(*names: str) -> bytes:
    return sb_frame(NEW_ENVIRON, SEND + b"".join(VAR + n.encode() for n in names))


@asynccontextmanager
async def link(
    script: Callable[[ScriptedMud, asyncio.StreamWriter], Awaitable[None]],
) -> AsyncIterator[tuple[ScriptedMud, Any]]:
    """Connect a ``MudTelnetClient`` to a scripted MUD."""
    async with scripted_mud(script) as mud:
        _reader, writer = await asyncio.wait_for(
            open_connection(
                "127.0.0.1",
                mud.port,
                client_factory=MudTelnetClient,
                compression=False,
                connect_maxwait=0.5,
                encoding="utf8",
                term=mtts.TERMINAL_TYPE,
            ),
            5,
        )
        try:
            yield mud, writer
        finally:
            writer.close()


async def test_ttype_cycle_over_a_socket() -> None:
    async def script(mud: ScriptedMud, writer: asyncio.StreamWriter) -> None:
        writer.write(IAC + DO + TTYPE)
        for i in range(4):
            writer.write(TTYPE_SEND)
            await writer.drain()
            await mud.wait_for(lambda i=i: len(_ttype_answers(mud)) > i)  # type: ignore[misc]
        await asyncio.sleep(5)

    async with link(script) as (mud, _w):
        await mud.wait_for(lambda: len(_ttype_answers(mud)) == 4)
        assert IAC + WILL + TTYPE in bytes(mud.received)
        assert _ttype_answers(mud) == ["BASTPROXY", "ANSI-256COLOR", "MTTS 525", "MTTS 525"]


async def test_dont_ttype_resets_the_cycle() -> None:
    async def script(mud: ScriptedMud, writer: asyncio.StreamWriter) -> None:
        writer.write(IAC + DO + TTYPE)
        for i in range(3):
            writer.write(TTYPE_SEND)
            await writer.drain()
            await mud.wait_for(lambda i=i: len(_ttype_answers(mud)) > i)  # type: ignore[misc]
        writer.write(IAC + DONT + TTYPE)
        writer.write(IAC + DO + TTYPE)
        writer.write(TTYPE_SEND)
        await writer.drain()
        await asyncio.sleep(5)

    async with link(script) as (mud, _w):
        await mud.wait_for(lambda: len(_ttype_answers(mud)) == 4)
        assert _ttype_answers(mud)[3] == "BASTPROXY"


async def test_a_new_connection_starts_the_cycle_again() -> None:
    async def script(mud: ScriptedMud, writer: asyncio.StreamWriter) -> None:
        writer.write(IAC + DO + TTYPE + TTYPE_SEND)
        await writer.drain()
        await asyncio.sleep(5)

    for _ in range(2):
        async with link(script) as (mud, _w):
            await mud.wait_for(lambda: len(_ttype_answers(mud)) == 1)
            assert _ttype_answers(mud) == ["BASTPROXY"]


async def _env_reply(*frames: bytes) -> list[dict[str, str]]:
    async def script(mud: ScriptedMud, writer: asyncio.StreamWriter) -> None:
        writer.write(IAC + DO + NEW_ENVIRON)
        for i, frame in enumerate(frames):
            writer.write(frame)
            await writer.drain()
            await mud.wait_for(lambda i=i: len(_env_answers(mud)) > i)  # type: ignore[misc]
        await asyncio.sleep(5)

    async with link(script) as (mud, _w):
        await mud.wait_for(lambda: len(_env_answers(mud)) == len(frames))
        assert IAC + WILL + NEW_ENVIRON in bytes(mud.received)
        return _env_answers(mud)


async def test_named_mnes_variables() -> None:
    [reply] = await _env_reply(_send_env("CLIENT_NAME", "CLIENT_VERSION"))
    assert reply == {"CLIENT_NAME": "BASTPROXY", "CLIENT_VERSION": bastproxy.__version__}


async def test_charset_and_mtts_variables() -> None:
    charset, both = await _env_reply(_send_env("CHARSET"), _send_env("MTTS", "TERMINAL_TYPE"))
    assert charset == {"CHARSET": "UTF-8"}
    assert both == {"MTTS": "525", "TERMINAL_TYPE": "ANSI-256COLOR"}


async def test_send_all_forms_give_every_mnes_variable() -> None:
    plain, empty_var = await _env_reply(
        sb_frame(NEW_ENVIRON, SEND), sb_frame(NEW_ENVIRON, SEND + VAR)
    )
    for reply in (plain, empty_var):
        assert mtts.mnes_variables().items() <= reply.items()
        assert "" not in reply


async def test_ipaddress_keeps_the_base_empty_answer() -> None:
    [reply] = await _env_reply(_send_env("IPADDRESS"))
    assert reply == {"IPADDRESS": ""}


async def test_send_env_mixes_base_and_mnes_keys() -> None:
    async def script(mud: ScriptedMud, writer: asyncio.StreamWriter) -> None:
        await asyncio.sleep(5)

    async with link(script) as (_mud, writer):
        protocol = writer.protocol
        assert isinstance(protocol, MudTelnetClient)
        env = protocol.send_env(["TERM", "CLIENT_NAME", ""])
        assert env == {"TERM": "ANSI-256COLOR", "CLIENT_NAME": "BASTPROXY"}

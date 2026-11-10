"""Tests for the client-side telnet negotiation (#66)."""

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest
from telnetlib3.telopt import (
    BINARY,
    DO,
    DONT,
    ECHO,
    GA,
    IAC,
    NAWS,
    NEW_ENVIRON,
    SB,
    SE,
    SGA,
    TTYPE,
    WILL,
    WONT,
)

from bastproxy.libs.net import client as client_mod
from bastproxy.libs.net.client import ClientConnection
from bastproxy.libs.net.server import CustomTelnetServer, create_server

IS = b"\x00"
SEND = b"\x01"
Cmd = tuple[bytes, bytes]


def _parse(data: bytes) -> tuple[list[Cmd], list[bytes], bool]:
    """Split raw bytes into (command, option) pairs, subnegotiations and GA seen."""
    cmds: list[Cmd] = []
    subs: list[bytes] = []
    got_ga = False
    i = 0
    while i < len(data):
        if data[i : i + 1] != IAC:
            i += 1
            continue
        verb = data[i + 1 : i + 2]
        if verb in (DO, DONT, WILL, WONT):
            cmds.append((verb, data[i + 2 : i + 3]))
            i += 3
        elif verb == SB:
            end = data.index(IAC + SE, i)
            subs.append(data[i + 2 : end])
            i = end + 2
        else:
            if verb == GA:
                got_ga = True
            i += 2
    return cmds, subs, got_ga


class _Result:
    def __init__(self) -> None:
        self.raw = b""
        self.before_login = b""
        self.cmds: list[Cmd] = []
        self.subs: list[bytes] = []
        self.got_ga = False
        self.server_rows_cols: tuple[Any, Any] = (None, None)
        self.protocol: Any = None


async def _run(ttype: bytes, *, naws: tuple[int, int] | None = None) -> _Result:
    """Connect a scripted client to a server configured like the listeners."""
    result = _Result()
    login = asyncio.Event()
    finish = asyncio.Event()
    done = asyncio.Event()

    async def shell(_reader: Any, writer: Any) -> None:
        # What client_telnet_handler / ClientConnection do around login.
        writer.iac(WILL, ECHO)
        await login.wait()
        writer.iac(WONT, ECHO)
        writer.send_ga()
        await writer.drain()
        await finish.wait()
        result.server_rows_cols = (writer.get_extra_info("rows"), writer.get_extra_info("cols"))
        result.protocol = writer.protocol
        done.set()
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
    ttype_sent = 0
    buf = b""

    def reply(cmds: list[Cmd], subs: list[bytes]) -> bytes:
        nonlocal ttype_sent
        out = b""
        for verb, opt in cmds:
            if verb == DO and opt == TTYPE:
                out += IAC + WILL + TTYPE
            elif verb == DO and opt == NAWS:
                out += IAC + WILL + NAWS
                if naws:
                    rows, cols = naws
                    out += IAC + SB + NAWS + cols.to_bytes(2, "big") + rows.to_bytes(2, "big")
                    out += IAC + SE
            elif verb == DO:
                out += IAC + WONT + opt
            elif verb == WILL and opt in (BINARY, ECHO):
                out += IAC + DO + opt
            elif verb == WILL:
                out += IAC + DONT + opt
        for sub in subs:
            if sub[:2] == TTYPE + SEND:
                ttype_sent += 1
                out += IAC + SB + TTYPE + IS + ttype + IAC + SE
        return out

    try:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 1.0
        # Run the negotiation, then log in, then read to the end.
        while loop.time() < deadline:
            try:
                chunk = await asyncio.wait_for(reader.read(4096), 0.1)
            except TimeoutError:
                continue
            if not chunk:
                break
            result.raw += chunk
            buf += chunk
            cmds, subs, _ = _parse(buf)
            buf = b""
            writer.write(reply(cmds, subs))
            await writer.drain()
        result.before_login = result.raw
        login.set()
        await asyncio.sleep(0.2)
        while True:
            try:
                chunk = await asyncio.wait_for(reader.read(4096), 0.1)
            except TimeoutError:
                break
            if not chunk:
                break
            result.raw += chunk
        finish.set()
        await asyncio.wait_for(done.wait(), 5)
    finally:
        writer.close()
        srv.close()
        await srv.wait_closed()
    result.cmds, result.subs, result.got_ga = _parse(result.raw)
    return result


@pytest.mark.parametrize("ttype", [b"xterm", b"Mudlet"])
async def test_echo_sent_once_each_way(ttype: bytes) -> None:
    result = await _run(ttype)
    before = _parse(result.before_login)[0]
    after = _parse(result.raw[len(result.before_login) :])[0]
    assert before.count((WILL, ECHO)) == 1
    assert (WONT, ECHO) not in before
    assert after.count((WONT, ECHO)) == 1
    assert result.cmds.count((WILL, ECHO)) == 1


@pytest.mark.parametrize("ttype", [b"xterm", b"Mudlet"])
async def test_connect_negotiation(ttype: bytes) -> None:
    result = await _run(ttype)
    assert (WILL, SGA) not in result.cmds
    assert (WILL, BINARY) in result.cmds
    assert (DO, NAWS) in result.cmds
    assert (DO, NEW_ENVIRON) in result.cmds
    assert result.got_ga


async def test_naws_reaches_extra_info() -> None:
    result = await _run(b"xterm", naws=(40, 100))
    assert result.server_rows_cols == (40, 100)


def test_client_connection_rows_cols() -> None:
    conn = object.__new__(ClientConnection)
    writer = MagicMock()
    writer.get_extra_info = {"rows": 40, "cols": 100}.get
    conn.writer = writer
    assert conn.rows == 40
    assert conn.cols == 100


async def test_naws_defaults_are_telnetlib3_defaults() -> None:
    result = await _run(b"xterm")
    assert result.server_rows_cols == (25, 80)


def test_server_override_does_not_call_super() -> None:
    server = object.__new__(CustomTelnetServer)
    server.writer = MagicMock()
    server.begin_advanced_negotiation()
    assert server.writer.iac.call_args_list == [
        ((DO, NAWS),),
        ((WILL, BINARY),),
    ]


def _login_client() -> tuple[ClientConnection, MagicMock, list[Any]]:
    conn = object.__new__(ClientConnection)
    conn.uuid = "u1"
    writer = MagicMock()
    conn.writer = writer
    conn.data_logger = MagicMock()
    conn.login_attempts = 0
    conn.api = lambda name: lambda *a, **k: "pw"  # type: ignore[assignment]
    return conn, writer, []


def test_login_sends_wont_echo_through_writer(monkeypatch: pytest.MonkeyPatch) -> None:
    conn, writer, sent = _login_client()
    order: list[str] = []
    writer.iac.side_effect = lambda *a: order.append("iac")

    class _Send:
        def __init__(self, data: Any, clients: list[str]) -> None:
            sent.append(data)

        def __call__(self) -> None:
            order.append("send")

    monkeypatch.setattr(client_mod, "SendDataDirectlyToClient", _Send)
    conn.process_data_from_not_logged_in_client("pw")
    assert writer.iac.call_args_list == [((WONT, ECHO),)]
    assert order == ["iac", "send"]
    assert len(sent) == 1


async def test_setup_client_sends_will_echo_through_writer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn, writer, _ = _login_client()

    async def drain() -> None:
        return None

    writer.drain = drain
    monkeypatch.setattr(client_mod, "SendDataDirectlyToClient", lambda *a, **k: lambda: None)
    await conn.setup_client()
    assert writer.iac.call_args_list == [((WILL, ECHO),)]

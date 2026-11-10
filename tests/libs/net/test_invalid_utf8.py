"""Tests that invalid utf8 from a client does not kill the connection (#305)."""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from telnetlib3 import server

from bastproxy.libs.net import listeners as listeners_mod
from bastproxy.libs.net.client import ClientConnection


def test_listeners_pass_encoding_errors_replace() -> None:
    settings = {
        "listenport": 9999,
        "ipv4": True,
        "ipv4address": "127.0.0.1",
        "ipv6": True,
        "ipv6address": "::1",
    }

    def api(name: str) -> Any:
        if name == "plugins.core.settings:setting.get":
            return lambda _plugin, key: settings[key]
        return MagicMock()

    obj = object.__new__(listeners_mod.Listeners)
    obj.api = api  # type: ignore[assignment]
    obj.ipv4_taskname = "v4"
    obj.ipv6_taskname = "v6"
    with patch.object(listeners_mod.server, "create_server", MagicMock()) as create:
        obj._create_listeners()
    assert create.call_count == 2
    for call in create.call_args_list:
        assert call.kwargs["encoding_errors"] == "replace"


async def test_invalid_utf8_is_replaced_end_to_end() -> None:
    lines: list[str] = []
    done = asyncio.Event()

    async def shell(reader: Any, writer: Any) -> None:
        lines.append(await reader.readline())
        lines.append(await reader.readline())
        done.set()
        writer.close()

    srv = await server.create_server(
        host="127.0.0.1",
        port=0,
        shell=shell,
        connect_maxwait=0.5,
        encoding="utf8",
        compression=False,
        force_binary=True,
        encoding_errors="replace",
    )
    assert srv.sockets
    port = srv.sockets[0].getsockname()[1]
    try:
        _reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"ab\xc3(\r\n")
        await writer.drain()
        await asyncio.sleep(0.1)
        writer.write(b"look\r\n")
        await writer.drain()
        await asyncio.wait_for(done.wait(), 5)
        writer.close()
    finally:
        srv.close()
        await srv.wait_closed()
    assert "�" in lines[0]
    assert lines[1].strip() == "look"


async def test_client_read_ends_on_unicode_decode_error() -> None:
    client = object.__new__(ClientConnection)
    client.uuid = "test-uuid"
    client.connected = True
    client.reader = MagicMock()
    client.reader.readline = AsyncMock(
        side_effect=UnicodeDecodeError("utf-8", b"\xc3", 0, 1, "unexpected end of data")
    )

    await client.client_read()

    assert client.connected is False
    client.reader.readline.assert_awaited_once()

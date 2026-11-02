"""Tests that the telnetlib3 calls force utf8 encoding (#63)."""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from telnetlib3 import open_connection, server

from bastproxy.libs.net import listeners as listeners_mod
from bastproxy.libs.net import mud as mud_mod
from bastproxy.libs.net.mud import MudConnection, MudTelnetClient


def test_listeners_pass_force_binary() -> None:
    settings = {
        "listenport": 9999,
        "ipv4": True,
        "ipv4address": "127.0.0.1",
        "ipv6": True,
        "ipv6address": "::1",
    }

    def api(name: str) -> Any:
        if name == "plugins.core.settings:get":
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
        assert call.kwargs["force_binary"] is True
        assert call.kwargs["encoding"] == "utf8"


async def test_mud_connect_passes_force_binary() -> None:
    conn = object.__new__(MudConnection)
    conn.addr = "127.0.0.1"
    conn.port = "4000"
    conn.term_type = "bastproxy"
    with patch.object(mud_mod, "open_connection", AsyncMock()) as opener:
        await conn.connect_to_mud()
    assert opener.call_args.kwargs["force_binary"] is True
    assert opener.call_args.kwargs["encoding"] == "utf8"


async def test_force_binary_yields_utf8_end_to_end() -> None:
    """With force_binary both ends report utf8 without BINARY negotiation."""
    seen: dict[str, str] = {}
    done = asyncio.Event()

    async def shell(reader: Any, writer: Any) -> None:
        seen["server"] = writer.protocol.encoding(outgoing=True, incoming=True)
        done.set()
        writer.close()

    srv = await server.create_server(
        host="127.0.0.1",
        port=0,
        shell=shell,
        encoding="utf8",
        force_binary=True,
        connect_maxwait=0.5,
        compression=False,
    )
    assert srv.sockets
    port = srv.sockets[0].getsockname()[1]
    try:
        _reader, writer = await open_connection(
            "127.0.0.1",
            port,
            client_factory=MudTelnetClient,
            encoding="utf8",
            force_binary=True,
            connect_maxwait=0.5,
            compression=False,
        )
        seen["client"] = writer.protocol.encoding(outgoing=True, incoming=True)
        await asyncio.wait_for(done.wait(), 5)
        writer.close()
    finally:
        srv.close()
        await srv.wait_closed()
    assert seen["client"].lower().replace("-", "") == "utf8"
    assert seen["server"].lower().replace("-", "") == "utf8"

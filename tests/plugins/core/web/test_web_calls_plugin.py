"""Command calls end to end over a real socket (#845)."""

import asyncio
import json
from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins.core.colors.plugin._colors import ColorsPlugin
from bastproxy.plugins.core.web.libs._call import Calls
from bastproxy.plugins.core.web.plugin._web import WebPlugin

from .test_web_plugin import stub as stub  # reason: reuse the fixture
from .test_web_routes_plugin import _login_sid, _open_socket


def _to_spans(text: str) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = ColorsPlugin._api_colorcode_to_spans(MagicMock(), text)
    return spans


async def _socket(stub: Any, reply: dict[str, Any]) -> Any:
    stub.command_calls.close()
    stub.command_calls = Calls(stub.server.sockets, lambda command, args: reply, _to_spans)
    await stub._restart(0)
    stub.settings["publicurl"] = f"http://127.0.0.1:{stub.port}"
    sid = await _login_sid(stub)
    conn = await _open_socket(stub, sid, f"http://127.0.0.1:{stub.port}")
    await conn.recv()  # hello
    return conn


async def _exchange(conn: Any, **fields: Any) -> dict[str, Any]:
    await conn.send(json.dumps({"v": 1, "type": "call", **fields}))
    async with asyncio.timeout(5):
        message: dict[str, Any] = json.loads(await conn.recv())
    return message


async def test_a_call_returns_colour_spans_and_data(stub: Any) -> None:
    reply = {"ok": True, "reason": "", "lines": ["@Rred@w plain"], "data": [1, 2]}
    conn = await _socket(stub, reply)
    result = await _exchange(conn, id="a1", command="core.web.status")
    assert (result["type"], result["id"], result["ok"]) == ("result", "a1", True)
    assert result["reply"]["data"] == [1, 2]
    (line,) = result["reply"]["lines"]
    assert line[0]["text"] == "red"
    assert line[0]["fg"] is not None
    assert line[-1]["text"] == " plain"
    await conn.close()


async def test_a_failed_call_carries_the_reason(stub: Any) -> None:
    reply = {"ok": False, "reason": "unknown_command", "lines": [], "data": None}
    conn = await _socket(stub, reply)
    result = await _exchange(conn, id=3, command="nope.nope.nope")
    assert (result["ok"], result["reason"], result["id"]) == (False, "unknown_command", 3)
    await conn.close()


async def test_close_unregisters_the_call_handler(stub: Any) -> None:
    assert "call" in stub.server.sockets.handlers
    WebPlugin._phook_close_server(stub)
    assert "call" not in stub.server.sockets.handlers

"""Tests for MudConnection writing, sending, setup and handler lifecycle (#310)."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from telnetlib3.telopt import GA, IAC

from bastproxy.libs.net import mud as mud_mod
from bastproxy.libs.net.mud import MudConnection
from bastproxy.libs.records import NetworkDataLine
from bastproxy.libs.records.enums import LineType

TIMEOUT = 5


async def until(cond: Callable[[], bool]) -> None:
    """Wait for ``cond`` to hold, failing the test after TIMEOUT seconds."""
    for _ in range(int(TIMEOUT / 0.01)):
        if cond():
            return
        await asyncio.sleep(0.01)
    pytest.fail("condition not reached in time")


Handler = Callable[[asyncio.StreamReader, asyncio.StreamWriter], Awaitable[None]]


@asynccontextmanager
async def raw_server(handler: Handler) -> AsyncIterator[int]:
    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        yield port
    finally:
        server.close()
        await server.wait_closed()


def _fake_writer() -> MagicMock:
    writer = MagicMock()
    writer.connection_closed = False
    writer.drain = AsyncMock()
    return writer


async def test_mud_write_io_empty_and_telnet_lines() -> None:
    conn = MudConnection("127.0.0.1", "4000")
    writer = _fake_writer()
    conn.writer = writer
    conn.connected = True
    io_line = NetworkDataLine("look\r\n")
    empty = NetworkDataLine("")
    cmd = NetworkDataLine(IAC + GA, line_type=LineType.COMMAND_TELNET)
    for line in (io_line, empty, cmd):
        conn.send_queue.put_nowait(line)

    task = asyncio.create_task(conn.mud_write())
    try:
        await until(lambda: cmd.was_sent)
    finally:
        conn.connected = False
        task.cancel()

    writer.write.assert_called_once_with("look\r\n")
    writer.send_iac.assert_called_once_with(IAC + GA)
    assert io_line.was_sent
    assert not empty.was_sent


async def test_mud_write_yields_after_max_lines() -> None:
    conn = MudConnection("127.0.0.1", "4000")
    conn.writer = _fake_writer()
    conn.connected = True
    conn.max_lines_to_process = 2
    lines = [NetworkDataLine(f"l{i}\r\n") for i in range(5)]
    for line in lines:
        conn.send_queue.put_nowait(line)
    task = asyncio.create_task(conn.mud_write())
    try:
        await until(lambda: lines[-1].was_sent)
    finally:
        conn.connected = False
        task.cancel()
    assert all(line.was_sent for line in lines)


async def test_mud_write_returns_when_not_connected() -> None:
    conn = MudConnection("127.0.0.1", "4000")
    await asyncio.wait_for(conn.mud_write(), TIMEOUT)


async def test_send_to_queues_only_when_connected_and_valid(
    caplog: pytest.LogCaptureFixture,
) -> None:
    conn = MudConnection("127.0.0.1", "4000")
    line = NetworkDataLine("x")
    conn.send_to(line)
    await asyncio.sleep(0)
    assert conn.send_queue.empty()

    conn.connected = True
    conn.send_to(line)
    conn.send_to("not a line")  # type: ignore[arg-type]
    await asyncio.sleep(0)
    assert conn.send_queue.qsize() == 1
    assert conn.send_queue.get_nowait() is line


def test_disconnect_from_mud_clears_flags() -> None:
    conn = MudConnection("127.0.0.1", "4000")
    conn.connected = True
    conn.connecting = True
    conn.disconnect_from_mud()
    assert conn.connected is False
    assert conn.connecting is False


async def test_setup_mud_drains_writer_only_when_present() -> None:
    conn = MudConnection("127.0.0.1", "4000")
    await conn.setup_mud()  # no writer: nothing to drain
    writer = _fake_writer()
    conn.writer = writer
    await conn.setup_mud()
    writer.drain.assert_awaited_once()


async def test_mud_telnet_handler_runs_until_mud_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Connect to a real server that sends a line and hangs up; the handler ends cleanly."""
    delivered: list[list[str]] = []
    notices: list[list[str]] = []

    class _ToClient:
        def __init__(self, data: Any) -> None:
            delivered.append([str(line.line) for line in data])

        def __call__(self) -> None:
            return None

    class _Send:
        def __init__(self, data: Any, *args: Any, **kwargs: Any) -> None:
            notices.append([str(getattr(line, "line", line)) for line in data])

        def __call__(self) -> None:
            return None

    monkeypatch.setattr(mud_mod, "ProcessDataToClient", _ToClient)
    monkeypatch.setattr(mud_mod, "SendDataDirectlyToClient", _Send)

    async def handler(_r: asyncio.StreamReader, w: asyncio.StreamWriter) -> None:
        w.write(b"hello from the mud\r\n")
        await w.drain()
        await asyncio.sleep(0.2)
        w.close()

    async with raw_server(handler) as port:
        conn = MudConnection("127.0.0.1", str(port))
        conn.api = lambda name: lambda *a, **k: 100  # type: ignore[assignment]
        await asyncio.wait_for(conn.connect_to_mud(), TIMEOUT)
        # connect_to_mud returns once the connection is open; the handler task keeps running
        await until(lambda: bool(notices))

    assert conn.connecting is False
    assert conn.connected is False
    assert notices == [["Connection to the mud has been closed."]]
    assert ["hello from the mud"] in delivered

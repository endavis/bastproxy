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
    conn.send_to("not a line")
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


def _recording_api(
    raised: list[tuple[str, dict[str, Any], bool]],
    conn_box: list[MudConnection],
    *,
    events_loaded: bool = True,
    raise_error: bool = False,
) -> Callable[[str], Callable[..., Any]]:
    """An api stand-in that records event raises along with ``connected`` at raise time."""

    def api(name: str) -> Callable[..., Any]:
        def call(*args: Any, **kwargs: Any) -> Any:
            if name == "libs.api:api.exists":
                return events_loaded
            if name == "plugins.core.events:event.raise":
                if raise_error:
                    raise RuntimeError("raise failed")
                raised.append((args[0], kwargs["event_args"], conn_box[0].connected))
                return None
            return 100

        return call

    return api


async def _connect_once(conn: MudConnection, hang_up_after: float = 0.1) -> None:
    async def handler(_r: asyncio.StreamReader, w: asyncio.StreamWriter) -> None:
        await asyncio.sleep(hang_up_after)
        w.close()

    # `connected` is True only while the link is up, and the whole connect, hang-up and
    # cleanup can finish between two polls (it did on Windows, #568). Wait instead for the
    # reader the handler sets on every connect, which the cleanup leaves in place.
    previous_reader = conn.reader
    async with raw_server(handler) as port:
        conn.port = str(port)
        await asyncio.wait_for(conn.connect_to_mud(), TIMEOUT)
        await until(lambda: conn.reader is not previous_reader)
        await until(lambda: not conn.connected)


@pytest.fixture
def quiet_client(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Noop:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def __call__(self) -> None:
            return None

    monkeypatch.setattr(mud_mod, "ProcessDataToClient", _Noop)
    monkeypatch.setattr(mud_mod, "SendDataDirectlyToClient", _Noop)


async def test_handler_raises_connect_event_on_every_connection(quiet_client: None) -> None:
    raised: list[tuple[str, dict[str, Any], bool]] = []
    conn_box: list[MudConnection] = []
    conn = MudConnection("127.0.0.1", "0")
    conn_box.append(conn)
    conn.api = _recording_api(raised, conn_box)  # type: ignore[assignment]

    await _connect_once(conn)
    await _connect_once(conn)

    assert [r for r in raised if r[0] == mud_mod.MUD_CONNECT_EVENT] == [
        (mud_mod.MUD_CONNECT_EVENT, {}, True),
        (mud_mod.MUD_CONNECT_EVENT, {}, True),
    ]


async def test_no_connect_event_without_the_events_plugin(quiet_client: None) -> None:
    raised: list[tuple[str, dict[str, Any], bool]] = []
    conn_box: list[MudConnection] = []
    conn = MudConnection("127.0.0.1", "0")
    conn_box.append(conn)
    conn.api = _recording_api(raised, conn_box, events_loaded=False)  # type: ignore[assignment]

    await _connect_once(conn)

    assert raised == []


async def test_failing_connect_event_is_logged_not_fatal(
    quiet_client: None, caplog: pytest.LogCaptureFixture
) -> None:
    raised: list[tuple[str, dict[str, Any], bool]] = []
    conn_box: list[MudConnection] = []
    conn = MudConnection("127.0.0.1", "0")
    conn_box.append(conn)
    conn.api = _recording_api(raised, conn_box, raise_error=True)  # type: ignore[assignment]

    with caplog.at_level("ERROR"):
        await _connect_once(conn)

    assert "Could not raise" in caplog.text
    assert conn.connected is False


async def test_send_to_from_the_connect_event_reaches_the_server(quiet_client: None) -> None:
    received: list[bytes] = []
    conn = MudConnection("127.0.0.1", "0")

    def api(name: str) -> Callable[..., Any]:
        def call(*args: Any, **kwargs: Any) -> Any:
            if name == "plugins.core.events:event.raise":
                conn.send_to(NetworkDataLine("hello server\r\n"))
            return True if name == "libs.api:api.exists" else 100

        return call

    conn.api = api  # type: ignore[assignment]

    async def handler(r: asyncio.StreamReader, w: asyncio.StreamWriter) -> None:
        received.append(await asyncio.wait_for(r.readuntil(b"\n"), TIMEOUT))
        w.close()

    async with raw_server(handler) as port:
        conn.port = str(port)
        await asyncio.wait_for(conn.connect_to_mud(), TIMEOUT)
        await until(lambda: bool(received))

    assert b"hello server" in received[0]


def _events_conn(**kwargs: Any) -> tuple[MudConnection, list[tuple[str, dict[str, Any], bool]]]:
    raised: list[tuple[str, dict[str, Any], bool]] = []
    conn_box: list[MudConnection] = []
    conn = MudConnection("127.0.0.1", "0")
    conn_box.append(conn)
    conn.api = _recording_api(raised, conn_box, **kwargs)  # type: ignore[assignment]
    return conn, raised


async def test_disconnect_event_raised_once_when_the_mud_hangs_up(quiet_client: None) -> None:
    conn, raised = _events_conn()

    await _connect_once(conn)
    await asyncio.sleep(0.05)

    assert raised == [
        (mud_mod.MUD_CONNECT_EVENT, {}, True),
        (mud_mod.MUD_DISCONNECT_EVENT, {}, False),
    ]


async def test_disconnect_event_raised_once_when_the_proxy_closes(quiet_client: None) -> None:
    conn, raised = _events_conn()

    async def handler(r: asyncio.StreamReader, w: asyncio.StreamWriter) -> None:
        await asyncio.wait_for(r.read(), 2 * TIMEOUT)
        w.close()

    async with raw_server(handler) as port:
        conn.port = str(port)
        await asyncio.wait_for(conn.connect_to_mud(), TIMEOUT)
        await until(lambda: conn.connected)
        conn.disconnect_from_mud()
        await asyncio.wait_for(
            until(lambda: any(r[0] == mud_mod.MUD_DISCONNECT_EVENT for r in raised)), TIMEOUT
        )
        await asyncio.sleep(0.1)

    assert [r[0] for r in raised].count(mud_mod.MUD_DISCONNECT_EVENT) == 1
    assert raised[-1][2] is False


async def test_disconnect_event_raised_once_when_a_task_fails(
    quiet_client: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn, raised = _events_conn()

    async def failing_read() -> None:
        raise RuntimeError("read failed")

    monkeypatch.setattr(conn, "mud_read", failing_read)

    async def handler(_r: asyncio.StreamReader, w: asyncio.StreamWriter) -> None:
        await asyncio.sleep(1)
        w.close()

    async with raw_server(handler) as port:
        conn.port = str(port)
        await asyncio.wait_for(conn.connect_to_mud(), TIMEOUT)
        await asyncio.wait_for(
            until(lambda: any(r[0] == mud_mod.MUD_DISCONNECT_EVENT for r in raised)), TIMEOUT
        )
        await asyncio.sleep(0.1)

    assert raised == [
        (mud_mod.MUD_CONNECT_EVENT, {}, True),
        (mud_mod.MUD_DISCONNECT_EVENT, {}, False),
    ]


async def test_disconnect_event_raised_once_when_setup_fails_and_tasks_end(
    quiet_client: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn, raised = _events_conn()

    async def failing_setup() -> None:
        raise RuntimeError("setup failed")

    monkeypatch.setattr(conn, "setup_mud", failing_setup)

    async def handler(_r: asyncio.StreamReader, w: asyncio.StreamWriter) -> None:
        await asyncio.sleep(0.3)
        w.close()

    async with raw_server(handler) as port:
        conn.port = str(port)
        await asyncio.wait_for(conn.connect_to_mud(), TIMEOUT)
        await until(lambda: any(r[0] == mud_mod.MUD_DISCONNECT_EVENT for r in raised))
        await until(
            lambda: (
                not [
                    t
                    for t in asyncio.all_tasks()
                    if t.get_name() in ("mud telnet read", "mud telnet write") and not t.done()
                ]
            )
        )

    assert [r[0] for r in raised].count(mud_mod.MUD_DISCONNECT_EVENT) == 1
    assert conn.connected is False
    assert raised[-1][2] is False


async def test_refused_connection_raises_no_events(quiet_client: None) -> None:
    conn, raised = _events_conn()
    server = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    server.close()
    await server.wait_closed()
    conn.port = str(port)

    await asyncio.wait_for(conn.connect_to_mud(), TIMEOUT)

    assert raised == []
    assert conn.connected is False


async def test_no_disconnect_event_without_the_events_plugin(quiet_client: None) -> None:
    conn, raised = _events_conn(events_loaded=False)

    await _connect_once(conn)

    assert raised == []


async def test_failing_disconnect_event_is_logged_not_fatal(
    quiet_client: None, caplog: pytest.LogCaptureFixture
) -> None:
    conn, _ = _events_conn(raise_error=True)

    with caplog.at_level("ERROR"):
        await _connect_once(conn)

    assert f"Could not raise {mud_mod.MUD_DISCONNECT_EVENT}" in caplog.text
    assert conn.connected is False


async def test_events_run_connect_disconnect_connect(quiet_client: None) -> None:
    conn, raised = _events_conn()

    await _connect_once(conn)
    await _connect_once(conn)
    await asyncio.sleep(0.05)

    assert [r[0] for r in raised] == [
        mud_mod.MUD_CONNECT_EVENT,
        mud_mod.MUD_DISCONNECT_EVENT,
        mud_mod.MUD_CONNECT_EVENT,
        mud_mod.MUD_DISCONNECT_EVENT,
    ]


def test_disconnect_from_mud_closes_an_open_writer() -> None:
    conn = MudConnection("127.0.0.1", "4000")
    writer = _fake_writer()
    conn.writer = writer
    conn.connected = True

    conn.disconnect_from_mud()

    writer.close.assert_called_once_with()
    assert conn.connected is False


def test_disconnect_from_mud_leaves_a_closed_writer_alone() -> None:
    conn = MudConnection("127.0.0.1", "4000")
    writer = _fake_writer()
    writer.connection_closed = True
    conn.writer = writer

    conn.disconnect_from_mud()

    writer.close.assert_not_called()

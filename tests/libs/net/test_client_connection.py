"""Tests for ClientConnection login, writing, registration and cleanup (#310)."""

import asyncio
from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from telnetlib3.telopt import ECHO, GA, IAC, WILL, WONT

from bastproxy.libs.net import client as client_mod
from bastproxy.libs.net.client import (
    ClientConnection,
    client_telnet_handler,
    register_client,
    unregister_client,
)
from bastproxy.libs.net.server import create_server
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


class FakeApi:
    """Records calls to API functions and returns canned values."""

    def __init__(self, values: dict[str, Any] | None = None) -> None:
        self.values = values or {}
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def __call__(self, name: str) -> Callable[..., Any]:
        def func(*args: Any, **_kwargs: Any) -> Any:
            self.calls.append((name, args))
            return self.values.get(name)

        return func

    def names(self) -> list[str]:
        return [name for name, _ in self.calls]


@pytest.fixture
def fake_api(monkeypatch: pytest.MonkeyPatch) -> FakeApi:
    api = FakeApi(
        {
            "plugins.core.proxy:ssc.proxypw.get": "secret",
            "plugins.core.proxy:ssc.proxypwview.get": "viewpw",
            "plugins.core.clients:client.is.banned": False,
        }
    )
    monkeypatch.setattr(client_mod, "API", lambda owner_id: api)
    return api


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Capture the text of everything sent through SendDataDirectlyToClient."""
    out: list[list[str]] = []

    class _Send:
        def __init__(self, data: Any, clients: list[str] | None = None) -> None:
            out.append([str(line.line) for line in data])

        def __call__(self) -> None:
            return None

    monkeypatch.setattr(client_mod, "SendDataDirectlyToClient", _Send)
    return out


def _writer() -> MagicMock:
    writer = MagicMock()
    writer.protocol = None
    writer.connection_closed = False
    writer.drain = AsyncMock()
    writer.get_extra_info.return_value = ("127.0.0.1", 5555)
    return writer


def _conn() -> tuple[ClientConnection, MagicMock]:
    writer = _writer()
    return ClientConnection("127.0.0.1", "5555", "telnet", MagicMock(), writer), writer


def test_login_with_main_password(fake_api: FakeApi, sent: list[list[str]]) -> None:
    conn, writer = _conn()
    conn.process_data_from_not_logged_in_client("secret\r\n")
    assert writer.iac.call_args_list == [((WONT, ECHO),)]
    assert sent == [["You are now logged in."]]
    assert "plugins.core.clients:client.logged.in.set" in fake_api.names()


def test_login_with_view_only_password(fake_api: FakeApi, sent: list[list[str]]) -> None:
    conn, writer = _conn()
    conn.process_data_from_not_logged_in_client("viewpw\r\n")
    assert writer.iac.call_args_list == [((WONT, ECHO),)]
    assert sent == [["You are now logged in as view only user."]]
    assert fake_api.names()[-1] == "plugins.core.clients:client.logged.in.set.view.only"


def test_wrong_password_counts_attempts_then_bans(fake_api: FakeApi, sent: list[list[str]]) -> None:
    conn, writer = _conn()
    conn.login_attempts = 1
    conn.process_data_from_not_logged_in_client("nope")
    conn.process_data_from_not_logged_in_client("nope")
    assert conn.login_attempts == 3
    assert sent == [["Invalid password. Please try again."]] * 2
    assert "plugins.core.clients:client.banned.add" not in fake_api.names()

    conn.process_data_from_not_logged_in_client("nope")
    assert sent[-1] == ["Too many login attempts. Goodbye."]
    assert fake_api.calls[-1] == ("plugins.core.clients:client.banned.add", (conn.uuid,))
    writer.iac.assert_not_called()


def test_view_only_client_cannot_enter_commands(fake_api: FakeApi, sent: list[list[str]]) -> None:
    conn, _ = _conn()
    conn.process_data_from_view_only_client("look\r\n")
    assert sent == [["As a view only user, you cannot enter commands"]]


async def test_client_write_io_prompt_and_telnet_command(fake_api: FakeApi) -> None:
    conn, writer = _conn()
    writer.send_ga.return_value = True
    io_line = NetworkDataLine("hello\r\n")
    empty = NetworkDataLine("")
    prompt = NetworkDataLine("prompt> ")
    prompt.is_prompt = True
    cmd = NetworkDataLine(IAC + GA, line_type=LineType.COMMAND_TELNET)
    for line in (io_line, empty, prompt, cmd):
        conn.send_queue.put_nowait(line)

    task = asyncio.create_task(conn.client_write())
    try:
        await until(lambda: cmd.was_sent)
    finally:
        conn.connected = False
        task.cancel()

    assert [c.args for c in writer.write.call_args_list] == [("hello\r\n",), ("prompt> ",)]
    writer.send_iac.assert_called_once_with(IAC + GA)
    writer.send_ga.assert_called_once_with()
    assert io_line.was_sent
    assert not empty.was_sent
    assert prompt.was_sent


async def test_client_write_stops_when_disconnected(fake_api: FakeApi) -> None:
    conn, _ = _conn()
    conn.connected = False
    await asyncio.wait_for(conn.client_write(), TIMEOUT)


async def test_send_to_queues_only_network_data_lines(
    fake_api: FakeApi, caplog: pytest.LogCaptureFixture
) -> None:
    conn, _ = _conn()
    good = NetworkDataLine("x")
    conn.send_to(good)
    conn.send_to("not a line")  # type: ignore[arg-type]
    await asyncio.sleep(0)
    assert conn.send_queue.qsize() == 1
    assert conn.send_queue.get_nowait() is good

    conn.connected = False
    conn.send_to(good)
    await asyncio.sleep(0)
    assert conn.send_queue.empty()


async def test_register_client_success_and_banned(fake_api: FakeApi) -> None:
    conn, writer = _conn()
    assert await register_client(conn) is True
    assert fake_api.calls[-1] == ("plugins.core.clients:client.add", (conn,))
    assert conn.connected

    fake_api.values["plugins.core.clients:client.is.banned"] = True
    assert await register_client(conn) is False
    assert conn.connected is False
    writer.write.assert_called_with("You are banned from this proxy. Goodbye.\r\n")


async def test_unregister_client_marks_disconnected_and_removes(fake_api: FakeApi) -> None:
    conn, _ = _conn()
    await unregister_client(conn)
    assert conn.connected is False
    assert fake_api.calls[-1] == ("plugins.core.clients:client.remove", (conn,))
    # a second call on an already disconnected client still removes it
    await unregister_client(conn)
    assert fake_api.names().count("plugins.core.clients:client.remove") == 2


async def test_client_telnet_handler_full_lifecycle(
    fake_api: FakeApi, sent: list[list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real client connects, logs in, receives data and disconnects."""
    connections: list[ClientConnection] = []
    base = FakeApi.__call__

    def tracking(self: FakeApi, name: str) -> Callable[..., Any]:
        func = base(self, name)
        if name == "plugins.core.clients:client.add":

            def add(conn: ClientConnection) -> None:
                connections.append(conn)
                func(conn)

            return add
        return func

    monkeypatch.setattr(FakeApi, "__call__", tracking)
    done = asyncio.Event()
    real_handler = client_telnet_handler

    async def shell(reader: Any, writer: Any) -> None:
        try:
            await real_handler(reader, writer)
        finally:
            done.set()

    srv = await create_server(
        host="127.0.0.1",
        port=0,
        shell=shell,
        encoding="utf8",
        compression=False,
        force_binary=True,
        encoding_errors="replace",
        connect_maxwait=0.2,
    )
    port = srv.sockets[0].getsockname()[1]
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        wait_for = until

        await wait_for(lambda: bool(connections) and bool(sent))
        assert sent[0] == ["Welcome to Bastproxy.", "Please enter your password."]
        conn = connections[0]
        assert conn.login_attempts == 1

        writer.write(b"secret\r\n")
        await writer.drain()
        await wait_for(lambda: "plugins.core.clients:client.logged.in.set" in fake_api.names())

        # logged in: a normal line is handed to ProcessDataToMud, a view-only one is refused
        conn.view_only = True
        conn.state["logged in"] = True
        writer.write(b"look\r\n")
        await writer.drain()
        await wait_for(lambda: ["As a view only user, you cannot enter commands"] in sent)

        # data and a telnet command queued for the client reach the wire
        conn.send_to(NetworkDataLine("hello client\r\n"))
        conn.send_to(NetworkDataLine(IAC + b"\xf1", line_type=LineType.COMMAND_TELNET))
        buf = b""
        async with asyncio.timeout(TIMEOUT):
            while b"hello client" not in buf or (IAC + b"\xf1") not in buf:
                buf += await reader.read(4096)
        assert IAC + WILL + ECHO in buf

        # the client hangs up: handler unregisters and the writer is closed
        writer.close()
        await asyncio.wait_for(done.wait(), TIMEOUT + 3)
        assert conn.connected is False
        assert fake_api.calls[-1][0] == "plugins.core.clients:client.remove"
    finally:
        writer.close()
        srv.close()
        await srv.wait_closed()


async def test_client_telnet_handler_banned_client_is_closed(
    fake_api: FakeApi, sent: list[list[str]]
) -> None:
    fake_api.values["plugins.core.clients:client.is.banned"] = True
    done = asyncio.Event()

    async def shell(reader: Any, writer: Any) -> None:
        try:
            await client_telnet_handler(reader, writer)
        finally:
            done.set()

    srv = await create_server(
        host="127.0.0.1",
        port=0,
        shell=shell,
        encoding="utf8",
        compression=False,
        force_binary=True,
        connect_maxwait=0.2,
    )
    port = srv.sockets[0].getsockname()[1]
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        data = b""
        async with asyncio.timeout(TIMEOUT):
            while b"banned" not in data:
                data += await reader.read(4096)
        await asyncio.wait_for(done.wait(), TIMEOUT + 3)
        assert "plugins.core.clients:client.add" not in fake_api.names()
        assert sent == []
    finally:
        writer.close()
        srv.close()
        await srv.wait_closed()

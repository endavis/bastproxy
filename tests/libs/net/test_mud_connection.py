"""Tests for the MUD-side telnetlib3 client behavior (#39)."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import pytest
from telnetlib3 import open_connection
from telnetlib3.telopt import CMD_EOR, DO, DONT, GA, GMCP, IAC, MCCP2_COMPRESS, WILL

from bastproxy.libs.net.mud import (
    MudConnection,
    MudLine,
    MudTelnetClient,
    MudTelnetReader,
)

Handler = Callable[[asyncio.StreamReader, asyncio.StreamWriter], Awaitable[None]]

TIMEOUT = 5


@asynccontextmanager
async def raw_server(handler: Handler) -> AsyncIterator[int]:
    """Run a raw TCP server on an ephemeral port and yield the port."""
    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        yield port
    finally:
        server.close()
        await server.wait_closed()


async def _connect(port: int) -> tuple:
    return await asyncio.wait_for(
        open_connection(
            "127.0.0.1",
            port,
            client_factory=MudTelnetClient,
            compression=False,
            connect_maxwait=0.5,
            encoding="utf8",
        ),
        TIMEOUT,
    )


@pytest.mark.parametrize(
    "separator",
    [b"\r\n", b"\n\r", b"\r\x00", b"\r", b"\n"],
)
async def test_patched_readline_splits_on_separator(separator: bytes) -> None:
    async def handler(_r: asyncio.StreamReader, w: asyncio.StreamWriter) -> None:
        w.write(b"one" + separator + b"two" + separator + b"three")
        await w.drain()
        w.close()

    async with raw_server(handler) as port:
        reader, writer = await _connect(port)
        lines = [await asyncio.wait_for(reader.readline(), TIMEOUT) for _ in range(3)]
        writer.close()

    expected_sep = "\r" if separator == b"\r\x00" else separator.decode()
    assert lines == ["one" + expected_sep, "two" + expected_sep, "three"]


async def _negotiate_and_collect(offer: bytes) -> bytes:
    """Offer an option to the client and return all bytes the server received."""
    received = bytearray()

    async def handler(r: asyncio.StreamReader, w: asyncio.StreamWriter) -> None:
        w.write(IAC + WILL + offer)
        await w.drain()
        try:
            while data := await asyncio.wait_for(r.read(4096), 1.0):
                received.extend(data)
        except TimeoutError:
            pass
        w.close()

    async with raw_server(handler) as port:
        _, writer = await _connect(port)
        await asyncio.sleep(1.2)
        writer.close()
    return bytes(received)


async def test_gmcp_is_declined() -> None:
    received = await _negotiate_and_collect(GMCP)
    assert IAC + DO + GMCP not in received
    assert b"Core.Hello" not in received
    assert IAC + DONT + GMCP in received


async def test_mccp2_is_refused() -> None:
    received = await _negotiate_and_collect(MCCP2_COMPRESS)
    assert IAC + DO + MCCP2_COMPRESS not in received
    assert IAC + DONT + MCCP2_COMPRESS in received


async def test_client_never_announces_gmcp() -> None:
    received = await _negotiate_and_collect(b"\x01")
    assert IAC + WILL + GMCP not in received


async def test_connect_to_mud_uses_parity_options(monkeypatch: pytest.MonkeyPatch) -> None:
    """connect_to_mud passes the MUD client factory and refuses MCCP."""
    from bastproxy.libs.net import mud

    calls: list[dict] = []

    async def fake_open_connection(*args: object, **kwargs: object) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(mud, "open_connection", fake_open_connection)
    await mud.MudConnection("127.0.0.1", "4000").connect_to_mud()

    assert len(calls) == 1
    assert calls[0]["client_factory"] is MudTelnetClient
    assert calls[0]["compression"] is False


def _make_recorder(calls: list[list[str]]) -> Callable[..., Callable[[], None]]:
    def factory(data: object) -> Callable[[], None]:
        def run() -> None:
            calls.append([str(line) for line in data])  # type: ignore[attr-defined]

        return run

    return factory


async def _run_mud_read(
    monkeypatch: pytest.MonkeyPatch, payload: bytes
) -> tuple[MudConnection, list[list[str]]]:
    from bastproxy.libs.net import mud

    calls: list[list[str]] = []
    monkeypatch.setattr(mud, "ProcessDataToClient", _make_recorder(calls))
    conn = MudConnection("127.0.0.1", "4000")
    reader = MudTelnetReader(fn_encoding=lambda **_kw: "utf8")
    if payload:
        reader.feed_data(payload)
    reader.feed_eof()
    conn.reader = reader
    conn.connected = True
    await asyncio.wait_for(conn.mud_read(), TIMEOUT)
    return conn, calls


@pytest.mark.asyncio
async def test_mud_read_processes_data_read_with_eof(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lines read in the same pass as EOF are delivered (#64)."""
    conn, calls = await _run_mud_read(monkeypatch, b"Goodbye!\r\nConnection closed.\r\n")
    assert conn.connected is False
    flat = [line for call in calls for line in call]
    assert len(flat) == 2
    assert "Goodbye!" in flat[0]
    assert "Connection closed." in flat[1]


@pytest.mark.asyncio
async def test_mud_read_eof_without_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """EOF with nothing read does not call ProcessDataToClient."""
    conn, calls = await _run_mud_read(monkeypatch, b"")
    assert conn.connected is False
    assert calls == []


# --- MudTelnetReader line splitting and prompt marks (#65) ---


def _reader(timeout: float = 5) -> MudTelnetReader:
    reader = MudTelnetReader(fn_encoding=lambda **_kw: "utf8")
    reader.line_timeout = timeout
    return reader


async def _read(reader: MudTelnetReader) -> MudLine:
    return await asyncio.wait_for(reader.read_mud_line(), TIMEOUT)


async def _step() -> None:
    """Let a pending read run up to its next wait."""
    for _ in range(3):
        await asyncio.sleep(0)


async def _drain(reader: MudTelnetReader) -> list[str]:
    """Read every line until EOF, returning the texts."""
    texts: list[str] = []
    while rec := await _read(reader):
        if not rec.text:
            break
        texts.append(rec.text)
    return texts


async def _lines_for(chunks: list[bytes]) -> list[str]:
    """Feed the chunks one at a time, with a read pending, and return the lines."""
    reader = _reader()
    texts: list[str] = []

    async def consume() -> None:
        texts.extend(await _drain(reader))

    task = asyncio.create_task(consume())
    for chunk in chunks:
        await _step()
        reader.feed_data(chunk)
    await _step()
    reader.feed_eof()
    await asyncio.wait_for(task, TIMEOUT)
    return texts


async def test_nr_ending_split_across_packets() -> None:
    reader = _reader()
    reader.feed_data(b"one\n")
    task = asyncio.create_task(reader.read_mud_line())
    await _step()
    assert not task.done()
    reader.feed_data(b"\rtwo\n\r")
    reader.feed_eof()
    first = await asyncio.wait_for(task, TIMEOUT)
    assert [first.text, (await _read(reader)).text] == ["one\n\r", "two\n\r"]


async def test_rn_ending_split_across_packets() -> None:
    assert await _lines_for([b"one\r", b"\ntwo\r\n"]) == ["one\r\n", "two\r\n"]


async def test_ambiguous_nrn_keeps_blank_line() -> None:
    assert await _lines_for([b"one\n\r\ntwo\n"]) == ["one\n\r", "\n", "two\n"]
    assert await _lines_for([b"one\n\r\n\rtwo"]) == ["one\n\r", "\n\r", "two"]


@pytest.mark.parametrize(
    "payload",
    [b"one\n\rtwo\n\r", b"one\r\ntwo\r\n", b"one\n\r\ntwo\n", b"a\rb\x00c\r\x00d"],
)
async def test_split_matches_unsplit_at_every_index(payload: bytes) -> None:
    whole = await _lines_for([payload])
    for i in range(1, len(payload)):
        assert await _lines_for([payload[:i], payload[i:]]) == whole, i


async def test_cr_nul_trimmed_to_cr() -> None:
    assert await _lines_for([b"a\r\x00b\r\x00"]) == ["a\r", "b\r"]


async def test_timeout_without_ending_gives_partial() -> None:
    reader = _reader(0.01)
    reader.feed_data(b"prompt> ")
    assert await _read(reader) == MudLine("prompt> ", False, False)


async def test_timeout_with_trailing_lone_newline_gives_line() -> None:
    reader = _reader(0.01)
    reader.feed_data(b"one\n")
    assert await _read(reader) == MudLine("one\n", True, False)


async def test_mid_line_split_within_timeout_is_one_line() -> None:
    assert await _lines_for([b"long li", b"ne\r\n"]) == ["long line\r\n"]


async def test_prompt_mark_without_ending() -> None:
    reader = _reader()
    reader.feed_data(b"HP> ")
    reader.mark_prompt(GA)
    assert reader.line_ready()
    assert await _read(reader) == MudLine("HP> ", False, True)


async def test_prompt_mark_after_ending_and_following_bytes() -> None:
    reader = _reader()
    reader.feed_data(b"HP>\n\r")
    reader.mark_prompt(GA)
    reader.feed_data(b"next\r\n")
    assert await _read(reader) == MudLine("HP>\n\r", True, True)
    assert await _read(reader) == MudLine("next\r\n", True, False)


async def test_prompt_mark_while_read_waits() -> None:
    reader = _reader()
    reader.feed_data(b"HP> ")
    task = asyncio.create_task(reader.read_mud_line())
    await _step()
    assert not task.done()
    reader.mark_prompt(CMD_EOR)
    assert await asyncio.wait_for(task, TIMEOUT) == MudLine("HP> ", False, True)


async def test_prompt_mark_on_empty_buffer_is_ignored() -> None:
    reader = _reader()
    reader.mark_prompt(GA)
    assert not reader.line_ready()


@pytest.mark.parametrize(("cmd", "text"), [(GA, "Name: "), (CMD_EOR, "Pass: ")])
async def test_ga_and_eor_mark_prompts_through_the_client(cmd: bytes, text: str) -> None:
    done = asyncio.Event()

    async def handler(_r: asyncio.StreamReader, w: asyncio.StreamWriter) -> None:
        w.write(text.encode() + IAC + cmd)
        await w.drain()
        await asyncio.wait_for(done.wait(), TIMEOUT)
        w.close()

    async with raw_server(handler) as port:
        reader, writer = await _connect(port)
        reader.line_timeout = 5
        assert await _read(reader) == MudLine(text, False, True)
        done.set()
        writer.close()


async def test_mud_read_marks_prompt_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    from bastproxy.libs.net import mud

    seen: list[tuple[str, bool, bool]] = []

    def factory(data: object) -> Callable[[], None]:
        def run() -> None:
            seen.extend((str(x), x.is_prompt, x.had_line_endings) for x in data)  # type: ignore[attr-defined]

        return run

    monkeypatch.setattr(mud, "ProcessDataToClient", factory)
    conn = MudConnection("127.0.0.1", "4000")
    conn.connected = True
    reader = _reader()
    reader.feed_data(b"line\r\nHP> ")
    reader.mark_prompt(GA)
    reader.feed_eof()
    conn.reader = reader
    await asyncio.wait_for(conn.mud_read(), TIMEOUT)
    assert seen == [("line", False, True), ("HP> ", True, False)]


async def test_mud_read_uses_only_the_reader_api(monkeypatch: pytest.MonkeyPatch) -> None:
    """mud_read needs read_mud_line, line_ready and at_eof, not the buffer."""
    from bastproxy.libs.net import mud

    calls: list[list[str]] = []
    monkeypatch.setattr(mud, "ProcessDataToClient", _make_recorder(calls))

    class _Double:
        def __init__(self) -> None:
            self.lines = [MudLine("a\r\n", True, False), MudLine("", False, False)]

        async def read_mud_line(self) -> MudLine:
            return self.lines.pop(0)

        def line_ready(self) -> bool:
            return True

        def at_eof(self) -> bool:
            return not self.lines

    conn = MudConnection("127.0.0.1", "4000")
    conn.connected = True
    conn.reader = _Double()  # type: ignore[assignment]
    await asyncio.wait_for(conn.mud_read(), TIMEOUT)
    assert [line for call in calls for line in call] == ["a"]


async def test_handler_applies_mudlinewait(monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import MagicMock

    from bastproxy.libs.net import mud

    conn = MudConnection("127.0.0.1", "4000")
    asked: list[tuple[str, str]] = []

    def setting_get(plugin_id: str, name: str) -> int:
        asked.append((plugin_id, name))
        return 250

    conn.api = MagicMock(return_value=setting_get)
    seen: list[float] = []

    class _Stop(Exception):
        pass

    async def fake_setup() -> None:
        assert conn.reader is not None
        seen.append(conn.reader.line_timeout)
        raise _Stop

    async def idle() -> None:
        await asyncio.Event().wait()

    tasks: list[asyncio.Task] = []

    class _Task:
        def __init__(self, coro: object, name: str) -> None:
            self.coro = coro

        def create(self) -> asyncio.Task:
            self.coro.close()  # type: ignore[attr-defined]
            task = asyncio.create_task(idle())
            tasks.append(task)
            return task

    monkeypatch.setattr(mud, "TaskItem", _Task)
    monkeypatch.setattr(conn, "setup_mud", fake_setup)
    writer = MagicMock()
    writer.get_extra_info.return_value = ("127.0.0.1", 4000)
    reader = _reader()

    with pytest.raises(_Stop):
        await asyncio.wait_for(conn.mud_telnet_handler(reader, writer), TIMEOUT)
    for task in tasks:
        task.cancel()

    assert seen == [0.25]
    assert asked == [("plugins.core.proxy", "mudlinewait")]


def test_reader_wiring_and_protected_names_exist() -> None:
    """Canary: the telnetlib3 names MudTelnetReader builds on are still there."""
    from telnetlib3 import TelnetReaderUnicode

    assert MudTelnetClient._reader_factory_encoding is MudTelnetReader
    fresh = TelnetReaderUnicode(fn_encoding=lambda **_kw: "utf8")
    for name in ("_buffer", "_eof", "_wait_for_data", "_maybe_resume_transport", "_wakeup_waiter"):
        assert hasattr(fresh, name), name


def test_new_connection_is_not_connected() -> None:
    assert MudConnection("127.0.0.1", "4000").connected is False


async def test_failed_connect_reports_and_stays_disconnected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A refused connect does not raise, tells the client and leaves connected False (#306)."""
    import socket

    from bastproxy.libs.net import mud

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    # the port is closed again, so the connect is refused

    sent: list[object] = []

    class _Recorder:
        def __init__(self, data: object) -> None:
            sent.append(data)

        def __call__(self) -> None:
            return None

    monkeypatch.setattr(mud, "SendDataDirectlyToClient", _Recorder)

    conn = MudConnection("127.0.0.1", str(port))
    await asyncio.wait_for(conn.connect_to_mud(), TIMEOUT)

    # the proxy's connect command only checks `connected`, so a new attempt can proceed
    assert conn.connected is False
    assert len(sent) == 1
    text = " ".join(str(line) for line in sent[0])  # type: ignore[attr-defined]
    assert "Could not connect to the mud" in text
    assert f"127.0.0.1:{port}" in text


async def test_handler_sets_connected(monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import MagicMock

    from bastproxy.libs.net import mud

    conn = MudConnection("127.0.0.1", "4000")
    conn.api = MagicMock(return_value=lambda *_a: 250)
    assert conn.connected is False
    before = conn.connected_time
    seen: list[bool] = []

    class _Stop(Exception):
        pass

    async def fake_setup() -> None:
        seen.append(conn.connected)
        raise _Stop

    async def idle() -> None:
        await asyncio.Event().wait()

    tasks: list[asyncio.Task] = []

    class _Task:
        def __init__(self, coro: object, name: str) -> None:
            self.coro = coro

        def create(self) -> asyncio.Task:
            # the real read/write loops run while connected, so it must be set by now
            seen.append(conn.connected)
            self.coro.close()  # type: ignore[attr-defined]
            task = asyncio.create_task(idle())
            tasks.append(task)
            return task

    monkeypatch.setattr(mud, "TaskItem", _Task)
    monkeypatch.setattr(conn, "setup_mud", fake_setup)
    writer = MagicMock()
    writer.get_extra_info.return_value = ("127.0.0.1", 4000)

    with pytest.raises(_Stop):
        await asyncio.wait_for(conn.mud_telnet_handler(_reader(), writer), TIMEOUT)
    for task in tasks:
        task.cancel()

    assert seen == [True, True, True]
    assert conn.connected_time >= before

"""Tests for the echo-off placeholder in MudConnection.mud_write (#342)."""

import asyncio
import logging
from types import SimpleNamespace

import pytest
from telnetlib3.telopt import ECHO

from bastproxy.libs.net.mud import MudConnection

MUD_LOGGER = "bastproxy.libs.net.mud"
LINE = "typed line\r\n"


class FakeRemoteOption:
    """Remote option state with a switchable ECHO flag."""

    def __init__(self) -> None:
        self.echo = False

    def enabled(self, opt: bytes) -> bool:
        return self.echo and opt == ECHO


class FakeWriter:
    """Writer that stops the connection after the expected number of writes."""

    connection_closed = False

    def __init__(self, conn: MudConnection, remote: FakeRemoteOption, stop_after: int) -> None:
        self.conn = conn
        self.remote_option = remote
        self.sent: list[str] = []
        self.stop_after = stop_after

    def write(self, line: str) -> None:
        self.sent.append(line)
        if len(self.sent) >= self.stop_after:
            self.conn.connected = False


async def _run(
    caplog: pytest.LogCaptureFixture, lines: list[str], echo_by_line: list[bool]
) -> FakeWriter:
    conn = MudConnection("127.0.0.1", "4000")
    remote = FakeRemoteOption()
    writer = FakeWriter(conn, remote, len(lines))
    conn.writer = writer  # type: ignore[assignment]
    conn.connected = True
    for line in lines:
        conn.send_queue.put_nowait(
            SimpleNamespace(
                is_io=True, is_command_telnet=False, line=line, was_sent=False, mask_log=False
            )  # type: ignore[arg-type]
        )
    original = writer.write

    # Set state for the first line before the loop starts; later lines switch on write.
    remote.echo = echo_by_line[0]
    switch = iter(echo_by_line[1:])

    def write_then_switch(line: str) -> None:
        original(line)
        remote.echo = next(switch, remote.echo)

    writer.write = write_then_switch  # type: ignore[method-assign]
    with (
        caplog.at_level(logging.DEBUG, logger=MUD_LOGGER),
        caplog.at_level(logging.DEBUG, logger="data.mud"),
    ):
        await asyncio.wait_for(conn.mud_write(), 5)
    return writer


async def test_echo_on_logs_placeholder_only(caplog: pytest.LogCaptureFixture) -> None:
    """With echo on, no record carries the line text; a length placeholder is logged."""
    writer = await _run(caplog, [LINE], [True])

    assert writer.sent == [LINE]
    assert "typed line" not in caplog.text
    data = [r.getMessage() for r in caplog.records if r.name == "data.mud"]
    assert data == [f"{'to_mud':<12} : <input while echo is off, {len(LINE) - 2} chars>"]
    assert "Writing message to mud: <input while echo is off, 10 chars>" in caplog.text


async def test_echo_off_logs_line(caplog: pytest.LogCaptureFixture) -> None:
    """With echo off, the line is logged as before."""
    await _run(caplog, [LINE], [False])

    data = [r.getMessage() for r in caplog.records if r.name == "data.mud"]
    assert data == [f"{'to_mud':<12} : {LINE}"]
    assert "Writing message to mud: typed line" in caplog.text


async def test_echo_state_change_on_to_off(caplog: pytest.LogCaptureFixture) -> None:
    """The first line is masked and the next, after echo goes off, is logged."""
    await _run(caplog, ["first one\r\n", "second\r\n"], [True, False])

    data = [r.getMessage() for r in caplog.records if r.name == "data.mud"]
    assert "first one" not in caplog.text
    assert data[0].endswith("<input while echo is off, 9 chars>")
    assert data[1].endswith("second\r\n")


async def test_masked_line_stays_masked_after_echo_goes_off(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A line read from the client while echo was off stays masked when written."""
    conn = MudConnection("127.0.0.1", "4000")
    remote = FakeRemoteOption()
    writer = FakeWriter(conn, remote, 1)
    conn.writer = writer  # type: ignore[assignment]
    conn.connected = True
    conn.send_queue.put_nowait(
        SimpleNamespace(
            is_io=True, is_command_telnet=False, line="kept\r\n", was_sent=False, mask_log=True
        )  # type: ignore[arg-type]
    )
    with caplog.at_level(logging.DEBUG, logger="data.mud"):
        await asyncio.wait_for(conn.mud_write(), 5)
    assert "kept" not in caplog.text
    assert writer.sent == ["kept\r\n"]

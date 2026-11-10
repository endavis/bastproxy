"""Tests for the data.mud log label in MudConnection.mud_write (#309)."""

import asyncio
import logging
from types import SimpleNamespace

import pytest

from bastproxy.libs.net.mud import MudConnection


async def test_mud_write_logs_telnet_command_as_to_mud(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A telnet command sent to the MUD is logged to data.mud as to_mud."""
    conn = MudConnection("127.0.0.1", "4000")
    sent: list[bytes] = []

    class FakeWriter:
        connection_closed = False

        def send_iac(self, line: bytes) -> None:
            sent.append(line)
            conn.connected = False

    msg = SimpleNamespace(is_io=False, is_command_telnet=True, line=b"\xff\xf9", was_sent=False)
    conn.writer = FakeWriter()  # type: ignore[assignment]
    conn.connected = True
    conn.send_queue.put_nowait(msg)  # type: ignore[arg-type]
    with caplog.at_level(logging.INFO, logger="data.mud"):
        await asyncio.wait_for(conn.mud_write(), 5)

    assert sent == [b"\xff\xf9"]
    labels = [r.getMessage().split(" :")[0].strip() for r in caplog.records if r.name == "data.mud"]
    assert labels == ["to_mud"]

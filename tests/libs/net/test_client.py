"""Tests for ClientConnection.client_read connection-error handling (#68)."""

import asyncio
import contextlib
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from bastproxy.libs.net.client import ClientConnection
from bastproxy.libs.records import NetworkDataLine


def _make_client(readline: AsyncMock) -> ClientConnection:
    """Build a ClientConnection without running __init__ (needs a live API)."""
    client = object.__new__(ClientConnection)
    client.uuid = "test-uuid"
    client.connected = True
    client.reader = MagicMock()
    client.reader.readline = readline
    return client


@pytest.mark.parametrize("exc", [BrokenPipeError, ConnectionResetError])
async def test_client_read_ends_on_connection_error(exc: type[ConnectionError]) -> None:
    readline = AsyncMock(side_effect=exc("boom"))
    client = _make_client(readline)

    await client.client_read()

    assert client.connected is False
    readline.assert_awaited_once()


async def test_client_read_keeps_leading_and_trailing_spaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the line terminator is removed before the line goes to the MUD (#52)."""
    from bastproxy.libs.net import client as client_module

    readline = AsyncMock(side_effect=["  look  \r\n", ""])
    client = _make_client(readline)
    client.state = {"logged in": True}
    client.view_only = False
    client.max_lines_to_process = 100
    client.data_logger = MagicMock()
    # no MUD connection, so echo is not off (the client was built without __init__, so no API)
    client.api = MagicMock(return_value=lambda: None)
    sent: list[str] = []

    class _FakeProcess:
        def __init__(self, data: object, client_id: str) -> None:
            sent.append(data.get_first_line())  # type: ignore[attr-defined]

        def __call__(self) -> None:
            return None

    monkeypatch.setattr(client_module, "ProcessDataToMud", _FakeProcess)

    await client.client_read()

    assert sent == ["  look  "]


async def test_register_client_ban_message_ends_with_crlf() -> None:
    """The ban message sent to a banned client ends in CRLF (#69)."""
    from bastproxy.libs.net.client import register_client

    connection = MagicMock()
    connection.addr = "1.2.3.4"
    connection.port = 1234
    connection.uuid = "test-uuid"
    connection.api.return_value = MagicMock(return_value=True)
    connection.writer.drain = AsyncMock()

    assert await register_client(connection) is False

    connection.writer.write.assert_called_once_with("You are banned from this proxy. Goodbye.\r\n")


def _client_for_write(send_ga_result: bool, lines: list) -> tuple[ClientConnection, MagicMock]:
    client = _make_client(AsyncMock())
    client.writer = MagicMock()
    client.writer.connection_closed = False
    client.writer.send_ga.return_value = send_ga_result
    client.data_logger = MagicMock()
    client.max_lines_to_process = 100
    client.send_queue = asyncio.Queue()
    for line in lines:
        client.send_queue.put_nowait(line)
    return client, client.writer


async def _run_write(client: ClientConnection) -> None:
    """Run client_write until it has taken every queued line, then cancel it."""
    task = asyncio.create_task(client.client_write())
    for _ in range(20):
        await asyncio.sleep(0)
    assert client.send_queue.empty()
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await asyncio.wait_for(task, 5)


def _prompt_line(prompt: bool) -> NetworkDataLine:
    line = NetworkDataLine("HP> ", originated="mud", had_line_endings=False)
    line.is_prompt = prompt
    return line


async def test_client_write_prompt_sends_ga_through_send_ga() -> None:
    client, writer = _client_for_write(True, [_prompt_line(True)])
    await _run_write(client)
    writer.send_ga.assert_called_once_with()
    assert all(isinstance(c.args[0], str) for c in writer.write.call_args_list)
    logged = [c.args for c in cast(MagicMock, client.data_logger).info.call_args_list]
    assert any(b"\xff\xf9" in args for args in logged)


async def test_client_write_non_prompt_does_not_send_ga() -> None:
    client, writer = _client_for_write(True, [_prompt_line(False)])
    await _run_write(client)
    writer.send_ga.assert_not_called()


async def test_client_write_prompt_when_ga_suppressed() -> None:
    client, writer = _client_for_write(False, [_prompt_line(True)])
    await _run_write(client)
    writer.send_ga.assert_called_once_with()
    writer.write.assert_any_call("HP> ")
    logged = [c.args for c in cast(MagicMock, client.data_logger).info.call_args_list]
    assert not any(b"\xff\xf9" in args for args in logged)


def _logged(client: ClientConnection) -> list[tuple[object, ...]]:
    return [c.args for c in cast(MagicMock, client.data_logger).info.call_args_list]


async def test_client_write_prompt_sends_eor_when_agreed() -> None:
    client, writer = _client_for_write(True, [_prompt_line(True)])
    writer.send_eor.return_value = True
    await _run_write(client)
    writer.send_eor.assert_called_once_with()
    writer.send_ga.assert_not_called()
    writer.write.assert_any_call("HP> ")
    logged = _logged(client)
    assert any(b"\xff\xef" in args for args in logged)
    assert not any(b"\xff\xf9" in args for args in logged)


async def test_client_write_prompt_falls_back_to_ga_without_eor() -> None:
    client, writer = _client_for_write(True, [_prompt_line(True)])
    writer.send_eor.return_value = False
    await _run_write(client)
    writer.send_eor.assert_called_once_with()
    writer.send_ga.assert_called_once_with()
    logged = _logged(client)
    assert any(b"\xff\xf9" in args for args in logged)
    assert not any(b"\xff\xef" in args for args in logged)


async def test_client_write_prompt_without_eor_or_ga_logs_no_signal() -> None:
    client, writer = _client_for_write(False, [_prompt_line(True)])
    writer.send_eor.return_value = False
    await _run_write(client)
    writer.write.assert_any_call("HP> ")
    logged = _logged(client)
    assert not any(b"\xff\xef" in args or b"\xff\xf9" in args for args in logged)


async def test_client_write_non_prompt_sends_neither_signal() -> None:
    client, writer = _client_for_write(True, [_prompt_line(False)])
    writer.send_eor.return_value = True
    await _run_write(client)
    writer.send_eor.assert_not_called()
    writer.send_ga.assert_not_called()


async def test_client_write_eor_and_sga_agreed_sends_eor_only() -> None:
    client, writer = _client_for_write(False, [_prompt_line(True)])
    writer.send_eor.return_value = True
    await _run_write(client)
    writer.send_ga.assert_not_called()
    assert any(b"\xff\xef" in args for args in _logged(client))


@pytest.mark.parametrize(("view_only", "expected"), [(False, 1), (True, 0)])
async def test_client_read_reports_input_to_the_window_size_forwarder(
    monkeypatch: pytest.MonkeyPatch, view_only: bool, expected: int
) -> None:
    """Only a full-login client's input makes it the active client (#308)."""
    from bastproxy.libs.net import client as client_module

    client = _make_client(AsyncMock(side_effect=["look\r\n", ""]))
    client.state = {"logged in": True}
    client.view_only = view_only
    client.max_lines_to_process = 100
    client.data_logger = MagicMock()
    client.api = MagicMock(return_value=lambda: None)
    forwarder = MagicMock()
    monkeypatch.setattr(client_module, "WINDOW_SIZE", forwarder)
    monkeypatch.setattr(client_module, "ProcessDataToMud", lambda *_a, **_k: lambda: None)
    monkeypatch.setattr(client, "process_data_from_view_only_client", lambda _inp: None)

    await client.client_read()

    assert forwarder.client_input.call_count == expected


async def test_unregister_client_tells_the_window_size_forwarder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bastproxy.libs.net import client as client_module

    forwarder = MagicMock()
    monkeypatch.setattr(client_module, "WINDOW_SIZE", forwarder)
    monkeypatch.setattr(client_module, "PROTOCOLS", MagicMock())
    connection = MagicMock()

    await client_module.unregister_client(connection)

    forwarder.client_gone.assert_called_once_with(connection)

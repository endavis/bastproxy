"""Tests for ClientConnection.client_read connection-error handling (#68)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from bastproxy.libs.net.client import ClientConnection


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

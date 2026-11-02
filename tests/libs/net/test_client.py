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

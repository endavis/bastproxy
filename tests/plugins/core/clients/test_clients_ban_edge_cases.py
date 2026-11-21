"""Tests for ban API edge cases (#642)."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from bastproxy.plugins.core.clients.plugin import _clients
from bastproxy.plugins.core.clients.plugin._clients import ClientPlugin


def _stub(clients: dict[str, Any]) -> MagicMock:
    stub = MagicMock()
    stub.plugin_id = "plugins.core.clients"
    stub.clients = clients
    stub.banned = {}
    return stub


def test_banned_add_unknown_client_returns_false() -> None:
    stub = _stub({})
    assert ClientPlugin._api_client_banned_add(stub, "nope") is False
    stub.api.assert_not_called()


def test_banned_add_known_client_bans_its_address() -> None:
    client = SimpleNamespace(connected=True, addr="192.0.2.1")
    stub = _stub({"abc": client})
    by_ip = MagicMock(return_value=True)
    stub.api.return_value = by_ip
    assert ClientPlugin._api_client_banned_add(stub, "abc", 30) is True
    assert client.connected is False
    by_ip.assert_called_once_with("192.0.2.1", 30)


@pytest.mark.parametrize("how_long", [0, -2, -100])
def test_banned_add_by_ip_refuses_invalid_duration(how_long: int) -> None:
    stub = _stub({})
    with patch.object(_clients, "BanRecord") as record:
        assert ClientPlugin._api_client_banned_add_by_ip(stub, "192.0.2.1", how_long) is False
    record.assert_not_called()
    assert stub.banned == {}
    stub.api.assert_not_called()


def test_banned_add_by_ip_accepts_positive_duration() -> None:
    stub = _stub({})
    with patch.object(_clients, "BanRecord", return_value="rec") as record:
        assert ClientPlugin._api_client_banned_add_by_ip(stub, "192.0.2.1", 5) is True
    record.assert_called_once()
    assert stub.banned == {"192.0.2.1": "rec"}

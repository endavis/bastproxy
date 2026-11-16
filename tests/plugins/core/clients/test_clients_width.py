"""Tests for the client.width.get API of the clients plugin (#421)."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins.core.clients.plugin._clients import ClientPlugin


class _BrokenClient:
    naws_reported = True

    @property
    def cols(self) -> int:
        raise OSError("link closed")


def _stub(clients: dict[str, Any]) -> MagicMock:
    stub = MagicMock()
    stub.plugin_id = "plugins.core.clients"
    stub.clients = clients
    return stub


def _width(clients: dict[str, Any], uuid: str = "a") -> int | None:
    result: int | None = ClientPlugin._api_client_width_get(_stub(clients), uuid)
    return result


def test_unknown_uuid_is_none() -> None:
    assert _width({}) is None


def test_not_reported_is_none() -> None:
    assert _width({"a": SimpleNamespace(naws_reported=False, cols=120)}) is None


def test_zero_cols_is_none() -> None:
    assert _width({"a": SimpleNamespace(naws_reported=True, cols=0)}) is None


def test_raising_cols_is_none() -> None:
    assert _width({"a": _BrokenClient()}) is None


def test_reported_width_is_returned() -> None:
    assert _width({"a": SimpleNamespace(naws_reported=True, cols=120)}) == 120

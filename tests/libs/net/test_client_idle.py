"""Tests for ClientConnection.idle (#90)."""

from types import SimpleNamespace
from typing import Any

from bastproxy.libs.net.client import ClientConnection


def _client(telnet_server: Any, calls: list[tuple[Any, Any]]) -> ClientConnection:
    conn = object.__new__(ClientConnection)
    conn.telnet_server = telnet_server

    def to_string(start: Any, end: Any) -> str:
        calls.append((start, end))
        return "formatted"

    conn.api = lambda name: to_string  # type: ignore[assignment]
    return conn


def test_idle_formats_telnet_server_idle() -> None:
    calls: list[tuple[Any, Any]] = []
    client = _client(SimpleNamespace(idle=42.5), calls)

    assert client.idle == "formatted"
    start, end = calls[0]
    assert (end - start).total_seconds() == 42.5


def test_idle_dash_without_telnet_server() -> None:
    calls: list[tuple[Any, Any]] = []

    assert _client(None, calls).idle == "-"
    assert calls == []

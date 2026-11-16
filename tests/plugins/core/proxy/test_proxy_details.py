"""Tests for the proxy details command and the options rows of info (#422)."""

import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins.core.proxy.plugin._proxy import ProxyPlugin

CLIENT_LINES = ["Client block", "row"]


def _mud(**kwargs: Any) -> SimpleNamespace:
    values: dict[str, Any] = {
        "connected": True,
        "connecting": False,
        "addr": "mud.example",
        "port": "4000",
        "connected_time": datetime.datetime(2026, 1, 2, 3, 4, 5, tzinfo=datetime.UTC),
        "idle": "3s",
        "lines_sent": 4,
        "lines_received": 2000,
        "bytes_sent": 10,
        "bytes_received": 99999,
        "telnet_options": lambda: (["TTYPE"], ["GMCP", "MCCP2_COMPRESS"]),
    }
    values.update(kwargs)
    return SimpleNamespace(**values)


def _stub(mud: SimpleNamespace | None) -> MagicMock:
    stub = MagicMock()
    stub.mud_connection = mud
    stub.api.proxy_start_time = None
    stub.api.time_format = "%Y-%m-%d"

    def api(name: str) -> Any:
        if name == "plugins.core.commands:output.header.format":
            return lambda title: [f"== {title} =="]
        if name == "plugins.core.clients:client.list.details":
            return lambda: list(CLIENT_LINES)
        if name == "plugins.core.clients:client.list.formatted":
            return lambda: list(CLIENT_LINES)
        return MagicMock()

    stub.api.side_effect = api
    stub._mud_details = lambda: ProxyPlugin._mud_details(stub)
    return stub


def test_details_disconnected() -> None:
    stub = _stub(None)
    result = ProxyPlugin._command_details(stub)
    assert result.success is True
    assert result.message[0] == "== Mud =="
    assert "Mud                           : disconnected" in result.message
    assert result.message[-3:] == ["", *CLIENT_LINES]


def test_details_connecting() -> None:
    result = ProxyPlugin._command_details(_stub(_mud(connected=False, connecting=True)))
    assert "Mud                           : connecting" in result.message


def test_details_connected_shows_rows() -> None:
    text = "\n".join(ProxyPlugin._command_details(_stub(_mud())).message)
    for expected in (
        "Host                          : mud.example",
        "Port                          : 4000",
        "Idle                          : 3s",
        "Lines sent                    : 4",
        "Lines received                : 2,000",
        "Bytes sent (uncompressed)     : 10",
        "Bytes received (uncompressed) : 99,999",
        "Local options                 : TTYPE",
        "Remote options                : GMCP, MCCP2_COMPRESS",
    ):
        assert expected in text


def test_info_shows_option_rows_not_an_empty_options_row() -> None:
    lines = ProxyPlugin._command_info(_stub(_mud())).message
    assert "Local options   : TTYPE" in lines
    assert "Remote options  : GMCP, MCCP2_COMPRESS" in lines
    assert not any(line.startswith("Options ") for line in lines)

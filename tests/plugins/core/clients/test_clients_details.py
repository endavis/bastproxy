"""Tests for the client.list.details API of the clients plugin (#422)."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins.core.clients.plugin._clients import ClientPlugin

PID = "plugins.core.clients"


def _client(addr: str = "10.0.0.5", port: int = 4242, **kwargs: Any) -> SimpleNamespace:
    values: dict[str, Any] = {
        "addr": addr,
        "port": port,
        "view_only": False,
        "term_type": "xterm",
        "connected_length": "1m",
        "idle": "7s",
        "lines_sent": 1200,
        "lines_received": 3,
        "bytes_sent": 123456,
        "bytes_received": 42,
        "telnet_options": lambda: (["EOR", "GMCP"], ["NAWS"]),
    }
    values.update(kwargs)
    return SimpleNamespace(**values)


def _stub(*clients: SimpleNamespace) -> MagicMock:
    stub = MagicMock()
    stub.plugin_id = PID
    stub.clients = {str(i): c for i, c in enumerate(clients)}

    def api(name: str) -> Any:
        assert name == "plugins.core.commands:output.header.format"
        return lambda title: [f"== {title} =="]

    stub.api = api
    return stub


def test_one_client_shows_every_row() -> None:
    lines = ClientPlugin._api_client_list_details(_stub(_client()))
    assert lines[0] == "== Client 10.0.0.5:4242 =="
    text = "\n".join(lines)
    for expected in (
        "State                         : Active",
        "Term Type                     : xterm",
        "Connected                     : 1m",
        "Idle                          : 7s",
        "Lines sent                    : 1,200",
        "Lines received                : 3",
        "Bytes sent (uncompressed)     : 123,456",
        "Bytes received (uncompressed) : 42",
        "Local options                 : EOR, GMCP",
        "Remote options                : NAWS",
    ):
        assert expected in text


def test_empty_options_show_a_dash_and_view_only_is_named() -> None:
    client = _client(view_only=True, telnet_options=lambda: ([], []))
    text = "\n".join(ClientPlugin._api_client_list_details(_stub(client)))
    assert "State                         : View only" in text
    assert "Local options                 : -" in text
    assert "Remote options                : -" in text


def test_no_clients() -> None:
    assert ClientPlugin._api_client_list_details(_stub()) == ["No clients connected"]


def test_two_clients_are_separated_by_a_blank_line() -> None:
    lines = ClientPlugin._api_client_list_details(_stub(_client(), _client("10.0.0.6", 1)))
    headers = [i for i, line in enumerate(lines) if line.startswith("== Client")]
    assert len(headers) == 2
    assert lines[headers[1] - 1] == ""

"""Tests for the formatted client and ban tables of the clients plugin (#89)."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins.core.clients.plugin._clients import ClientPlugin
from bastproxy.plugins.core.utils.plugin._utils import UtilsPlugin
from tests.plugins.core.utils.test_utils_output_table import make_utils_stub

PID = "plugins.core.clients"


def _stub(banned: dict[str, Any] | None = None, permbanips: list[str] | None = None) -> MagicMock:
    utils = make_utils_stub()
    stub = MagicMock()
    stub.plugin_id = PID
    stub.clients = {
        "uuid1": SimpleNamespace(addr="10.0.0.5", port=4242, connected_length="1m", view_only=False)
    }
    stub.banned = banned or {}

    def api(name: str) -> Any:
        if name == "plugins.core.settings:get":
            return lambda _pid, setting: list(permbanips or []) if setting == "permbanips" else "@w"
        if name == "plugins.core.utils:convert.data.to.output.table":
            return lambda *a, **k: UtilsPlugin._api_convert_data_to_output_table(utils, *a, **k)
        if name == f"{PID}:get.clients.formatted":
            return lambda: ClientPlugin._api_get_clients_formatted(stub)
        raise AssertionError(name)

    stub.api = api
    return stub


def test_one_client_no_bans() -> None:
    text = "\n".join(ClientPlugin._api_get_clients_formatted(_stub()))

    for word in ("Clients", "State", "Client IP", "Port", "Term Type", "Connected", "View Only"):
        assert word in text
    assert "10.0.0.5" in text
    assert "4242" in text
    assert "Banned IPs" not in text


def test_bans_follow_clients_table() -> None:
    stub = _stub(banned={"1.2.3.4": SimpleNamespace(expires="tomorrow")}, permbanips=["9.9.9.9"])

    msg = ClientPlugin._api_get_clients_formatted(stub)

    text = "\n".join(msg)
    assert "" in msg
    assert text.index("Clients") < text.index("Banned IPs")
    assert "1.2.3.4" in text
    assert "tomorrow" in text
    assert "9.9.9.9" in text
    assert "Permanent" in text


def test_show_returns_api_output() -> None:
    stub = _stub()
    assert ClientPlugin._command_show(stub) == (True, ClientPlugin._api_get_clients_formatted(stub))

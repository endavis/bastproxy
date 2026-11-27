"""A client socket as a proxy client: output as spans, input to the MUD (#844)."""

import asyncio
import types
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from bastproxy.libs.api import API
from bastproxy.libs.net.naws import WINDOW_SIZE
from bastproxy.libs.records import (
    LineType,
    NetworkData,
    NetworkDataLine,
    Originated,
    ProcessDataToClient,
    SendDataDirectlyToClient,
)
from bastproxy.plugins.core.clients.plugin._clients import ClientPlugin
from bastproxy.plugins.core.colors.plugin._colors import ColorsPlugin
from bastproxy.plugins.core.web.libs._proxyclient import (
    OUTPUT_QUEUE_LIMIT,
    SocketClient,
    SocketClients,
)
from bastproxy.plugins.core.web.libs._ws import CLOSE_POLICY, SocketHub


class FakeWriter:
    def __init__(self, peer: tuple[str, int] | None = ("10.1.2.3", 5555)) -> None:
        self.peer = peer

    def get_extra_info(self, name: str) -> Any:
        return self.peer if name == "peername" else None


class FakeSocket:
    """Stands in for SocketConnection: records what is sent to it."""

    def __init__(self, view_only: bool = False, peer: tuple[str, int] | None = ("1.2.3.4", 99)):
        self.view_only = view_only
        self.writer = FakeWriter(peer)
        self.sent: list[dict[str, Any]] = []
        self.waited: list[dict[str, Any]] = []
        self.closed: list[tuple[int, str]] = []
        self.open = True

    def __hash__(self) -> int:
        return id(self)

    def send(self, message: dict[str, Any]) -> bool:
        self.sent.append(message)
        return True

    async def send_wait(self, message: dict[str, Any]) -> bool:
        if not self.open:
            return False
        self.waited.append(message)
        return True

    def close(self, code: int, reason: str) -> None:
        self.closed.append((code, reason))


class TelnetStandIn:
    """A telnet-like client: records the lines it is sent."""

    conn_type = "telnet"
    addr = "9.9.9.9"
    port = "23"
    view_only = False
    term_type = "xterm"
    connected_length = "1m"
    idle = "1s"
    lines_sent = 0
    lines_received = 0
    bytes_sent = 0
    bytes_received = 0

    def __init__(self, uuid: str = "telnet1") -> None:
        self.uuid = uuid
        self.connected = True
        self.state = {"logged in": False}
        self.lines: list[NetworkDataLine] = []

    def send_to(self, line: NetworkDataLine) -> None:
        self.lines.append(line)

    def telnet_options(self) -> tuple[list[str], list[str]]:
        return [], []


class Env:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []
        self.sent_to_mud: list[NetworkDataLine] = []
        self.echo_off = False
        self.stub = types.SimpleNamespace(
            clients={}, plugin_id="plugins.core.clients", api=self._plugin_api
        )

    def _plugin_api(self, name: str) -> Callable[..., Any]:
        assert name == "plugins.core.events:event.raise"
        return self.event_raise

    def event_raise(self, name: str, **kwargs: Any) -> None:
        self.events.append((name, kwargs))
        if name.endswith("to_mud_data_modify"):
            self.sent_to_mud.extend(kwargs.get("data_list", []))

    @property
    def clients(self) -> dict[str, Any]:
        return dict(self.stub.clients)


@pytest.fixture
def env() -> Iterator[Env]:
    holder = Env()
    stub = holder.stub
    colors = types.SimpleNamespace()

    def bind(method: Callable[..., Any]) -> Callable[..., Any]:
        return lambda *a, **k: method(stub, *a, **k)

    mud = types.SimpleNamespace(echo_off=False, send_to=lambda line: None)

    def mud_get() -> Any:
        mud.echo_off = holder.echo_off
        return mud

    stand_ins: dict[str, Callable[..., Any]] = {
        "plugins.core.events:event.raise": holder.event_raise,
        "plugins.core.clients:client.add": bind(ClientPlugin._api_client_add),
        "plugins.core.clients:client.remove": bind(ClientPlugin._api_client_remove),
        "plugins.core.clients:client.send": bind(ClientPlugin._api_client_send),
        "plugins.core.clients:client.list": bind(ClientPlugin._api_client_list),
        "plugins.core.clients:client.is.logged.in": bind(ClientPlugin._api_client_is_logged_in),
        "plugins.core.clients:client.is.view.client": bind(ClientPlugin._api_is_client_view_client),
        "plugins.core.clients:client.logged.in.set": bind(ClientPlugin._api_client_logged_in_set),
        "plugins.core.clients:client.logged.in.set.view.only": bind(
            ClientPlugin._api_client_logged_in_set_view_only
        ),
        "plugins.core.clients:client.width.get": bind(ClientPlugin._api_client_width_get),
        "plugins.core.colors:ansicode.to.spans": lambda text: ColorsPlugin._api_ansicode_to_spans(
            colors, text
        ),
        "plugins.core.utils:timedelta.to.string": lambda a, b: "1s",
        "plugins.core.proxy:mud.connection.get": mud_get,
    }
    saved = {name: API._class_api.get(name) for name in stand_ins}
    api = API("test844")
    for full_name, func in stand_ins.items():
        top, name = full_name.split(":")
        api.add(top, name, func, force=True, description="stand-in")
    WINDOW_SIZE.reset()
    try:
        yield holder
    finally:
        WINDOW_SIZE.reset()
        for full_name, item in saved.items():
            if item is None:
                API._class_api.pop(full_name, None)
            else:
                API._class_api[full_name] = item


def _open(env: Env, *, view_only: bool = False) -> tuple[SocketClients, FakeSocket, SocketClient]:
    hub = SocketHub()
    sockets = SocketClients(hub)
    sock = FakeSocket(view_only=view_only)
    sockets.opened(sock)  # type: ignore[arg-type]
    client = sockets.client_for(sock)  # type: ignore[arg-type]
    assert client is not None
    return sockets, sock, client


async def _settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


def _line(text: str, **fields: Any) -> NetworkDataLine:
    line = NetworkDataLine(text, originated=Originated.MUD)
    for name, value in fields.items():
        setattr(line, name, value)
    return line


async def test_registration_logged_in_full(env: Env) -> None:
    sockets, _sock, client = _open(env)
    assert client.conn_type == "websocket"
    assert client.term_type == "websocket"
    assert (client.addr, client.port) == ("1.2.3.4", "99")
    assert env.clients[client.uuid] is client
    assert client.state["logged in"] is True
    assert client.view_only is False
    assert client.uuid in WINDOW_SIZE._clients
    sockets.close()


async def test_registration_view_only_and_no_peer(env: Env) -> None:
    hub = SocketHub()
    sockets = SocketClients(hub)
    sock = FakeSocket(view_only=True, peer=None)
    sockets.opened(sock)  # type: ignore[arg-type]
    client = sockets.client_for(sock)  # type: ignore[arg-type]
    assert client is not None
    assert (client.addr, client.port) == ("-", "-")
    assert client.state["logged in"] is True
    assert client.view_only is True
    assert client.uuid not in WINDOW_SIZE._clients
    sockets.close()


async def test_closed_removes_the_client_and_stops_the_writer(env: Env) -> None:
    sockets, sock, client = _open(env)
    task = client.task
    assert task is not None
    sockets.closed(sock)  # type: ignore[arg-type]
    await _settle()
    assert env.clients == {}
    assert client.connected is False
    assert task.cancelled()
    assert sockets.client_for(sock) is None  # type: ignore[arg-type]
    assert client.uuid not in WINDOW_SIZE._clients


async def test_close_drops_all_and_unregisters(env: Env) -> None:
    hub = SocketHub()
    sockets = SocketClients(hub)
    first, second = FakeSocket(), FakeSocket()
    sockets.opened(first)  # type: ignore[arg-type]
    sockets.opened(second)  # type: ignore[arg-type]
    assert len(env.clients) == 2
    sockets.close()
    assert env.clients == {}
    assert "input" not in hub.handlers
    assert "cols" not in hub.handlers
    assert hub._listeners == []


async def test_registration_failure_closes_the_socket(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(_client: Any) -> None:
        raise RuntimeError("no clients plugin")

    API("test844").add("plugins.core.clients", "client.add", boom, force=True, description="x")
    hub = SocketHub()
    sockets = SocketClients(hub)
    sock = FakeSocket()
    sockets.opened(sock)  # type: ignore[arg-type]
    assert sock.closed and sock.closed[0][0] == 1011
    assert sockets.client_for(sock) is None  # type: ignore[arg-type]
    sockets.close()


async def test_output_matches_telnet(env: Env) -> None:
    sockets, sock, client = _open(env)
    telnet = TelnetStandIn()
    env.stub.clients[telnet.uuid] = telnet
    telnet.state["logged in"] = True
    prompt = _line("hp> ", is_prompt=True)
    gagged = _line("secret", send=False)
    command = NetworkDataLine(b"\xff\xfb\x01", line_type=LineType.COMMAND_TELNET)
    lines = [
        _line("a MUD line"),
        _line("\x1b[31mred\x1b[0m text"),
        command,
        prompt,
        gagged,
    ]
    ProcessDataToClient(NetworkData(lines))()
    await _settle()
    telnet_io = [line for line in telnet.lines if line.is_io]
    assert [str(line.line).rstrip("\r\n") for line in telnet_io] == [
        "a MUD line",
        "\x1b[31mred\x1b[0m text",
        "hp> ",
    ]
    assert len(sock.waited) == len(telnet_io)
    colors = types.SimpleNamespace()
    for message, line in zip(sock.waited, telnet_io, strict=True):
        assert message["type"] == "output"
        assert message["v"] == 1
        assert message["spans"] == ColorsPlugin._api_ansicode_to_spans(
            colors, str(line.line).rstrip("\r\n")
        )
        assert message["record"] == line.uuid
        assert message["prompt"] is bool(line.is_prompt)
    assert [m["prompt"] for m in sock.waited] == [False, False, True]
    assert client.lines_sent == 3
    assert all(line.was_sent for line in telnet_io)
    sockets.close()


async def test_view_only_skips_internal_lines(env: Env) -> None:
    sockets, sock, _client = _open(env, view_only=True)
    internal = NetworkDataLine("from a command", preamble=False)
    SendDataDirectlyToClient(NetworkData([internal]))()
    ProcessDataToClient(NetworkData([_line("from the mud")]))()
    await _settle()
    assert [m["spans"][0]["text"] for m in sock.waited] == ["from the mud"]
    sockets.close()


async def test_targeting(env: Env) -> None:
    sockets, sock, client = _open(env)
    other = TelnetStandIn()
    other.state["logged in"] = True
    env.stub.clients[other.uuid] = other
    ProcessDataToClient(NetworkData([_line("only socket")]), clients=[client.uuid])()
    ProcessDataToClient(NetworkData([_line("not socket")]), exclude_clients=[client.uuid])()
    await _settle()
    assert [m["spans"][0]["text"] for m in sock.waited] == ["only socket"]
    assert [str(line.line).rstrip("\r\n") for line in other.lines] == ["not socket"]
    sockets.close()


async def test_output_queue_overflow_closes_the_socket(env: Env) -> None:
    sockets, sock, client = _open(env)
    assert client.task is not None
    client.task.cancel()
    await _settle()
    for index in range(OUTPUT_QUEUE_LIMIT):
        client.send_to(_line(f"l{index}"))
    assert sock.closed == []
    client.send_to(_line("one too many"))
    assert sock.closed == [(CLOSE_POLICY, "output queue full")]
    assert client.connected is False
    client.send_to(_line("ignored"))
    assert client.queue.qsize() == OUTPUT_QUEUE_LIMIT
    sockets.close()


async def test_send_to_ignores_non_io_and_wrong_types(env: Env) -> None:
    sockets, _sock, client = _open(env)
    assert client.task is not None
    client.task.cancel()
    client.send_to("not a line")
    client.send_to(NetworkDataLine(b"\xff", line_type=LineType.COMMAND_TELNET))
    assert client.queue.qsize() == 0
    sockets.close()


async def test_writer_stops_when_the_socket_closes(env: Env) -> None:
    sockets, sock, client = _open(env)
    sock.open = False
    client.send_to(_line("x"))
    assert client.task is not None
    await asyncio.wait_for(client.task, 1)
    assert client.lines_sent == 0
    sockets.close()


async def test_input_reaches_the_mud(env: Env) -> None:
    sockets, sock, client = _open(env)
    client.handle_input({"text": "#bp.core.web.status"})
    assert [str(line.line).rstrip("\r\n") for line in env.sent_to_mud] == ["#bp.core.web.status"]
    line = env.sent_to_mud[0]
    assert line.originated == Originated.CLIENT
    assert client.lines_received == 1
    assert sock.sent == []
    sockets.close()


async def test_input_lines_and_empty(env: Env) -> None:
    sockets, _sock, client = _open(env)
    client.handle_input({"text": "a\nb"})
    client.handle_input({"text": ""})
    assert [str(line.line).rstrip("\r\n") for line in env.sent_to_mud] == ["a", "b", ""]
    assert client.lines_received == 3
    sockets.close()


async def test_input_masks_the_log_while_the_mud_echo_is_off(env: Env) -> None:
    sockets, _sock, client = _open(env)
    env.echo_off = True
    client.handle_input({"text": "secret"})
    assert env.sent_to_mud[0].mask_log is True
    sockets.close()


async def test_input_must_be_text(env: Env) -> None:
    sockets, sock, client = _open(env)
    client.handle_input({"text": 5})
    client.handle_input({})
    assert [m["code"] for m in sock.sent] == ["bad_message", "bad_message"]
    assert env.sent_to_mud == []
    sockets.close()


async def test_view_only_input_is_refused(env: Env) -> None:
    sockets, sock, client = _open(env, view_only=True)
    client.handle_input({"text": "look"})
    assert sock.sent[0]["type"] == "error"
    assert sock.sent[0]["code"] == "view_only"
    assert sock.sent[0]["for"] == "input"
    assert env.sent_to_mud == []
    assert client.lines_received == 0
    sockets.close()


async def test_handlers_route_over_the_hub(env: Env) -> None:
    hub = SocketHub()
    sockets = SocketClients(hub)
    sock = FakeSocket()
    sockets.opened(sock)  # type: ignore[arg-type]
    hub.handlers["input"](sock, {"v": 1, "type": "input", "text": "go"})  # type: ignore[arg-type]
    hub.handlers["cols"](sock, {"v": 1, "type": "cols", "cols": 99})  # type: ignore[arg-type]
    stranger = FakeSocket()
    hub.handlers["input"](stranger, {"text": "x"})  # type: ignore[arg-type]
    hub.handlers["cols"](stranger, {"cols": 5})  # type: ignore[arg-type]
    assert [str(line.line).rstrip("\r\n") for line in env.sent_to_mud] == ["go"]
    client = sockets.client_for(sock)  # type: ignore[arg-type]
    assert client is not None
    assert client.cols == 99
    sockets.close()


async def test_cols_sets_the_width(env: Env) -> None:
    sockets, sock, client = _open(env)
    client.handle_cols({"cols": 120, "rows": 40})
    api = API("test844")
    assert api("plugins.core.clients:client.width.get")(client.uuid) == 120
    assert (client.cols, client.rows, client.naws_reported) == (120, 40, True)
    assert WINDOW_SIZE.target() == (120, 40)
    client.handle_cols({"cols": 100})
    assert (client.cols, client.rows) == (100, 25)
    assert sock.sent == []
    sockets.close()


@pytest.mark.parametrize(
    "message",
    [
        {"cols": 0},
        {"cols": 70000},
        {"cols": True},
        {"cols": "80"},
        {},
        {"cols": 80, "rows": 0},
        {"cols": 80, "rows": "x"},
        {"cols": 80, "rows": False},
    ],
)
async def test_cols_rejects_bad_values(env: Env, message: dict[str, Any]) -> None:
    sockets, sock, client = _open(env)
    client.handle_cols(message)
    assert sock.sent[0]["code"] == "bad_message"
    assert sock.sent[0]["for"] == "cols"
    assert client.naws_reported is False
    assert client.cols == 80
    sockets.close()


async def test_list_details_shows_the_type(env: Env) -> None:
    sockets, _sock, _client = _open(env)
    telnet = TelnetStandIn()
    env.stub.clients[telnet.uuid] = telnet
    stub = types.SimpleNamespace(
        clients=env.stub.clients,
        api=lambda name: lambda title: [f"== {title} =="],
    )
    text = "\n".join(ClientPlugin._api_client_list_details(stub))
    assert "Type                          : websocket" in text
    assert "Type                          : telnet" in text
    assert "Term Type                     : websocket" in text
    sockets.close()


async def test_client_properties(env: Env) -> None:
    sockets, _sock, client = _open(env)
    assert client.connected_length == "1s"
    assert client.idle == "1s"
    assert client.telnet_options() == ([], [])
    assert client.mxp_enabled is False
    sockets.close()

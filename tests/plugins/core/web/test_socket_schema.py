"""The JSON Schema of the client socket messages, checked against what the proxy sends (#870)."""

import ast
import asyncio
import json
import types
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
from websockets.asyncio.client import ClientConnection, connect

from bastproxy.libs.api import API
from bastproxy.libs.records import NetworkDataLine, Originated
from bastproxy.plugins.core.colors.plugin._colors import ColorsPlugin
from bastproxy.plugins.core.commands.plugin._commands import CALL_REASONS
from bastproxy.plugins.core.web.libs import _proxyclient, _ws
from bastproxy.plugins.core.web.libs._call import MAX_COMMAND_LENGTH, MAX_ID_LENGTH, Calls
from bastproxy.plugins.core.web.libs._proxyclient import MAX_DIMENSION, SocketClient, SocketClients
from bastproxy.plugins.core.web.libs._server import WebApp, WebServer
from bastproxy.plugins.core.web.libs._store import (
    PageStore,
    ProviderListeners,
    RouteTable,
    SessionStore,
)
from bastproxy.plugins.core.web.libs._subscribe import Subscriptions

from .schema_check import errors, is_valid, load_schema

SCHEMA = load_schema()
DEFS: dict[str, Any] = SCHEMA["$defs"]
LIBS = Path(_ws.__file__).parent
SERVER_TYPES = {"hello", "output", "snapshot", "update", "result", "error"}
CLIENT_TYPES = {"input", "cols", "subscribe", "unsubscribe", "call"}
OWNER = "plugins.test.caller"
TOPIC = "test.caller.mobs"
OPEN_TIMEOUT = 5


def wire(message: dict[str, Any]) -> Any:
    """A message as the client receives it: through json, as the socket sends it."""
    return json.loads(json.dumps(message, default=str))


def valid(message: Any) -> bool:
    return is_valid(SCHEMA, message)


def assert_valid(message: Any) -> None:
    assert not errors(SCHEMA, message), (message, errors(SCHEMA, message))


def type_names(def_name: str) -> set[str]:
    """The message types listed by a root-level ``oneOf`` def (``serverMessage``)."""
    names: set[str] = set()
    for option in DEFS[def_name]["oneOf"]:
        target = DEFS[option["$ref"].rsplit("/", 1)[1]]
        variants = target.get("oneOf", [target])
        names |= {variant["properties"]["type"]["const"] for variant in variants}
    return names


def literal_calls(function: str) -> list[ast.Call]:
    """Every call of ``function`` with a literal string first argument in the web libs."""
    found: list[ast.Call] = []
    for path in LIBS.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == function
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                found.append(node)
    return found


def enum_values(def_name: str) -> set[Any]:
    definition = DEFS[def_name]
    if "enum" in definition:
        return set(definition["enum"])
    return {option["const"] for option in definition["oneOf"]}


# ---- the schema itself


def test_the_schema_is_draft_2020_12_and_a_closed_set_of_messages() -> None:
    assert SCHEMA["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert SCHEMA["oneOf"] == [
        {"$ref": "#/$defs/serverMessage"},
        {"$ref": "#/$defs/clientMessage"},
    ]


def test_every_message_type_is_present_in_both_directions() -> None:
    assert type_names("serverMessage") == SERVER_TYPES
    assert type_names("clientMessage") == CLIENT_TYPES
    for name in SERVER_TYPES | CLIENT_TYPES:
        assert name in DEFS


def test_every_message_is_closed_and_carries_the_version() -> None:
    for name in SERVER_TYPES | CLIENT_TYPES:
        definition = DEFS[name]
        for variant in definition.get("oneOf", [definition]):
            assert variant["additionalProperties"] is False
            assert variant["properties"]["v"] == {"$ref": "#/$defs/version"}
            assert {"v", "type"} <= set(variant["required"])
    assert DEFS["version"]["const"] == 1


def test_client_types_equal_the_registered_handlers() -> None:
    hub = _ws.SocketHub()
    SocketClients(hub)
    Subscriptions(hub, RouteTable, ProviderListeners())
    Calls(hub, lambda command, arguments: None, lambda text: [])
    assert set(hub.handlers) == CLIENT_TYPES == type_names("clientMessage")


def test_server_types_equal_the_literal_types_the_code_builds() -> None:
    built = {str(call.args[0].value) for call in literal_calls("envelope")}  # type: ignore[attr-defined]
    if literal_calls("error_message"):
        built.add("error")
    assert built == SERVER_TYPES == type_names("serverMessage")


def test_error_codes_equal_the_codes_the_code_uses() -> None:
    used = {str(call.args[0].value) for call in literal_calls("error_message")}  # type: ignore[attr-defined]
    assert used == enum_values("errorCode")


def test_close_codes_equal_the_codes_the_code_defines() -> None:
    defined = {
        value
        for name, value in vars(_ws).items()
        if name.startswith("CLOSE_") and name != "CLOSE_TIMEOUT"
    }
    assert defined | {1009} == enum_values("closeCode")
    assert _ws.MAX_MESSAGE == 65536
    for option in DEFS["closeCode"]["oneOf"]:
        assert option["description"]


def test_call_reasons_equal_the_commands_reasons_and_timeout() -> None:
    assert enum_values("callReason") == set(CALL_REASONS) | {"timeout"}


def test_limits_equal_the_code() -> None:
    call = DEFS["call"]["properties"]
    assert call["command"]["maxLength"] == MAX_COMMAND_LENGTH
    assert DEFS["callId"]["oneOf"][0]["maxLength"] == MAX_ID_LENGTH
    cols = DEFS["cols"]["properties"]
    assert cols["cols"]["maximum"] == cols["rows"]["maximum"] == MAX_DIMENSION
    assert cols["cols"]["minimum"] == cols["rows"]["minimum"] == 1


def referenced(node: Any) -> set[str]:
    if isinstance(node, dict):
        names = {node["$ref"].rsplit("/", 1)[1]} if "$ref" in node else set()
        for key, value in node.items():
            if key != "$defs":
                names |= referenced(value)
        return names
    if isinstance(node, list):
        return set().union(*(referenced(item) for item in node)) if node else set()
    return set()


def test_every_def_is_used() -> None:
    used = referenced(SCHEMA)
    for definition in DEFS.values():
        used |= referenced(definition)
    # the close codes describe the socket, not a message field
    assert set(DEFS) - used == {"closeCode"}


# ---- messages the proxy builds


class FakeConnection:
    """Stands in for a socket: records what is sent."""

    def __init__(self, view_only: bool = False) -> None:
        self.subscriptions: set[str] = set()
        self.sent: list[dict[str, Any]] = []
        self.view_only = view_only
        self.writer = types.SimpleNamespace(get_extra_info=lambda name: ("1.2.3.4", 99))

    def __hash__(self) -> int:
        return id(self)

    def send(self, message: dict[str, Any]) -> bool:
        self.sent.append(message)
        return True

    async def send_wait(self, message: dict[str, Any]) -> bool:
        return self.send(message)

    def close(self, code: int, reason: str) -> None:
        pass


async def run_handler(hub: _ws.SocketHub, connection: Any, message: dict[str, Any]) -> None:
    result = hub.handlers[message["type"]](connection, message)
    if asyncio.iscoroutine(result):
        await result


class Live:
    """A listener with one session, for messages that cross a real socket."""

    def __init__(self, server: WebServer, sessions: SessionStore, port: int) -> None:
        self.server = server
        self.port = port
        self.sid = sessions.create(3600)

    async def open(self) -> ClientConnection:
        return await connect(
            f"ws://127.0.0.1:{self.port}/ws",
            origin=f"http://127.0.0.1:{self.port}",  # type: ignore[arg-type]
            additional_headers={"Cookie": f"bpsession={self.sid}"},
            open_timeout=OPEN_TIMEOUT,
        )


@pytest.fixture
async def live() -> AsyncIterator[Live]:
    sessions = SessionStore()
    server = WebServer()
    holder: dict[str, Live] = {}
    app = WebApp(
        PageStore(),
        sessions=sessions,
        allowed_origins=lambda: [f"http://127.0.0.1:{holder['live'].port}/"],
        proxy_version="9.9.9",
    )
    app.routes.add_provider(OWNER, "mobs", lambda: [["Orc", 5]], None, "json", None, str)
    port = await server.start("127.0.0.1", 0, app, None)
    holder["live"] = Live(server, sessions, port)
    yield holder["live"]
    server.close()
    await server.wait_closed()


async def receive(conn: ClientConnection) -> dict[str, Any]:
    async with asyncio.timeout(OPEN_TIMEOUT):
        message = json.loads(await conn.recv())
    assert isinstance(message, dict)
    return message


async def test_a_live_socket_sends_valid_hello_and_error_messages(live: Live) -> None:
    async with await live.open() as conn:
        hello = await receive(conn)
        assert hello["type"] == "hello"
        assert hello["topics"] == [TOPIC]
        assert_valid(hello)
        for text in (
            "{not json",
            "[]",
            json.dumps({"v": 2, "type": "x"}),
            json.dumps({"v": 1}),
            json.dumps({"v": 1, "type": "nope"}),
        ):
            await conn.send(text)
            error = await receive(conn)
            assert error["type"] == "error"
            assert_valid(error)


async def test_a_live_socket_accepts_the_sample_client_messages(live: Live) -> None:
    hub = live.server.sockets
    seen: list[str] = []
    both = asyncio.Event()

    def handle(conn: Any, message: dict[str, Any]) -> None:
        seen.append(message["type"])
        if len(seen) == 2:
            both.set()

    for kind in ("input", "cols"):
        hub.register(kind, handle)
    async with await live.open() as conn:
        await receive(conn)
        for message in (
            {"v": 1, "type": "input", "text": "look"},
            {"v": 1, "type": "cols", "cols": 80, "rows": 24},
        ):
            assert_valid(message)
            await conn.send(json.dumps(message))
        async with asyncio.timeout(OPEN_TIMEOUT):
            await both.wait()
        assert seen == ["input", "cols"]


class SubEnv:
    def __init__(self) -> None:
        self.hub = _ws.SocketHub()
        self.routes = RouteTable()
        self.listeners = ProviderListeners()
        self.data: Any = [["Orc", 5]]
        self.subs = Subscriptions(self.hub, lambda: self.routes, self.listeners, 0.02)
        self.routes.add_provider(OWNER, "mobs", self.snapshot, None, "json", None, str)

    def snapshot(self) -> Any:
        if isinstance(self.data, Exception):
            raise self.data
        return self.data


async def test_subscription_messages_are_valid() -> None:
    env = SubEnv()
    connection = FakeConnection()
    env.hub.add(connection)  # type: ignore[arg-type]
    subscribe = {"v": 1, "type": "subscribe", "topic": TOPIC}
    assert_valid(subscribe)
    await run_handler(env.hub, connection, subscribe)
    env.data = {"nested": [1, 2.5, None, "x"]}
    env.listeners.notify(TOPIC)
    await asyncio.sleep(0.1)
    env.data = RuntimeError("boom")
    env.listeners.notify(TOPIC)
    await asyncio.sleep(0.1)
    env.subs.removed([TOPIC])
    for message in (
        {"v": 1, "type": "subscribe"},
        {"v": 1, "type": "subscribe", "topic": "no.such"},
    ):
        await run_handler(env.hub, connection, message)
    kinds = [(m["type"], m.get("code")) for m in connection.sent]
    assert kinds == [
        ("snapshot", None),
        ("update", None),
        ("error", "snapshot_failed"),
        ("error", "topic_removed"),
        ("error", "bad_message"),
        ("error", "unknown_topic"),
    ]
    for message in connection.sent:
        assert_valid(wire(message))
    unsubscribe = {"v": 1, "type": "unsubscribe", "topic": TOPIC}
    assert_valid(unsubscribe)
    await run_handler(env.hub, connection, unsubscribe)
    env.subs.close()


class CallEnv:
    def __init__(self) -> None:
        self.hub = _ws.SocketHub()
        self.reply: Any = {"ok": True, "reason": "", "lines": ["a@Rb", "c"], "data": {"n": 1}}
        self.calls = Calls(self.hub, lambda c, a: self.reply, self.spans, timeout=0.05)

    @staticmethod
    def spans(text: str) -> list[dict[str, Any]]:
        return [{"text": text, "fg": None, "bg": 9, "bold": False}]


@pytest.mark.parametrize("reason", sorted(set(CALL_REASONS) | {"timeout"}))
async def test_call_results_are_valid_for_every_reason(reason: str) -> None:
    env = CallEnv()
    connection = FakeConnection()
    if reason == "timeout":

        async def slow(command: str, arguments: str) -> Any:
            await asyncio.sleep(1)

        env.calls._runner = slow
    else:
        env.reply = {"ok": False, "reason": reason, "lines": ["x"], "data": None}
    call = {"v": 1, "type": "call", "id": "c1", "command": "core.web.status", "args": "-x"}
    assert_valid(call)
    await run_handler(env.hub, connection, call)
    result = wire(connection.sent[0])
    assert result["reason"] == reason
    assert_valid(result)


async def test_call_ok_results_and_refusals_are_valid() -> None:
    env = CallEnv()
    connection = FakeConnection()
    calls = [
        {"v": 1, "type": "call", "id": 7, "command": "c"},
        {"v": 1, "type": "call", "id": "x" * MAX_ID_LENGTH, "command": "c", "args": ["a", "b c"]},
        {"v": 1, "type": "call", "id": "n", "command": "c", "args": None},
    ]
    for call in calls:
        assert_valid(call)
        await run_handler(env.hub, connection, call)
    assert [m["ok"] for m in connection.sent] == [True, True, True]
    bad = [
        {"v": 1, "type": "call", "command": "c"},
        {"v": 1, "type": "call", "id": "1", "command": ""},
        {"v": 1, "type": "call", "id": "1", "command": "c", "args": 5},
    ]
    for call in bad:
        await run_handler(env.hub, connection, call)
    view_only = FakeConnection(view_only=True)
    await run_handler(env.hub, view_only, calls[0])
    assert view_only.sent[0]["id"] == 7
    for message in [*connection.sent, *view_only.sent]:
        assert_valid(wire(message))
    assert [m["code"] for m in connection.sent[3:]] == ["bad_message"] * 3
    assert view_only.sent[0]["code"] == "view_only"


@pytest.fixture
def colors_api() -> Iterator[None]:
    name = "plugins.core.colors:ansicode.to.spans"
    saved = API._class_api.get(name)
    colors = types.SimpleNamespace()
    API("test870").add(
        "plugins.core.colors",
        "ansicode.to.spans",
        lambda text: ColorsPlugin._api_ansicode_to_spans(colors, text),
        force=True,
        description="stand-in",
    )
    try:
        yield
    finally:
        if saved is None:
            API._class_api.pop(name, None)
        else:
            API._class_api[name] = saved


def socket_client(view_only: bool = False) -> tuple[SocketClient, FakeConnection]:
    sock = FakeConnection(view_only=view_only)
    return SocketClient(sock, "1.2.3.4", "99"), sock  # type: ignore[arg-type]


@pytest.mark.usefixtures("colors_api")
def test_output_messages_are_valid() -> None:
    client, _sock = socket_client()
    lines = [
        NetworkDataLine("a MUD line", originated=Originated.MUD),
        NetworkDataLine(
            "\x1b[1;31mred\x1b[0m and \x1b[38;5;200mpink\x1b[0m", originated=Originated.MUD
        ),
        NetworkDataLine("", originated=Originated.MUD),
        NetworkDataLine("one\r\ntwo", originated=Originated.MUD),
    ]
    prompt = NetworkDataLine("hp> ", originated=Originated.MUD)
    prompt.is_prompt = True
    for line in [*lines, prompt]:
        message = wire(client.output_message(line))
        assert_valid(message)
        assert message["record"] == line.uuid
    assert wire(client.output_message(prompt))["prompt"] is True


def test_input_and_cols_messages_are_accepted_and_refused_like_the_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, sock = socket_client()
    sent_lines: list[Any] = []
    monkeypatch.setattr(SocketClient, "_mud_echo_off", lambda self: False)
    monkeypatch.setattr(
        _proxyclient, "ProcessDataToMud", lambda data, client_id: lambda: sent_lines.append(data)
    )
    for message in (
        {"v": 1, "type": "input", "text": "look"},
        {"v": 1, "type": "input", "text": ""},
        {"v": 1, "type": "cols", "cols": 1},
        {"v": 1, "type": "cols", "cols": 65535, "rows": 65535},
    ):
        assert_valid(message)
    client.handle_input({"v": 1, "type": "input", "text": "a\nb"})
    assert len(sent_lines) == 2
    client.handle_cols({"v": 1, "type": "cols", "cols": 120, "rows": 40})
    assert (client.cols, client.rows) == (120, 40)
    assert sock.sent == []
    client.handle_input({"v": 1, "type": "input", "text": 5})
    client.handle_cols({"v": 1, "type": "cols", "cols": 0})
    only, only_sock = socket_client(view_only=True)
    only.handle_input({"v": 1, "type": "input", "text": "look"})
    assert [m["code"] for m in sock.sent + only_sock.sent] == [
        "bad_message",
        "bad_message",
        "view_only",
    ]
    for message in sock.sent + only_sock.sent:
        assert_valid(wire(message))
    assert only_sock.sent[0]["message"] == "this session is view only"


# ---- malformed messages


MALFORMED_CLIENT: list[tuple[str, dict[str, Any]]] = [
    ("no version", {"type": "input", "text": "x"}),
    ("version 2", {"v": 2, "type": "input", "text": "x"}),
    ("version true", {"v": True, "type": "input", "text": "x"}),
    ("version 1.0", {"v": 1.0, "type": "input", "text": "x"}),
    ("no type", {"v": 1, "text": "x"}),
    ("unknown type", {"v": 1, "type": "nope"}),
    ("input without text", {"v": 1, "type": "input"}),
    ("input text number", {"v": 1, "type": "input", "text": 5}),
    ("cols without cols", {"v": 1, "type": "cols", "rows": 5}),
    ("cols zero", {"v": 1, "type": "cols", "cols": 0}),
    ("cols too big", {"v": 1, "type": "cols", "cols": 65536}),
    ("cols bool", {"v": 1, "type": "cols", "cols": True}),
    ("cols string", {"v": 1, "type": "cols", "cols": "80"}),
    ("rows zero", {"v": 1, "type": "cols", "cols": 80, "rows": 0}),
    ("subscribe without topic", {"v": 1, "type": "subscribe"}),
    ("subscribe empty topic", {"v": 1, "type": "subscribe", "topic": ""}),
    ("subscribe topic number", {"v": 1, "type": "subscribe", "topic": 3}),
    ("call without id", {"v": 1, "type": "call", "command": "c"}),
    ("call empty id", {"v": 1, "type": "call", "id": "", "command": "c"}),
    ("call long id", {"v": 1, "type": "call", "id": "x" * 65, "command": "c"}),
    ("call bool id", {"v": 1, "type": "call", "id": True, "command": "c"}),
    ("call without command", {"v": 1, "type": "call", "id": "1"}),
    ("call empty command", {"v": 1, "type": "call", "id": "1", "command": ""}),
    ("call long command", {"v": 1, "type": "call", "id": "1", "command": "c" * 257}),
    ("call args number", {"v": 1, "type": "call", "id": "1", "command": "c", "args": 5}),
    ("call args mixed list", {"v": 1, "type": "call", "id": "1", "command": "c", "args": ["a", 1]}),
]

# the schema is stricter than the server here: the server ignores extra fields
EXTRA_FIELDS: list[dict[str, Any]] = [
    {"v": 1, "type": "input", "text": "x", "extra": 1},
    {"v": 1, "type": "cols", "cols": 80, "extra": 1},
    {"v": 1, "type": "subscribe", "topic": TOPIC, "extra": 1},
    {"v": 1, "type": "unsubscribe", "topic": TOPIC, "extra": 1},
    {"v": 1, "type": "call", "id": "1", "command": "c", "extra": 1},
]


@pytest.mark.parametrize(
    ("label", "message"), MALFORMED_CLIENT, ids=[c[0] for c in MALFORMED_CLIENT]
)
def test_malformed_client_messages_fail_the_schema(label: str, message: dict[str, Any]) -> None:
    assert not valid(message), label


@pytest.mark.parametrize("message", EXTRA_FIELDS)
def test_extra_fields_fail_the_schema_but_not_the_server(message: dict[str, Any]) -> None:
    assert not valid(message)
    assert _ws.parse_message(json.dumps(message)) == (message, None)


@pytest.mark.parametrize(
    "text",
    [
        "{not json",
        "[]",
        '"x"',
        "null",
        '{"v": 2, "type": "x"}',
        '{"v": true, "type": "x"}',
        '{"v": 1}',
        '{"v": 1, "type": ""}',
    ],
)
def test_the_server_refuses_malformed_envelopes(text: str) -> None:
    message, error = _ws.parse_message(text)
    assert message is None
    assert error is not None
    assert_valid(wire(error))
    if text.startswith("{not"):
        return  # not json at all, so there is nothing to validate
    assert not valid(json.loads(text))


async def test_the_server_refuses_the_malformed_handler_messages() -> None:
    sub = SubEnv()
    call = CallEnv()
    clients_hub = _ws.SocketHub()
    SocketClients(clients_hub)
    refused = 0
    for label, message in MALFORMED_CLIENT:
        kind = message.get("type")
        if type(message.get("v")) is not int or message["v"] != 1 or kind not in CLIENT_TYPES:
            continue
        for hub in (sub.hub, call.hub, clients_hub):
            if kind in hub.handlers:
                connection = FakeConnection()
                if kind in {"input", "cols"}:
                    client, connection = socket_client()
                    getattr(client, f"handle_{kind}")(message)
                else:
                    await run_handler(hub, connection, message)
                assert [m["type"] for m in connection.sent] == ["error"], label
                assert connection.sent[0]["code"] == "bad_message", label
                refused += 1
    assert refused >= 15


@pytest.mark.parametrize(
    "message",
    [
        {"v": 1, "type": "hello", "protocol": 1, "proxy": "1", "connection": "c"},
        {"v": 1, "type": "hello", "protocol": 2, "proxy": "1", "connection": "c", "topics": []},
        {"v": 1, "type": "output", "spans": [{"text": "x"}], "prompt": False, "record": "r"},
        {"v": 1, "type": "output", "spans": [], "prompt": 0, "record": "r"},
        {
            "v": 1,
            "type": "output",
            "spans": [{"text": "x", "fg": 256, "bg": None, "bold": False}],
            "prompt": False,
            "record": "r",
        },
        {"v": 1, "type": "snapshot", "topic": "t"},
        {"v": 1, "type": "update", "data": 1},
        {"v": 1, "type": "result", "id": "1", "ok": False, "reply": {"lines": [], "data": None}},
        {
            "v": 1,
            "type": "result",
            "id": "1",
            "ok": True,
            "reason": "failed",
            "reply": {"lines": [], "data": None},
        },
        {
            "v": 1,
            "type": "result",
            "id": "1",
            "ok": False,
            "reason": "nope",
            "reply": {"lines": [], "data": None},
        },
        {
            "v": 1,
            "type": "result",
            "id": "1",
            "ok": True,
            "reply": {"lines": [{"text": "x"}], "data": None},
        },
        {"v": 1, "type": "error", "code": "nope", "message": "m"},
        {"v": 1, "type": "error", "code": "bad_json"},
        {"v": 2, "type": "error", "code": "bad_json", "message": "m"},
        {"type": "error", "code": "view_only", "message": "m"},
    ],
)
def test_malformed_server_messages_fail_the_schema(message: dict[str, Any]) -> None:
    assert not valid(message)


def test_a_valid_sample_of_each_server_type_passes() -> None:
    span = {"text": "x", "fg": 1, "bg": None, "bold": True}
    samples: list[dict[str, Any]] = [
        {
            "v": 1,
            "type": "hello",
            "protocol": 1,
            "proxy": "1",
            "connection": "c",
            "topics": ["a.b"],
        },
        {"v": 1, "type": "output", "spans": [span], "prompt": True, "record": "r"},
        {"v": 1, "type": "snapshot", "topic": "t", "data": None},
        {"v": 1, "type": "update", "topic": "t", "data": [1, {"a": 2}]},
        {"v": 1, "type": "snapshot", "topic": "t", "data": None, "unavailable": "No database."},
        {"v": 1, "type": "update", "topic": "t", "data": None, "unavailable": "Gone."},
        {"v": 1, "type": "result", "id": 1, "ok": True, "reply": {"lines": [[span]], "data": 3}},
        {
            "v": 1,
            "type": "result",
            "id": "1",
            "ok": False,
            "reason": "error",
            "reply": {"lines": [], "data": None},
        },
        {"v": 1, "type": "error", "code": "view_only", "message": "m", "for": "call", "id": 4},
        {"v": 1, "type": "error", "code": "topic_removed", "message": "m", "topic": "t"},
    ]
    for sample in samples:
        assert_valid(sample)


@pytest.mark.parametrize("kind", ["snapshot", "update"])
@pytest.mark.parametrize("unavailable", ["", 3, None, ["m"]])
def test_a_bad_unavailable_fails_the_schema(kind: str, unavailable: Any) -> None:
    assert not valid({"v": 1, "type": kind, "topic": "t", "data": None, "unavailable": unavailable})


async def test_unavailable_table_messages_are_valid() -> None:
    env = SubEnv()
    env.routes.add_provider(
        OWNER, "grid", env.snapshot, [{"name": "a", "label": "A"}], "table", None, str
    )
    connection = FakeConnection()
    env.hub.add(connection)  # type: ignore[arg-type]
    topic = "test.caller.grid"
    env.data = {"unavailable": "No database."}
    await run_handler(env.hub, connection, {"v": 1, "type": "subscribe", "topic": topic})
    env.listeners.notify(topic)
    await asyncio.sleep(0.1)
    assert [m["type"] for m in connection.sent] == ["snapshot", "update"]
    for message in connection.sent:
        assert message["unavailable"] == "No database."
        assert_valid(wire(message))

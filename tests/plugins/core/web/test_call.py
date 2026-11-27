"""Command calls on the client socket: result shape, errors, view-only and timeout (#845)."""

import asyncio
import json
from typing import Any

import pytest
from websockets.asyncio.client import connect

from bastproxy.plugins.core.web.libs._call import CALL_TIMEOUT, Calls
from bastproxy.plugins.core.web.libs._http import HANDLER_TIMEOUT
from bastproxy.plugins.core.web.libs._server import WebApp, WebServer
from bastproxy.plugins.core.web.libs._store import PageStore, SessionStore
from bastproxy.plugins.core.web.libs._ws import SocketHub


class FakeConnection:
    def __init__(self, view_only: bool = False) -> None:
        self.sent: list[dict[str, Any]] = []
        self.view_only = view_only

    def send(self, message: dict[str, Any]) -> bool:
        self.sent.append(message)
        return True


class Env:
    def __init__(self) -> None:
        self.hub = SocketHub()
        self.runs: list[tuple[str, str]] = []
        self.reply: Any = {"ok": True, "reason": "", "lines": ["a@Rb", "c"], "data": {"n": 1}}
        self.calls = Calls(self.hub, self.runner, self.spans, timeout=0.05)

    def runner(self, command: str, arguments: str) -> Any:
        self.runs.append((command, arguments))
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply

    @staticmethod
    def spans(text: str) -> list[dict[str, Any]]:
        return [{"text": text}]

    async def send(self, connection: FakeConnection, **fields: Any) -> None:
        handler: Any = self.hub.handlers["call"]
        result = handler(connection, {"v": 1, "type": "call", **fields})
        if asyncio.iscoroutine(result):
            await result


@pytest.fixture
def env() -> Env:
    return Env()


async def test_a_call_answers_with_a_result(env: Env) -> None:
    connection = FakeConnection()
    await env.send(connection, id="1", command="core.web.status", args="-x")
    assert env.runs == [("core.web.status", "-x")]
    assert connection.sent == [
        {
            "v": 1,
            "type": "result",
            "id": "1",
            "ok": True,
            "reply": {"lines": [[{"text": "a@Rb"}], [{"text": "c"}]], "data": {"n": 1}},
        }
    ]


async def test_args_are_optional_and_an_integer_id_is_allowed(env: Env) -> None:
    connection = FakeConnection()
    await env.send(connection, id=7, command="core.web.status")
    assert env.runs == [("core.web.status", "")]
    assert connection.sent[0]["id"] == 7


async def test_a_list_of_args_is_joined(env: Env) -> None:
    await env.send(FakeConnection(), id="1", command="c", args=["a", "b c"])
    assert env.runs == [("c", "a 'b c'")]


async def test_the_reason_is_carried_when_not_ok(env: Env) -> None:
    env.reply = {"ok": False, "reason": "failed", "lines": [], "data": None}
    connection = FakeConnection()
    await env.send(connection, id="1", command="c")
    assert connection.sent[0]["ok"] is False
    assert connection.sent[0]["reason"] == "failed"
    assert connection.sent[0]["reply"] == {"lines": [], "data": None}


@pytest.mark.parametrize(
    "fields",
    [
        {"command": "c"},
        {"id": "", "command": "c"},
        {"id": "x" * 65, "command": "c"},
        {"id": True, "command": "c"},
        {"id": 1.5, "command": "c"},
        {"id": "1"},
        {"id": "1", "command": ""},
        {"id": "1", "command": 5},
        {"id": "1", "command": "c" * 300},
        {"id": "1", "command": "c", "args": 5},
        {"id": "1", "command": "c", "args": ["a", 1]},
    ],
)
async def test_a_malformed_call_is_a_bad_message(env: Env, fields: dict[str, Any]) -> None:
    connection = FakeConnection()
    await env.send(connection, **fields)
    assert env.runs == []
    assert [(m["type"], m["code"], m["for"]) for m in connection.sent] == [
        ("error", "bad_message", "call")
    ]


async def test_a_view_only_socket_is_refused(env: Env) -> None:
    connection = FakeConnection(view_only=True)
    await env.send(connection, id="1", command="c")
    assert env.runs == []
    assert [(m["type"], m["code"], m["for"], m["id"]) for m in connection.sent] == [
        ("error", "view_only", "call", "1")
    ]


async def test_a_slow_runner_answers_timeout(env: Env) -> None:
    async def slow(command: str, arguments: str) -> Any:
        await asyncio.sleep(1)

    env.calls._runner = slow
    connection = FakeConnection()
    await env.send(connection, id="1", command="c")
    assert connection.sent == [
        {
            "v": 1,
            "type": "result",
            "id": "1",
            "ok": False,
            "reason": "timeout",
            "reply": {"lines": [], "data": None},
        }
    ]


async def test_a_runner_exception_propagates_to_the_hub(env: Env) -> None:
    env.reply = RuntimeError("boom")
    with pytest.raises(RuntimeError):
        await env.send(FakeConnection(), id="1", command="c")


def test_the_call_timeout_is_below_the_handler_timeout() -> None:
    assert CALL_TIMEOUT < HANDLER_TIMEOUT


def test_close_unregisters(env: Env) -> None:
    env.calls.close()
    assert "call" not in env.hub.handlers


@pytest.mark.parametrize("view_only", [True, False])
async def test_a_call_on_a_real_session_socket(view_only: bool) -> None:
    """A socket opened on a real session: a view-only one is refused, a normal one runs."""
    sessions = SessionStore()
    server = WebServer()
    origin = ""
    app = WebApp(
        PageStore(),
        sessions=sessions,
        allowed_origins=lambda: [origin + "/"],
        proxy_version="9.9.9",
    )
    port = await server.start("127.0.0.1", 0, app, None)
    origin = f"http://127.0.0.1:{port}"
    runs: list[tuple[str, str]] = []

    def runner(command: str, arguments: str) -> Any:
        runs.append((command, arguments))
        return {"ok": True, "reason": "", "lines": ["hi"], "data": None}

    calls = Calls(server.sockets, runner, lambda text: [{"text": text}])
    sid = sessions.create(3600, view_only=view_only)
    try:
        async with await connect(
            f"ws://127.0.0.1:{port}/ws",
            origin=origin,  # type: ignore[arg-type]
            additional_headers={"Cookie": f"bpsession={sid}"},
            open_timeout=5,
        ) as conn:
            async with asyncio.timeout(5):
                assert json.loads(await conn.recv())["type"] == "hello"
                await conn.send(
                    json.dumps({"v": 1, "type": "call", "id": "7", "command": "demo.cmd"})
                )
                reply = json.loads(await conn.recv())
        if view_only:
            assert (reply["type"], reply["code"], reply["for"], reply["id"]) == (
                "error",
                "view_only",
                "call",
                "7",
            )
            assert runs == []
        else:
            assert (reply["type"], reply["id"], reply["ok"]) == ("result", "7", True)
            assert runs == [("demo.cmd", "")]
    finally:
        calls.close()
        server.close()
        await server.wait_closed()

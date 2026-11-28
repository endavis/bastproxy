"""Topic subscriptions: snapshot, debounced updates, errors and removal (#843)."""

import asyncio
from typing import Any

import pytest

from bastproxy.plugins.core.web.libs._store import ProviderListeners, RouteTable
from bastproxy.plugins.core.web.libs._subscribe import Subscriptions
from bastproxy.plugins.core.web.libs._ws import SocketHub

OWNER = "plugins.test.caller"
TOPIC = "test.caller.mobs"
DEBOUNCE = 0.02


class FakeConnection:
    """Stands in for a socket: records what is sent."""

    def __init__(self, accept: bool = True) -> None:
        self.subscriptions: set[str] = set()
        self.sent: list[dict[str, Any]] = []
        self._accept = accept

    def send(self, message: dict[str, Any]) -> bool:
        if self._accept:
            self.sent.append(message)
        return self._accept


class Env:
    def __init__(self) -> None:
        self.hub = SocketHub()
        self.routes = RouteTable()
        self.listeners = ProviderListeners()
        self.calls = 0
        self.data: Any = [["Orc", 5]]
        self.subs = Subscriptions(self.hub, lambda: self.routes, self.listeners, DEBOUNCE)
        self.routes.add_provider(OWNER, "mobs", self.snapshot, None, "json", None, str)

    def snapshot(self) -> Any:
        self.calls += 1
        if isinstance(self.data, Exception):
            raise self.data
        return self.data

    def connect(self, *, accept: bool = True) -> FakeConnection:
        connection = FakeConnection(accept)
        self.hub.add(connection)  # type: ignore[arg-type]  # reason: a stand-in socket
        return connection

    async def send(self, connection: FakeConnection, kind: str, **fields: Any) -> None:
        handler: Any = self.hub.handlers[kind]
        result = handler(connection, {"v": 1, "type": kind, **fields})
        if asyncio.iscoroutine(result):
            await result

    async def follow(self, connection: FakeConnection) -> None:
        await self.send(connection, "subscribe", topic=TOPIC)
        connection.sent.clear()

    @staticmethod
    async def settle() -> None:
        await asyncio.sleep(DEBOUNCE * 5)


@pytest.fixture
def env() -> Env:
    return Env()


async def test_subscribe_sends_a_snapshot_and_follows(env: Env) -> None:
    connection = env.connect()
    await env.send(connection, "subscribe", topic=TOPIC)
    assert connection.sent == [{"v": 1, "type": "snapshot", "topic": TOPIC, "data": [["Orc", 5]]}]
    assert connection.subscriptions == {TOPIC}


async def test_an_async_snapshot_is_awaited(env: Env) -> None:
    async def later() -> dict[str, int]:
        return {"a": 1}

    env.routes.add_provider(OWNER, "later", later, None, "json", None, str)
    connection = env.connect()
    await env.send(connection, "subscribe", topic="test.caller.later")
    assert connection.sent[0]["data"] == {"a": 1}


async def test_a_change_sends_an_update_with_the_full_snapshot(env: Env) -> None:
    connection = env.connect()
    await env.follow(connection)
    env.data = [["Elf", 9]]
    env.listeners.notify(TOPIC)
    await env.settle()
    assert connection.sent == [{"v": 1, "type": "update", "topic": TOPIC, "data": [["Elf", 9]]}]


async def test_a_burst_sends_one_update_and_one_snapshot_call(env: Env) -> None:
    first, second = env.connect(), env.connect()
    await env.follow(first)
    await env.follow(second)
    env.calls = 0
    for _ in range(10):
        env.listeners.notify(TOPIC)
    await env.settle()
    assert env.calls == 1
    assert [m["type"] for m in first.sent] == ["update"]
    assert [m["type"] for m in second.sent] == ["update"]


async def test_a_change_after_the_window_sends_another_update(env: Env) -> None:
    connection = env.connect()
    await env.follow(connection)
    env.listeners.notify(TOPIC)
    await env.settle()
    env.listeners.notify(TOPIC)
    await env.settle()
    assert [m["type"] for m in connection.sent] == ["update", "update"]


async def test_unsubscribe_stops_updates_and_is_idempotent(env: Env) -> None:
    connection = env.connect()
    await env.follow(connection)
    await env.send(connection, "unsubscribe", topic=TOPIC)
    await env.send(connection, "unsubscribe", topic=TOPIC)
    await env.send(connection, "unsubscribe", topic=5)
    env.listeners.notify(TOPIC)
    await env.settle()
    assert connection.sent == []
    assert connection.subscriptions == set()


async def test_changes_with_no_subscribers_do_nothing(env: Env) -> None:
    env.connect()
    env.listeners.notify(TOPIC)
    await env.settle()
    assert env.calls == 0
    assert env.subs._timers == {}


def test_changed_without_a_loop_does_not_raise(env: Env) -> None:
    env.subs.changed(TOPIC)
    connection = env.connect()
    connection.subscriptions.add(TOPIC)
    env.subs.changed(TOPIC)
    assert env.calls == 0
    assert env.subs._timers == {}


@pytest.mark.parametrize("topic", [None, "", 5, ["a"]])
async def test_a_bad_topic_is_a_bad_message(env: Env, topic: Any) -> None:
    connection = env.connect()
    await env.send(connection, "subscribe", topic=topic)
    assert connection.sent[0]["code"] == "bad_message"
    assert connection.sent[0]["for"] == "subscribe"
    assert connection.subscriptions == set()


async def test_an_unknown_topic_is_an_error_naming_it(env: Env) -> None:
    connection = env.connect()
    await env.send(connection, "subscribe", topic="test.caller.nope")
    error = connection.sent[0]
    assert (error["code"], error["topic"], error["for"]) == (
        "unknown_topic",
        "test.caller.nope",
        "subscribe",
    )
    assert connection.subscriptions == set()


async def test_a_raising_snapshot_on_subscribe_affects_only_that_topic(env: Env) -> None:
    env.routes.add_provider(OWNER, "good", lambda: 1, None, "json", None, str)
    connection = env.connect()
    await env.send(connection, "subscribe", topic="test.caller.good")
    connection.sent.clear()
    env.data = ValueError("boom")
    await env.send(connection, "subscribe", topic=TOPIC)
    assert [(m["code"], m["topic"], m["for"]) for m in connection.sent] == [
        ("snapshot_failed", TOPIC, "subscribe")
    ]
    assert connection.subscriptions == {"test.caller.good"}


async def test_a_raising_snapshot_on_update_keeps_the_subscription(env: Env) -> None:
    connection = env.connect()
    await env.follow(connection)
    env.data = ValueError("boom")
    env.listeners.notify(TOPIC)
    await env.settle()
    assert [(m["code"], m["topic"]) for m in connection.sent] == [("snapshot_failed", TOPIC)]
    assert connection.subscriptions == {TOPIC}
    connection.sent.clear()
    env.data = [["ok"]]
    env.listeners.notify(TOPIC)
    await env.settle()
    assert [m["type"] for m in connection.sent] == ["update"]


async def test_a_full_send_queue_does_not_subscribe(env: Env) -> None:
    connection = env.connect(accept=False)
    await env.send(connection, "subscribe", topic=TOPIC)
    assert connection.subscriptions == set()


async def test_removed_sends_topic_removed_and_leaves_no_timer(env: Env) -> None:
    connection = env.connect()
    await env.follow(connection)
    env.listeners.notify(TOPIC)
    assert env.subs._timers
    env.routes.remove(OWNER)
    env.subs.removed([TOPIC])
    assert env.subs._timers == {}
    assert [(m["type"], m["code"], m["topic"]) for m in connection.sent] == [
        ("error", "topic_removed", TOPIC)
    ]
    assert connection.subscriptions == set()
    await env.settle()
    assert len(connection.sent) == 1


async def test_a_flush_for_a_vanished_provider_sends_topic_removed(env: Env) -> None:
    connection = env.connect()
    await env.follow(connection)
    env.listeners.notify(TOPIC)
    env.routes.remove(OWNER)
    await env.settle()
    assert [m["code"] for m in connection.sent] == ["topic_removed"]


async def test_a_closed_socket_drops_its_subscription(env: Env) -> None:
    connection = env.connect()
    await env.follow(connection)
    env.hub.discard(connection)  # type: ignore[arg-type]  # reason: a stand-in socket
    env.listeners.notify(TOPIC)
    await env.settle()
    assert connection.sent == []
    assert env.calls == 1  # the subscribe snapshot only


async def test_close_cancels_timers_and_detaches(env: Env) -> None:
    connection = env.connect()
    await env.follow(connection)
    env.listeners.notify(TOPIC)
    env.subs.close()
    assert env.subs._timers == {}
    assert "subscribe" not in env.hub.handlers
    assert "unsubscribe" not in env.hub.handlers
    env.listeners.notify(TOPIC)
    await env.settle()
    assert connection.sent == []


class TableEnv(Env):
    """An Env with a table provider alongside the json one (#876)."""

    def __init__(self) -> None:
        super().__init__()
        self.routes.add_provider(
            OWNER, "grid", self.snapshot, [{"name": "a", "label": "A"}], "table", None, str
        )


TABLE_TOPIC = "test.caller.grid"


async def test_an_unavailable_table_sends_null_data_and_the_message() -> None:
    env = TableEnv()
    env.data = {"unavailable": "No database."}
    connection = env.connect()
    await env.send(connection, "subscribe", topic=TABLE_TOPIC)
    assert connection.sent == [
        {
            "v": 1,
            "type": "snapshot",
            "topic": TABLE_TOPIC,
            "data": None,
            "unavailable": "No database.",
        }
    ]
    connection.sent.clear()
    env.data = {"unavailable": "Still gone."}
    env.listeners.notify(TABLE_TOPIC)
    await env.settle()
    assert connection.sent == [
        {"v": 1, "type": "update", "topic": TABLE_TOPIC, "data": None, "unavailable": "Still gone."}
    ]
    connection.sent.clear()
    env.data = {"rows": [["x"]]}
    env.listeners.notify(TABLE_TOPIC)
    await env.settle()
    assert connection.sent == [
        {"v": 1, "type": "update", "topic": TABLE_TOPIC, "data": {"rows": [["x"]]}}
    ]


async def test_a_malformed_table_mapping_is_snapshot_failed() -> None:
    env = TableEnv()
    env.data = {"bogus": 1}
    connection = env.connect()
    await env.send(connection, "subscribe", topic=TABLE_TOPIC)
    assert connection.sent[0]["code"] == "snapshot_failed"
    assert connection.subscriptions == set()


async def test_a_json_provider_with_an_unavailable_key_is_unchanged(env: Env) -> None:
    env.data = {"unavailable": "m"}
    connection = env.connect()
    await env.send(connection, "subscribe", topic=TOPIC)
    assert connection.sent == [
        {"v": 1, "type": "snapshot", "topic": TOPIC, "data": {"unavailable": "m"}}
    ]

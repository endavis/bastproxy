"""The web plugin's provider api, events and status (#840)."""

import asyncio
import json
import logging
from typing import Any

import pytest

from bastproxy.plugins.core.web.plugin._web import WebPlugin

from .test_web_plugin import status_text
from .test_web_plugin import stub as stub  # reason: reuse the fixture
from .test_web_routes_plugin import _login_sid, _open_socket

OWNER = "plugins.test.caller"
EVENT = "ev_mobs_changed"


def snap() -> list[list[Any]]:
    return [["Orc", 5]]


def add(stub: Any, name: str = "mobs", owner: str = OWNER, **kwargs: Any) -> str | None:
    result: str | None = WebPlugin._api_web_provider_add(stub, owner, name, snap, **kwargs)
    return result


def registered(stub: Any, what: str) -> list[str]:
    return [args[0] for name, args, _ in stub.calls if name.endswith(f"event.{what}")]


def test_a_provider_is_added_and_listed_sorted(stub: Any) -> None:
    assert add(stub, "zeta") == "test.caller.zeta"
    assert add(stub, "alpha") == "test.caller.alpha"
    assert WebPlugin._api_web_provider_list(stub) == ["test.caller.alpha", "test.caller.zeta"]


def test_the_owner_must_be_the_caller(stub: Any, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR):
        assert add(stub, owner="plugins.other.plugin") is None
    assert WebPlugin._api_web_provider_list(stub) == []
    assert any("not the calling plugin" in r.getMessage() for r in caplog.records)


def test_an_invalid_provider_is_refused_and_logged(
    stub: Any, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR):
        assert add(stub, kind="table") is None
    assert any("web provider 'mobs' refused" in r.getMessage() for r in caplog.records)
    assert registered(stub, "register") == []


def test_changed_notifies_listeners_for_the_owner_only(
    stub: Any, caplog: pytest.LogCaptureFixture
) -> None:
    seen: list[str] = []
    stub.provider_listeners.add(seen.append)
    add(stub)
    assert WebPlugin._api_web_provider_changed_raise(stub, OWNER, "mobs") is True
    assert seen == ["test.caller.mobs"]
    with caplog.at_level(logging.ERROR):
        assert WebPlugin._api_web_provider_changed_raise(stub, OWNER, "unknown") is False
        stub.caller = "plugins.other.plugin"
        assert WebPlugin._api_web_provider_changed_raise(stub, OWNER, "mobs") is False
    assert seen == ["test.caller.mobs"]
    assert len([r for r in caplog.records if "changed refused" in r.getMessage()]) == 2


def test_the_event_is_registered_once_and_fires_to_listeners(stub: Any) -> None:
    seen: list[str] = []
    stub.provider_listeners.add(seen.append)
    add(stub, "a", event=EVENT)
    add(stub, "b", event=EVENT)
    add(stub, "c")
    assert registered(stub, "register") == [EVENT]
    stub.current_event = EVENT
    WebPlugin._provider_event_fired(stub)
    assert seen == ["test.caller.a", "test.caller.b"]
    stub.current_event = "ev_other"
    WebPlugin._provider_event_fired(stub)
    assert len(seen) == 2


def test_replacing_a_provider_moves_its_event(stub: Any) -> None:
    add(stub, event=EVENT)
    add(stub, event="ev_next")
    assert registered(stub, "register") == [EVENT, "ev_next"]
    assert registered(stub, "unregister") == [EVENT]


def test_unload_removes_providers_and_unregisters_events(stub: Any) -> None:
    add(stub, event=EVENT)
    stub.unloaded = OWNER
    WebPlugin._eventcb_plugin_unloaded(stub)
    assert WebPlugin._api_web_provider_list(stub) == []
    assert registered(stub, "unregister") == [EVENT]


def test_route_remove_also_removes_providers(stub: Any) -> None:
    add(stub, event=EVENT)
    assert WebPlugin._api_web_route_remove(stub, OWNER) == 1
    assert registered(stub, "unregister") == [EVENT]


def test_after_load_registers_the_events_a_reload_carried_over(stub: Any) -> None:
    stub.routes.add_provider(OWNER, "mobs", snap, None, "json", EVENT, str)
    WebPlugin._phook_sync_provider_events(stub)
    assert registered(stub, "register") == [EVENT]


def test_status_counts_providers_apart_from_routes(stub: Any) -> None:
    add(stub, event=EVENT)
    text = status_text(stub)
    assert "Routes        : 0" in text
    assert "Providers     : 1 - test.caller.mobs" in text


def test_status_shows_the_path_of_each_provider(stub: Any) -> None:
    add(stub, event=EVENT)
    assert "test.caller.mobs (/data/test/caller/mobs)" in status_text(stub)


async def _socket(stub: Any) -> Any:
    await stub._restart(0)
    stub.settings["publicurl"] = f"http://127.0.0.1:{stub.port}"
    sid = await _login_sid(stub)
    return await _open_socket(stub, sid, f"http://127.0.0.1:{stub.port}")


async def _recv(conn: Any) -> dict[str, Any]:
    async with asyncio.timeout(5):
        message: dict[str, Any] = json.loads(await conn.recv())
    return message


async def _send(conn: Any, kind: str, **fields: Any) -> None:
    await conn.send(json.dumps({"v": 1, "type": kind, **fields}))


async def test_hello_lists_the_topics_and_changed_raise_sends_an_update(stub: Any) -> None:
    add(stub, "alpha")
    add(stub, "mobs")
    conn = await _socket(stub)
    assert (await _recv(conn))["topics"] == ["test.caller.alpha", "test.caller.mobs"]
    await _send(conn, "subscribe", topic="test.caller.mobs")
    snapshot = await _recv(conn)
    assert (snapshot["type"], snapshot["topic"], snapshot["data"]) == (
        "snapshot",
        "test.caller.mobs",
        [["Orc", 5]],
    )
    WebPlugin._api_web_provider_changed_raise(stub, OWNER, "mobs")
    update = await _recv(conn)
    assert (update["type"], update["topic"]) == ("update", "test.caller.mobs")
    await conn.close()


async def test_unload_and_route_remove_send_topic_removed(stub: Any) -> None:
    add(stub, "mobs")
    add(stub, "other")
    conn = await _socket(stub)
    await _recv(conn)
    for topic in ("test.caller.mobs", "test.caller.other"):
        await _send(conn, "subscribe", topic=topic)
        await _recv(conn)
    stub.unloaded = OWNER
    WebPlugin._eventcb_plugin_unloaded(stub)
    removed = {(await _recv(conn))["topic"] for _ in range(2)}
    assert removed == {"test.caller.mobs", "test.caller.other"}
    add(stub, "again")
    await _send(conn, "subscribe", topic="test.caller.again")
    await _recv(conn)
    assert WebPlugin._api_web_route_remove(stub, OWNER) == 1
    error = await _recv(conn)
    assert (error["type"], error["code"], error["topic"]) == (
        "error",
        "topic_removed",
        "test.caller.again",
    )
    await conn.close()

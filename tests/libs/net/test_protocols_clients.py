"""Tests for GMCP and MSDP on the client links (#59, ADR-0001).

These drive real telnetlib3 negotiation: a ``MudTelnetClient`` talks to a scripted MUD, and
scripted clients talk to the proxy's own ``create_server``. A simulated login (see
``ProxyServer.login``) stands in for the clients plugin.
"""

import asyncio
import collections
import json
import logging
import re
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any
from unittest.mock import MagicMock

import pytest
from telnetlib3 import open_connection
from telnetlib3.mud import gmcp_encode, msdp_decode
from telnetlib3.telopt import DO, DONT, GMCP, IAC, MCCP2_COMPRESS, MSDP, SB, SE, WILL

from bastproxy.libs.net import client as client_mod
from bastproxy.libs.net import oob
from bastproxy.libs.net.client import ClientConnection, unregister_client
from bastproxy.libs.net.mud import MudTelnetClient
from bastproxy.libs.net.negotiation import RecordingTelnetWriter
from bastproxy.libs.net.protocols import PROTOCOLS
from bastproxy.libs.records import RMANAGER
from bastproxy.libs.records.enums import Direction
from tests.libs.net.clients import (
    ProxyServer,
    ScriptedClient,
    ScriptedMud,
    proxy_server,
    sb_frame,
    scripted_mud,
    wait_until,
)

TIMEOUT = 5
BOTH = {GMCP, MSDP}


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Give each test empty records and a clean manager."""
    monkeypatch.setattr(RMANAGER, "record_instances", {})
    monkeypatch.setattr(RMANAGER, "records", {})
    PROTOCOLS.mud_disconnected()
    PROTOCOLS._owner_modules.clear()
    yield
    PROTOCOLS.mud_disconnected()
    PROTOCOLS._owner_modules.clear()


def _records(kind: str) -> list[Any]:
    return list(RMANAGER.records.get(kind, {}).values())


def _sent_to(link: str) -> list[Any]:
    return [
        r
        for r in _records("TelnetProtocolMessage")
        if r.link == link and str(r.direction) == "sent"
    ]


def gmcp_seen(client: ScriptedClient) -> list[tuple[str, Any]]:
    """The GMCP messages a scripted client received, as ``(package, data)``."""
    out: list[tuple[str, Any]] = []
    for opt, payload in client.subnegotiations:
        if opt == GMCP:
            package, _, body = payload.decode().partition(" ")
            out.append((package, json.loads(body) if body else None))
    return out


def msdp_seen(client: ScriptedClient) -> list[dict[str, Any]]:
    """The MSDP messages a scripted client received."""
    return [msdp_decode(payload) for opt, payload in client.subnegotiations if opt == MSDP]


def supports_sent(mud: ScriptedMud) -> list[list[str]]:
    """Every ``Core.Supports.Set`` list the MUD received, in order."""
    return [
        json.loads(m.group(1))
        for m in re.finditer(rb"Core\.Supports\.Set (\[[^\]]*\])", bytes(mud.received))
    ]


async def settle() -> None:
    """Let in-flight bytes arrive when a test asserts that nothing happened."""
    await asyncio.sleep(0.3)


@asynccontextmanager
async def mud_link() -> AsyncIterator[tuple[ScriptedMud, Callable[[bytes], None], Any]]:
    """A ``MudTelnetClient`` linked to a scripted MUD that offers GMCP and MSDP.

    Yields the MUD, a function that makes the MUD write bytes, and the proxy's MUD writer.
    """
    frames: asyncio.Queue[bytes | None] = asyncio.Queue()

    async def script(mud: ScriptedMud, writer: asyncio.StreamWriter) -> None:
        writer.write(IAC + WILL + GMCP + IAC + WILL + MSDP)
        await writer.drain()
        await mud.wait_for(lambda: b"Core.Hello" in mud.received)
        while (frame := await frames.get()) is not None:
            writer.write(frame)
            await writer.drain()

    async with scripted_mud(script) as mud:
        _reader, writer = await asyncio.wait_for(
            open_connection(
                "127.0.0.1",
                mud.port,
                client_factory=MudTelnetClient,
                compression=False,
                connect_maxwait=0.5,
                encoding="utf8",
            ),
            TIMEOUT,
        )
        PROTOCOLS.mud_connected(writer)
        await mud.wait_for(lambda: b"Core.Hello" in mud.received)
        try:
            yield mud, frames.put_nowait, writer
        finally:
            frames.put_nowait(None)
            writer.close()
            PROTOCOLS.mud_disconnected()


@asynccontextmanager
async def world() -> AsyncIterator[tuple[ProxyServer, ScriptedMud, Callable[[bytes], None], Any]]:
    """A proxy server with real ``ClientConnection`` objects, linked to a scripted MUD."""
    async with mud_link() as (mud, push, writer), proxy_server(connections=True) as proxy:
        yield proxy, mud, push, writer


async def join(
    stack: AsyncExitStack,
    proxy: ProxyServer,
    agree: set[bytes],
    modules: list[str] | None = None,
    login: str | None = None,
) -> tuple[ScriptedClient, ClientConnection]:
    """Connect a scripted client, optionally send its Core.Supports, optionally log it in."""
    client = await proxy.connect(agree)
    stack.push_async_callback(client.close)
    index = len(proxy.connections) - 1
    conn = proxy.connections[index]
    if modules is not None:
        client.gmcp("Core.Supports.Set", modules)
        if GMCP in agree:  # a client that refused has its messages dropped
            await wait_until(lambda: conn.gmcp_modules == oob.parse_supports(modules))
    if login is not None:
        proxy.login(index, view_only=login == "view")
    return client, conn


# the offer and the flags ---------------------------------------------------------------


async def test_the_server_offers_gmcp_and_msdp_and_the_flags_follow_the_answer() -> None:
    async with proxy_server(connections=True) as proxy, AsyncExitStack() as stack:
        accepts, accepting = await join(stack, proxy, BOTH)
        refuses, refusing = await join(stack, proxy, set())
        for client in (accepts, refuses):
            assert (WILL, GMCP) in client.commands
            assert (WILL, MSDP) in client.commands
        assert accepting.gmcp_enabled and accepting.msdp_enabled
        assert not refusing.gmcp_enabled and not refusing.msdp_enabled


async def test_option_callback_fires_once_per_change() -> None:
    async with proxy_server(connections=True) as proxy, AsyncExitStack() as stack:
        calls: list[tuple[bytes, bool]] = []
        client, conn = await join(stack, proxy, set())
        writer: Any = conn.writer
        writer.oob_option_callback = lambda opt, enabled: calls.append((opt, enabled))
        client.send(IAC + DO + GMCP + IAC + DO + GMCP)
        await wait_until(lambda: len(calls) >= 1)
        await settle()
        assert calls == [(GMCP, True)]
        client.send(IAC + DONT + GMCP + IAC + DONT + GMCP)
        await wait_until(lambda: len(calls) >= 2)
        await settle()
        assert calls == [(GMCP, True), (GMCP, False)]


# who receives what ---------------------------------------------------------------------


async def test_mud_data_reaches_the_client_that_accepted_and_not_the_one_that_refused() -> None:
    async with world() as (proxy, _mud, push, _w), AsyncExitStack() as stack:
        a, conn_a = await join(stack, proxy, BOTH, ["Char 1"], login="full")
        b, _conn_b = await join(stack, proxy, set(), ["Char 1"], login="full")
        push(ScriptedMud.gmcp_frame("Char.Vitals", {"hp": 5}))
        push(ScriptedMud.msdp_frame({"HEALTH": "5"}))
        await a.wait_for(lambda: bool(gmcp_seen(a) and msdp_seen(a)))
        await settle()
        assert gmcp_seen(a) == [("Char.Vitals", {"hp": 5})]
        assert msdp_seen(a) == [{"HEALTH": "5"}]
        assert gmcp_seen(b) == [] and msdp_seen(b) == []
        sent = _sent_to(conn_a.uuid)
        assert sorted((r.protocol, r.package) for r in sent) == [
            ("GMCP", "Char.Vitals"),
            ("MSDP", "HEALTH"),
        ]


async def test_a_client_that_is_not_logged_in_gets_nothing() -> None:
    async with world() as (proxy, _mud, push, _w), AsyncExitStack() as stack:
        a, _ = await join(stack, proxy, BOTH, ["Char 1"])
        push(ScriptedMud.gmcp_frame("Char.Vitals", {"hp": 5}))
        push(ScriptedMud.msdp_frame({"HEALTH": "5"}))
        await wait_until(lambda: PROTOCOLS.api("libs.net.protocols:msdp.cache.get")("HEALTH"))
        await settle()
        assert gmcp_seen(a) == [] and msdp_seen(a) == []


async def test_a_view_only_client_receives_data() -> None:
    async with world() as (proxy, _mud, push, _w), AsyncExitStack() as stack:
        a, _ = await join(stack, proxy, BOTH, ["Char 1"], login="view")
        push(ScriptedMud.gmcp_frame("Char.Vitals", {"hp": 5}))
        await a.wait_for(lambda: bool(gmcp_seen(a)))


async def test_live_gmcp_is_filtered_by_each_clients_core_supports() -> None:
    async with world() as (proxy, _mud, push, _w), AsyncExitStack() as stack:
        a, _ = await join(stack, proxy, BOTH, ["Char 1"], login="full")
        b, _ = await join(stack, proxy, BOTH, ["Room 1"], login="full")
        c, _ = await join(stack, proxy, BOTH, None, login="full")
        push(ScriptedMud.gmcp_frame("Char.Vitals", {"hp": 1}))
        push(ScriptedMud.gmcp_frame("Character.Other", {"x": 1}))
        push(ScriptedMud.gmcp_frame("Room.Info", {"num": 2}))
        push(ScriptedMud.msdp_frame({"HEALTH": "1"}))
        await a.wait_for(lambda: bool(gmcp_seen(a) and gmcp_seen(b) and msdp_seen(c)))
        await settle()
        assert gmcp_seen(a) == [("Char.Vitals", {"hp": 1})]
        assert gmcp_seen(b) == [("Room.Info", {"num": 2})]
        assert gmcp_seen(c) == []
        # MSDP is not filtered by modules
        assert all(msdp_seen(x) == [{"HEALTH": "1"}] for x in (a, b, c))


# replay --------------------------------------------------------------------------------


async def test_a_client_that_logs_in_late_gets_the_cached_values() -> None:
    async with world() as (proxy, _mud, push, _w), AsyncExitStack() as stack:
        early, _ = await join(stack, proxy, BOTH, ["Char 1"], login="full")
        push(ScriptedMud.gmcp_frame("Char.Vitals", {"hp": 9}))
        push(ScriptedMud.msdp_frame({"HEALTH": "9"}))
        await early.wait_for(lambda: bool(gmcp_seen(early) and msdp_seen(early)))
        late, _ = await join(stack, proxy, BOTH, ["Char 1"])
        await settle()
        assert gmcp_seen(late) == []  # not logged in yet
        proxy.login(1)
        await late.wait_for(lambda: bool(gmcp_seen(late) and msdp_seen(late)))
        assert gmcp_seen(late) == [("Char.Vitals", {"hp": 9})]
        assert msdp_seen(late) == [{"HEALTH": "9"}]


async def test_a_client_that_enables_msdp_after_login_gets_the_replay_then() -> None:
    async with world() as (proxy, _mud, push, _w), AsyncExitStack() as stack:
        push(ScriptedMud.msdp_frame({"HEALTH": "3"}))
        late, _ = await join(stack, proxy, set(), login="full")
        await wait_until(lambda: PROTOCOLS.api("libs.net.protocols:msdp.cache.get")("HEALTH"))
        await settle()
        assert msdp_seen(late) == []
        late.send(IAC + DO + MSDP)
        await late.wait_for(lambda: bool(msdp_seen(late)))
        assert msdp_seen(late) == [{"HEALTH": "3"}]


async def test_a_client_that_enables_gmcp_after_login_gets_the_replay_once_it_says_what_it_wants() -> (
    None
):
    async with world() as (proxy, _mud, push, _w), AsyncExitStack() as stack:
        push(ScriptedMud.gmcp_frame("Char.Vitals", {"hp": 4}))
        late, _ = await join(stack, proxy, set(), login="full")
        await wait_until(lambda: PROTOCOLS.api("libs.net.protocols:gmcp.cache.get")("Char.Vitals"))
        late.send(IAC + DO + GMCP)
        late.gmcp("Core.Supports.Set", ["Char 1"])
        await late.wait_for(lambda: bool(gmcp_seen(late)))
        assert gmcp_seen(late) == [("Char.Vitals", {"hp": 4})]
        # adding a module later replays only what that module brings
        push(ScriptedMud.gmcp_frame("Room.Info", {"num": 1}))
        await wait_until(lambda: PROTOCOLS.api("libs.net.protocols:gmcp.cache.get")("Room.Info"))
        late.gmcp("Core.Supports.Add", ["Room 1"])
        await late.wait_for(lambda: len(gmcp_seen(late)) == 2)
        await settle()
        assert gmcp_seen(late) == [("Char.Vitals", {"hp": 4}), ("Room.Info", {"num": 1})]


# messages that arrive before the connection exists ----------------------------------------


async def test_core_supports_sent_right_behind_do_gmcp_is_kept_for_login() -> None:
    sb = sb_frame(GMCP, gmcp_encode("Core.Supports.Set", ["Char 1", "Logged 1"]))
    async with world() as (proxy, mud, push, _w), AsyncExitStack() as stack:
        push(ScriptedMud.gmcp_frame("Logged.In", {"name": "x"}))
        push(ScriptedMud.gmcp_frame("Room.Info", {"num": 1}))
        await wait_until(lambda: PROTOCOLS.api("libs.net.protocols:gmcp.cache.get")("Room.Info"))
        client = await proxy.connect(BOTH, {GMCP: sb})
        stack.push_async_callback(client.close)
        conn = proxy.connections[0]
        assert conn.gmcp_modules == {"char": 1, "logged": 1}
        writer: Any = proxy.connections[0].writer
        assert not writer.pending_oob
        proxy.login(0)
        await client.wait_for(lambda: bool(gmcp_seen(client)))
        await settle()
        assert gmcp_seen(client) == [("Logged.In", {"name": "x"})]  # not Room.Info
        await wait_until(lambda: supports_sent(mud) == [["char 1", "logged 1"]])


def test_pending_messages_are_bounded() -> None:
    writer = object.__new__(RecordingTelnetWriter)
    writer.pending_oob = collections.deque()
    queue = writer._make_pending_callback(GMCP)
    for i in range(RecordingTelnetWriter.OOB_PENDING_MAX + 5):
        queue("Pkg", i)
    assert len(writer.pending_oob) == RecordingTelnetWriter.OOB_PENDING_MAX


# the Core.Supports union ---------------------------------------------------------------


async def test_client_modules_join_the_union_and_the_union_shrinks_on_leave_and_dont() -> None:
    async with world() as (proxy, mud, _push, _w), AsyncExitStack() as stack:
        PROTOCOLS.api("libs.net.protocols:gmcp.modules.add")(["Base 1"], owner_id="plugin.test")
        await wait_until(lambda: supports_sent(mud) == [["base 1"]])
        # a client that is not logged in contributes nothing
        await join(stack, proxy, BOTH, ["Zed 1"])
        await settle()
        assert supports_sent(mud) == [["base 1"]]
        a, conn_a = await join(stack, proxy, BOTH, ["Char 1"], login="full")
        await wait_until(lambda: len(supports_sent(mud)) == 2)
        assert supports_sent(mud)[-1] == ["base 1", "char 1"]
        # adding a module changes the union; the highest version wins
        a.gmcp("Core.Supports.Add", ["Room 2", "Char 3"])
        await wait_until(lambda: len(supports_sent(mud)) == 3)
        assert supports_sent(mud)[-1] == ["base 1", "char 3", "room 2"]
        # the same list again sends nothing
        a.gmcp("Core.Supports.Set", ["Room 2", "Char 3"])
        await settle()
        assert len(supports_sent(mud)) == 3
        b, _conn_b = await join(stack, proxy, BOTH, ["Zed 1"], login="full")
        await wait_until(lambda: len(supports_sent(mud)) == 4)
        assert supports_sent(mud)[-1] == ["base 1", "char 3", "room 2", "zed 1"]
        # DONT GMCP removes a client's modules from the union
        b.send(IAC + DONT + GMCP)
        await wait_until(lambda: len(supports_sent(mud)) == 5)
        assert supports_sent(mud)[-1] == ["base 1", "char 3", "room 2"]
        # so does the client going away
        proxy.logout(1)
        await wait_until(lambda: len(supports_sent(mud)) == 6)
        assert supports_sent(mud)[-1] == ["base 1"]
        assert conn_a.gmcp_modules  # the client keeps its own list; only the union changed


async def test_the_last_client_leaving_sends_an_empty_set() -> None:
    async with world() as (proxy, mud, _push, _w), AsyncExitStack() as stack:
        await join(stack, proxy, BOTH, ["Char 1"], login="full")
        await wait_until(lambda: supports_sent(mud) == [["char 1"]])
        proxy.logout(0)
        await wait_until(lambda: supports_sent(mud) == [["char 1"], []])


async def test_a_client_core_supports_add_is_bounded() -> None:
    async with proxy_server(connections=True) as proxy, AsyncExitStack() as stack:
        client, conn = await join(stack, proxy, BOTH, [f"M{i} 1" for i in range(60)])
        client.gmcp("Core.Supports.Add", [f"N{i} 1" for i in range(60)])
        await wait_until(lambda: len(conn.gmcp_modules) == oob.CLIENT_MAX_MODULES)
        await settle()
        assert len(conn.gmcp_modules) == oob.CLIENT_MAX_MODULES


# client to MUD -------------------------------------------------------------------------


async def test_client_core_messages_are_not_forwarded_to_the_mud() -> None:
    async with world() as (proxy, mud, _push, _w), AsyncExitStack() as stack:
        a, _ = await join(stack, proxy, BOTH, None, login="full")
        a.gmcp("Core.Hello", {"client": "tintin-test", "version": "1"})
        a.gmcp("Core.KeepAlive")
        a.gmcp("Core.Supports.Set", ["Char 1"])
        a.gmcp("Test.Marker", {"n": 1})
        await mud.wait_for(lambda: b"Test.Marker" in mud.received)
        assert b"tintin-test" not in mud.received
        assert b"Core.KeepAlive" not in mud.received
        assert mud.received.count(b"Core.Hello") == 1  # the proxy's own
        # Core.Supports reached the MUD only as the proxy's union
        assert supports_sent(mud) == [["char 1"]]


async def test_gmcp_forwarding_needs_a_logged_in_client_that_is_not_view_only() -> None:
    async with world() as (proxy, mud, _push, _w), AsyncExitStack() as stack:
        full, _ = await join(stack, proxy, BOTH, None, login="full")
        view, _ = await join(stack, proxy, BOTH, None, login="view")
        anon, _ = await join(stack, proxy, BOTH, None)
        anon.gmcp("Test.Anon", {"n": 1})
        view.gmcp("Test.View", {"n": 2})
        view.gmcp("Core.Ping")
        await view.wait_for(lambda: bool(gmcp_seen(view)))
        await settle()
        assert b"Test.Anon" not in mud.received and b"Test.View" not in mud.received
        full.gmcp("Test.Full", {"n": 3})
        await mud.wait_for(lambda: b"Test.Full" in mud.received)
        assert b"Test.Anon" not in mud.received and b"Test.View" not in mud.received


async def test_msdp_forwarding_allows_list_send_report_only() -> None:
    async with world() as (proxy, mud, _push, _w), AsyncExitStack() as stack:
        full, _ = await join(stack, proxy, BOTH, None, login="full")
        view, _ = await join(stack, proxy, BOTH, None, login="view")
        view.msdp({"REPORT": "HEALTH"})
        full.msdp({"RESET": "REPORTABLE_VARIABLES"})
        full.msdp({"UNREPORT": "HEALTH"})
        full.msdp({"SEND": "ROOM"})
        await mud.wait_for(lambda: b"SEND" in mud.received)
        await settle()
        assert b"RESET" not in mud.received and b"UNREPORT" not in mud.received
        assert b"HEALTH" not in mud.received  # the view-only REPORT was blocked
        full.msdp({"REPORT": "HEALTH", "RESET": "X"})
        full.msdp({"LIST": "COMMANDS"})
        await mud.wait_for(lambda: b"LIST" in mud.received)
        assert b"REPORT" in mud.received and b"HEALTH" in mud.received
        assert b"RESET" not in mud.received


async def test_core_ping_is_answered_on_that_link_only() -> None:
    async with world() as (proxy, _mud, _push, _w), AsyncExitStack() as stack:
        a, conn_a = await join(stack, proxy, BOTH, None, login="full")
        b, _ = await join(stack, proxy, BOTH, None, login="full")
        a.gmcp("Core.Ping")
        await a.wait_for(lambda: bool(gmcp_seen(a)))
        await settle()
        assert gmcp_seen(a) == [("Core.Ping", None)]
        assert gmcp_seen(b) == []
        assert [r.package for r in _sent_to(conn_a.uuid)] == ["Core.Ping"]


async def test_gmcp_travels_inside_mccp2_for_a_client_that_has_both() -> None:
    async with world() as (proxy, _mud, push, _w), AsyncExitStack() as stack:
        a, conn = await join(stack, proxy, BOTH | {MCCP2_COMPRESS}, ["Char 1"], login="full")
        assert conn.mccp2_active
        push(ScriptedMud.gmcp_frame("Char.Vitals", {"hp": 8}))
        push(ScriptedMud.msdp_frame({"HEALTH": "8"}))
        await a.wait_for(lambda: bool(gmcp_seen(a) and msdp_seen(a)))
        assert a.mccp2_starts == 1
        assert gmcp_seen(a) == [("Char.Vitals", {"hp": 8})]
        assert msdp_seen(a) == [{"HEALTH": "8"}]
        assert b"Char.Vitals" not in a.raw  # only the compressed stream carried it


# redaction -----------------------------------------------------------------------------

SECRET = "pw-9f3a1c"


async def test_char_login_is_forwarded_but_never_stored_or_logged_verbatim(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    async with world() as (proxy, mud, _push, _w), AsyncExitStack() as stack:
        full, _ = await join(stack, proxy, BOTH, None, login="full")
        anon, _ = await join(stack, proxy, BOTH, None)
        anon.gmcp("Char.Login", {"name": "anon", "password": SECRET})
        full.gmcp("char.login.credentials", {"account": "x", "password": SECRET})
        full.gmcp("Char.Login", {"name": "x", "password": SECRET})
        await mud.wait_for(lambda: mud.received.count(SECRET.encode()) == 2)
        await settle()

    messages = [r for r in _records("TelnetProtocolMessage") if "login" in r.package.lower()]
    assert messages
    assert {r.data for r in messages} == {"<redacted>"}
    assert {(r.link == "mud", str(r.direction)) for r in messages} >= {(True, "sent")}
    negotiations = [r for r in _records("TelnetNegotiation") if r.command == "SB"]
    login_sbs = [r for r in negotiations if b"ogin" in r.data]
    assert len(login_sbs) >= 3  # anon (dropped), full twice; plus the copies sent to the mud
    for record in negotiations:
        assert SECRET.encode() not in record.data
        assert SECRET.encode() not in record.raw
    assert SECRET not in caplog.text


def test_redact_gmcp_payload_keeps_other_packages() -> None:
    assert oob.redact_gmcp_payload(b'Char.Vitals {"hp": 1}') == b'Char.Vitals {"hp": 1}'
    assert oob.redact_gmcp_payload(b'Char.Login {"password": "x"}') == b"Char.Login <redacted>"
    assert oob.redact_gmcp_payload(b"Char.Login") == b"Char.Login <redacted>"
    assert not oob.is_credential_package("Char.Loginx")


def test_recorded_sb_for_a_login_keeps_valid_framing() -> None:
    writer = object.__new__(RecordingTelnetWriter)
    writer.link_id = "link-x"
    writer._record(
        Direction.RECEIVED,
        "SB",
        GMCP,
        b'Char.Login {"password": "p"}',
        b"raw",
    )
    [record] = _records("TelnetNegotiation")
    assert record.data == b"Char.Login <redacted>"
    assert record.raw == IAC + SB + GMCP + b"Char.Login <redacted>" + IAC + SE


# ClientConnection wiring ---------------------------------------------------------------


def _conn_with_fakes(monkeypatch: pytest.MonkeyPatch) -> tuple[ClientConnection, list[str]]:
    calls: list[str] = []
    values = {
        "plugins.core.proxy:ssc.proxypw.get": "pw",
        "plugins.core.proxy:ssc.proxypwview.get": "view",
    }
    api = MagicMock(side_effect=lambda name: lambda *a, **k: values.get(name))
    monkeypatch.setattr(client_mod, "API", lambda owner_id: api)
    monkeypatch.setattr(client_mod, "SendDataDirectlyToClient", lambda *a, **k: lambda: None)
    monkeypatch.setattr(PROTOCOLS, "client_ready", lambda conn: calls.append("ready"))
    monkeypatch.setattr(PROTOCOLS, "client_gone", lambda conn: calls.append("gone"))
    writer = MagicMock()
    writer.protocol = None
    conn = ClientConnection("h", "1", "telnet", MagicMock(), writer)
    return conn, calls


def test_each_successful_login_branch_tells_the_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    conn, calls = _conn_with_fakes(monkeypatch)
    conn.process_data_from_not_logged_in_client("pw\r\n")
    assert calls == ["ready"]
    conn.process_data_from_not_logged_in_client("view\r\n")
    assert calls == ["ready", "ready"]
    conn.process_data_from_not_logged_in_client("wrong\r\n")
    assert calls == ["ready", "ready"]


def test_a_failing_manager_does_not_break_login(monkeypatch: pytest.MonkeyPatch) -> None:
    conn, _ = _conn_with_fakes(monkeypatch)

    def boom(_conn: Any) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(PROTOCOLS, "client_ready", boom)
    conn.process_data_from_not_logged_in_client("pw\r\n")  # does not raise


async def test_unregister_tells_the_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    conn, calls = _conn_with_fakes(monkeypatch)
    await unregister_client(conn)
    assert calls == ["gone"]


def test_the_writer_is_wired_to_the_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    conn, _ = _conn_with_fakes(monkeypatch)
    seen: list[Any] = []
    monkeypatch.setattr(PROTOCOLS, "client_option_changed", lambda *a: seen.append(a))
    monkeypatch.setattr(PROTOCOLS, "on_client_gmcp", lambda *a: seen.append(a))
    monkeypatch.setattr(PROTOCOLS, "on_client_msdp", lambda *a: seen.append(a))
    writer: Any = conn.writer
    writer.oob_option_callback(GMCP, True)
    for call in writer.set_ext_callback.call_args_list:
        opt, func = call.args
        func(*(("Pkg", 1) if opt == GMCP else ({"LIST": "X"},)))
    assert seen == [(conn, GMCP, True), (conn, "Pkg", 1), (conn, {"LIST": "X"})]

"""Link tests for plugin-owned telnet options over real sockets (#566, ADR-0012).

A ``MudTelnetClient`` talks to a scripted MUD, and scripted clients talk to the proxy's own
``create_server``. Option 102 is Aardwolf's: ``SB 102 100 3`` is its "character active" state
from the MUD and ``SB 102 7 1`` turns spellup tags on from a client. Every wait is bounded.
"""

import asyncio
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any

import pytest
from telnetlib3 import open_connection
from telnetlib3.telopt import DO, DONT, IAC, SB, WILL, WONT

from bastproxy.libs.net.mud import MudTelnetClient
from bastproxy.libs.net.protocols import PROTOCOLS
from bastproxy.libs.records import RMANAGER
from tests.libs.net.clients import (
    ProxyServer,
    ScriptedClient,
    ScriptedMud,
    proxy_server,
    sb_frame,
    scripted_mud,
    wait_until,
)
from tests.libs.net.test_telopt import FakeApi

TIMEOUT = 5
A102 = bytes([102])
O150 = bytes([150])
OWNER = "plugins.test.a102"
MUD_EVENT = "ev_libs.net.mud_telopt_102"


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeApi]:
    """Give each test empty records, no registrations and a collecting event API."""
    monkeypatch.setattr(RMANAGER, "record_instances", {})
    monkeypatch.setattr(RMANAGER, "records", {})
    PROTOCOLS.mud_disconnected()
    PROTOCOLS.telopt.reset()
    fake = FakeApi(PROTOCOLS.api)
    monkeypatch.setattr(PROTOCOLS, "api", fake)
    yield fake
    PROTOCOLS.mud_disconnected()
    PROTOCOLS.telopt.reset()


def _events(fake: FakeApi, name: str) -> list[dict[str, Any]]:
    return [args for event, args in fake.raised if event == name]


def _telopt_records(direction: str, link: str | None = None) -> list[Any]:
    return [
        r
        for r in RMANAGER.records.get("TelnetProtocolMessage", {}).values()
        if r.protocol == "TELOPT" and str(r.direction) == direction and link in (None, r.link)
    ]


def sbs(client: ScriptedClient, opt: bytes = A102) -> list[bytes]:
    """The payloads of the subnegotiations for ``opt`` a scripted client received."""
    return [payload for option, payload in client.subnegotiations if option == opt]


async def settle() -> None:
    """Let in-flight bytes arrive when a test asserts that nothing happened."""
    await asyncio.sleep(0.3)


@asynccontextmanager
async def mud_link(
    offer: tuple[bytes, ...] = (A102,),
) -> AsyncIterator[tuple[ScriptedMud, Callable[[bytes], None], Any]]:
    """A ``MudTelnetClient`` linked to a scripted MUD that offers ``offer`` with ``WILL``.

    Yields the MUD, a function that makes the MUD write bytes, and the proxy's MUD writer.
    """
    frames: asyncio.Queue[bytes | None] = asyncio.Queue()

    async def script(mud: ScriptedMud, writer: asyncio.StreamWriter) -> None:
        for opt in offer:
            writer.write(IAC + WILL + opt)
        await writer.drain()
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
        try:
            yield mud, frames.put_nowait, writer
        finally:
            frames.put_nowait(None)
            writer.close()
            PROTOCOLS.mud_disconnected()


@asynccontextmanager
async def world(
    offer: tuple[bytes, ...] = (A102,),
) -> AsyncIterator[tuple[ProxyServer, ScriptedMud, Callable[[bytes], None], Any]]:
    """A proxy server with real ``ClientConnection`` objects, linked to a scripted MUD."""
    async with mud_link(offer) as (mud, push, writer), proxy_server(connections=True) as proxy:
        yield proxy, mud, push, writer


async def join(
    stack: AsyncExitStack, proxy: ProxyServer, agree: set[bytes], login: bool = True
) -> ScriptedClient:
    """Connect a scripted client and optionally log it in."""
    client = await proxy.connect(agree)
    stack.push_async_callback(client.close)
    if login:
        proxy.login(len(proxy.connections) - 1)
    return client


# MUD side ---------------------------------------------------------------------


async def test_unregistered_options_are_refused_as_before(isolated: FakeApi) -> None:
    async with mud_link((A102, O150)) as (mud, _push, _writer):
        await mud.wait_for(lambda: IAC + DONT + A102 in mud.received)
        await mud.wait_for(lambda: IAC + DONT + O150 in mud.received)
        await settle()
        assert IAC + DO + A102 not in mud.received
        assert isolated.raised == []


async def test_a_registered_option_is_accepted_and_raises_enabled(isolated: FakeApi) -> None:
    PROTOCOLS.telopt.register(102, OWNER)
    async with mud_link() as (mud, _push, _writer):
        await mud.wait_for(lambda: IAC + DO + A102 in mud.received)
        await wait_until(lambda: bool(_events(isolated, MUD_EVENT + "_enabled")))
        await settle()
        assert _events(isolated, MUD_EVENT + "_enabled") == [{"option": 102}]
        assert mud.received.count(IAC + DO + A102) == 1
        assert IAC + DONT + A102 not in mud.received
        assert PROTOCOLS.telopt.get(102)["mud_enabled"] is True  # type: ignore[index]


async def test_a_mud_subnegotiation_raises_the_event_and_is_recorded(isolated: FakeApi) -> None:
    PROTOCOLS.telopt.register(102, OWNER)
    async with mud_link() as (mud, push, _writer):
        await mud.wait_for(lambda: IAC + DO + A102 in mud.received)
        push(sb_frame(A102, bytes([100, 3])))
        await wait_until(lambda: bool(_events(isolated, MUD_EVENT)))
        assert _events(isolated, MUD_EVENT) == [{"option": 102, "data": bytes([100, 3])}]
        [rec] = _telopt_records("received", "mud")
        assert (rec.package, rec.data) == ("102", bytes([100, 3]))


async def test_an_escaped_iac_in_a_mud_payload_is_unescaped(isolated: FakeApi) -> None:
    PROTOCOLS.telopt.register(102, OWNER)
    async with mud_link() as (mud, push, _writer):
        await mud.wait_for(lambda: IAC + DO + A102 in mud.received)
        push(sb_frame(A102, bytes([1, 255, 2])))
        await wait_until(lambda: bool(_events(isolated, MUD_EVENT)))
        assert _events(isolated, MUD_EVENT)[0]["data"] == bytes([1, 255, 2])


async def test_wont_raises_disabled(isolated: FakeApi) -> None:
    PROTOCOLS.telopt.register(102, OWNER)
    async with mud_link() as (mud, push, _writer):
        await mud.wait_for(lambda: IAC + DO + A102 in mud.received)
        push(IAC + WONT + A102)
        await wait_until(lambda: bool(_events(isolated, MUD_EVENT + "_disabled")))
        assert PROTOCOLS.telopt.get(102)["mud_enabled"] is False  # type: ignore[index]


async def test_a_subnegotiation_before_negotiation_is_dropped(isolated: FakeApi) -> None:
    PROTOCOLS.telopt.register(102, OWNER)
    async with mud_link(offer=()) as (_mud, push, _writer):
        push(sb_frame(A102, bytes([100, 3])))
        await settle()
        assert isolated.raised == []
        assert _telopt_records("received") == []


async def test_an_unknown_option_works_end_to_end_once_registered(isolated: FakeApi) -> None:
    PROTOCOLS.telopt.register(150, OWNER)
    async with mud_link((O150,)) as (mud, push, _writer):
        await mud.wait_for(lambda: IAC + DO + O150 in mud.received)
        push(sb_frame(O150, b"\x01\x02"))
        await wait_until(lambda: bool(_events(isolated, "ev_libs.net.mud_telopt_150")))
        assert PROTOCOLS.telopt.send(150, b"\x07\x01") is True
        await mud.wait_for(lambda: IAC + SB + O150 + b"\x07\x01" in mud.received)


async def test_send_reaches_the_mud_as_aardwolfs_frame(isolated: FakeApi) -> None:
    PROTOCOLS.telopt.register(102, OWNER)
    async with mud_link() as (mud, _push, _writer):
        await mud.wait_for(lambda: IAC + DO + A102 in mud.received)
        await wait_until(lambda: PROTOCOLS.telopt.get(102)["mud_enabled"])  # type: ignore[index]
        assert PROTOCOLS.telopt.send(102, bytes([5, 1])) is True
        await mud.wait_for(lambda: bytes([255, 250, 102, 5, 1, 255, 240]) in mud.received)
        assert [r.data for r in _telopt_records("sent", "mud")] == [bytes([5, 1])]


async def test_registering_after_an_early_will_asks_with_do(isolated: FakeApi) -> None:
    async with mud_link() as (mud, push, _writer):
        await mud.wait_for(lambda: IAC + DONT + A102 in mud.received)
        assert IAC + DO + A102 not in mud.received
        PROTOCOLS.telopt.register(102, OWNER)
        await mud.wait_for(lambda: IAC + DO + A102 in mud.received)
        push(IAC + WILL + A102)  # the MUD's answer
        await wait_until(lambda: bool(_events(isolated, MUD_EVENT + "_enabled")))
        await settle()
        assert mud.received.count(IAC + DO + A102) == 1
        assert len(_events(isolated, MUD_EVENT + "_enabled")) == 1


async def test_unregistering_while_enabled_sends_dont(isolated: FakeApi) -> None:
    PROTOCOLS.telopt.register(102, OWNER)
    async with mud_link() as (mud, _push, _writer):
        await mud.wait_for(lambda: IAC + DO + A102 in mud.received)
        await wait_until(lambda: bool(_events(isolated, MUD_EVENT + "_enabled")))
        assert PROTOCOLS.telopt.unregister(102, OWNER)
        await mud.wait_for(lambda: IAC + DONT + A102 in mud.received)
        assert len(_events(isolated, MUD_EVENT + "_disabled")) == 1


async def test_a_mud_disconnect_raises_disabled(isolated: FakeApi) -> None:
    PROTOCOLS.telopt.register(102, OWNER)
    async with mud_link() as (mud, _push, _writer):
        await mud.wait_for(lambda: IAC + DO + A102 in mud.received)
        await wait_until(lambda: bool(_events(isolated, MUD_EVENT + "_enabled")))
        PROTOCOLS.mud_disconnected()
        assert len(_events(isolated, MUD_EVENT + "_disabled")) == 1


# client side ------------------------------------------------------------------


async def test_a_new_client_is_offered_a_registered_option() -> None:
    PROTOCOLS.telopt.register(102, OWNER)
    async with proxy_server(connections=True) as proxy, AsyncExitStack() as stack:
        client = await join(stack, proxy, {A102}, login=False)
        assert (WILL, A102) in client.commands


async def test_no_offer_when_unregistered_or_not_for_clients() -> None:
    async with proxy_server(connections=True) as proxy, AsyncExitStack() as stack:
        client = await join(stack, proxy, {A102}, login=False)
        assert (WILL, A102) not in client.commands
        PROTOCOLS.telopt.register(102, OWNER, client=False)
        other = await join(stack, proxy, {A102}, login=False)
        assert (WILL, A102) not in other.commands
        await settle()
        assert (WILL, A102) not in client.commands


async def test_registering_offers_to_clients_already_connected() -> None:
    async with proxy_server(connections=True) as proxy, AsyncExitStack() as stack:
        client = await join(stack, proxy, {A102}, login=False)
        assert (WILL, A102) not in client.commands
        PROTOCOLS.telopt.register(102, OWNER)
        await client.wait_for(lambda: (WILL, A102) in client.commands)
        await client.wait_for(lambda: PROTOCOLS.telopt.get(102) is not None)


async def test_the_mud_subnegotiation_goes_to_enabled_logged_in_clients(isolated: FakeApi) -> None:
    PROTOCOLS.telopt.register(102, OWNER)
    async with world() as (proxy, mud, push, _writer), AsyncExitStack() as stack:
        await mud.wait_for(lambda: IAC + DO + A102 in mud.received)
        agreed = await join(stack, proxy, {A102})
        refused = await join(stack, proxy, set())
        not_in = await join(stack, proxy, {A102}, login=False)
        push(sb_frame(A102, bytes([100, 3])))
        await agreed.wait_for(lambda: (A102, bytes([100, 3])) in agreed.subnegotiations)
        await settle()
        assert sbs(refused) == []
        assert sbs(not_in) == []
        assert len(_telopt_records("sent", proxy.connections[0].uuid)) == 1
        assert len(_events(isolated, MUD_EVENT)) == 1


async def test_forwarding_can_be_turned_off(isolated: FakeApi) -> None:
    PROTOCOLS.telopt.register(102, OWNER, forward=False)
    async with world() as (proxy, mud, push, _writer), AsyncExitStack() as stack:
        await mud.wait_for(lambda: IAC + DO + A102 in mud.received)
        client = await join(stack, proxy, {A102})
        push(sb_frame(A102, bytes([100, 3])))
        await wait_until(lambda: bool(_events(isolated, MUD_EVENT)))
        await settle()
        assert sbs(client) == []


async def test_a_client_subnegotiation_raises_the_client_event(isolated: FakeApi) -> None:
    PROTOCOLS.telopt.register(102, OWNER)
    async with world() as (proxy, mud, _push, _writer), AsyncExitStack() as stack:
        await mud.wait_for(lambda: IAC + DO + A102 in mud.received)
        client = await join(stack, proxy, {A102})
        client.send(sb_frame(A102, bytes([7, 1])))
        name = "ev_libs.net.client_telopt_102"
        await wait_until(lambda: bool(_events(isolated, name)))
        assert _events(isolated, name) == [
            {
                "option": 102,
                "data": bytes([7, 1]),
                "client_id": proxy.connections[0].uuid,
                "view_only": False,
            }
        ]
        await settle()
        assert IAC + SB + A102 not in mud.received


async def test_a_subnegotiation_from_a_client_not_logged_in_is_dropped(isolated: FakeApi) -> None:
    PROTOCOLS.telopt.register(102, OWNER)
    async with proxy_server(connections=True) as proxy, AsyncExitStack() as stack:
        client = await join(stack, proxy, {A102}, login=False)
        client.send(sb_frame(A102, bytes([7, 1])))
        await settle()
        assert isolated.raised == []


async def test_send_client_targets(isolated: FakeApi) -> None:
    PROTOCOLS.telopt.register(102, OWNER)
    async with proxy_server(connections=True) as proxy, AsyncExitStack() as stack:
        first = await join(stack, proxy, {A102})
        second = await join(stack, proxy, {A102})
        refused = await join(stack, proxy, set())
        target = proxy.connections[1].uuid
        assert PROTOCOLS.telopt.send_client(102, bytes([5, 1]), target) is True
        await second.wait_for(lambda: (A102, bytes([5, 1])) in second.subnegotiations)
        await settle()
        assert sbs(first) == []
        assert PROTOCOLS.telopt.send_client(102, bytes([6, 1])) is True
        await first.wait_for(lambda: (A102, bytes([6, 1])) in first.subnegotiations)
        await second.wait_for(lambda: (A102, bytes([6, 1])) in second.subnegotiations)
        assert sbs(refused) == []
        assert len(_telopt_records("sent")) == 3
        assert PROTOCOLS.telopt.send_client(150, b"\x01") is False


async def test_unregistering_sends_wont_to_enabled_clients() -> None:
    PROTOCOLS.telopt.register(102, OWNER)
    async with proxy_server(connections=True) as proxy, AsyncExitStack() as stack:
        client = await join(stack, proxy, {A102})
        refused = await join(stack, proxy, set())
        assert PROTOCOLS.telopt.unregister(102, OWNER)
        await client.wait_for(lambda: (WONT, A102) in client.commands)
        await settle()
        assert (WONT, A102) not in refused.commands

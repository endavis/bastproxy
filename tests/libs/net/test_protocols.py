"""Tests for GMCP and MSDP on the MUD link and the protocol manager (#59)."""

import asyncio
import logging
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import MagicMock

import pytest
from telnetlib3 import open_connection
from telnetlib3.telopt import DO, GMCP, IAC, MSDP, WILL

from bastproxy.libs.net import negotiation as neg_mod
from bastproxy.libs.net import oob
from bastproxy.libs.net.mud import MudTelnetClient
from bastproxy.libs.net.protocols import (
    EVENT_RAISE_API,
    MUD_GMCP_EVENT,
    MUD_MSDP_EVENT,
    PROTOCOL_EVENTS,
    PROTOCOLS,
)
from bastproxy.libs.records import RMANAGER
from bastproxy.plugins._baseplugin import BasePlugin
from bastproxy.plugins.core.events.plugin._events import EventsPlugin
from tests.libs.net.clients import ScriptedMud, proxy_server, scripted_mud, wait_until

TIMEOUT = 5
ADD = "libs.net.protocols:gmcp.modules.add"
REMOVE = "libs.net.protocols:gmcp.modules.remove"
REMOVE_OWNER = "libs.net.protocols:gmcp.modules.remove.for.owner"
SUPPORTS = "libs.net.protocols:gmcp.supports.get"
GMCP_CACHE = "libs.net.protocols:gmcp.cache.get"
MSDP_CACHE = "libs.net.protocols:msdp.cache.get"


class FakeApi:
    """Wraps the real API, pretending the events plugin is loaded and collecting its raises."""

    def __init__(self, real: Any) -> None:
        self.real = real
        self.owner_id = real.owner_id
        self.raised: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, name: str) -> Any:
        if name == EVENT_RAISE_API:
            return self._raise
        if name == "libs.api:api.exists":
            return lambda api_name: api_name == EVENT_RAISE_API or self.real(name)(api_name)
        return self.real(name)

    def _raise(self, event: str, event_args: dict[str, Any], calledfrom: str | None = None) -> None:
        self.raised.append((event, event_args))


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeApi]:
    """Give each test an empty record store, a clean manager and a collecting event API."""
    monkeypatch.setattr(RMANAGER, "record_instances", {})
    monkeypatch.setattr(RMANAGER, "records", {})
    PROTOCOLS.mud_disconnected()
    PROTOCOLS._owner_modules.clear()
    fake = FakeApi(PROTOCOLS.api)
    monkeypatch.setattr(PROTOCOLS, "api", fake)
    yield fake
    PROTOCOLS.mud_disconnected()
    PROTOCOLS._owner_modules.clear()


def _messages() -> list[Any]:
    return list(RMANAGER.records.get("TelnetProtocolMessage", {}).values())


class FakeWriter:
    """Stands in for the MUD's writer: GMCP is negotiated and sends are collected."""

    def __init__(self, gmcp_enabled: bool = True) -> None:
        self.remote_option = MagicMock()
        self.remote_option.enabled = lambda opt: gmcp_enabled and opt == GMCP
        self.sent: list[tuple[str, Any]] = []
        self.closing = False

    def is_closing(self) -> bool:
        return self.closing

    def send_gmcp(self, package: str, data: Any = None) -> None:
        self.sent.append((package, data))


# registration ----------------------------------------------------------------


def test_apis_exist() -> None:
    for name in (ADD, REMOVE, REMOVE_OWNER, SUPPORTS, GMCP_CACHE, MSDP_CACHE):
        assert callable(PROTOCOLS.api(name)), name


def test_protocol_events_are_defined() -> None:
    names = {spec.name: spec for spec in PROTOCOL_EVENTS}
    assert set(names) == {MUD_GMCP_EVENT, MUD_MSDP_EVENT}
    assert set(names[MUD_GMCP_EVENT].arg_descriptions) == {"package", "data"}
    assert set(names[MUD_MSDP_EVENT].arg_descriptions) == {"variable", "data"}


def test_events_plugin_registers_the_protocol_events() -> None:
    added: list[str] = []

    class _Api:
        def __call__(self, name: str) -> Any:
            if name == "plugins.core.events:event.add":
                return lambda event_name, *_a, **_k: added.append(event_name)
            return MagicMock()

    plugin = MagicMock()
    plugin.plugin_id = "plugins.core.events"
    plugin.api = _Api()
    EventsPlugin._phook_initialize(plugin)
    assert {MUD_GMCP_EVENT, MUD_MSDP_EVENT} <= set(added)


def test_uninitialize_removes_the_plugin_modules() -> None:
    calls: list[tuple[str, tuple[Any, ...]]] = []

    class _Api:
        def __call__(self, name: str) -> Any:
            return lambda *a, **_k: calls.append((name, a))

    plugin = MagicMock()
    plugin.plugin_id = "plugins.test.owner"
    plugin.is_reloading_f = False
    plugin.api = _Api()
    BasePlugin._phook_base_unitialize_hook(plugin)
    assert (REMOVE_OWNER, ("plugins.test.owner",)) in calls


# the Core.Supports union ------------------------------------------------------


def _connect(writer: FakeWriter | None = None) -> FakeWriter:
    writer = writer or FakeWriter()
    PROTOCOLS.mud_connected(writer)
    return writer


def test_hello_is_sent_once_with_no_supports_when_the_union_is_empty() -> None:
    writer = _connect()
    PROTOCOLS.on_mud_will_gmcp(GMCP)
    assert [p for p, _ in writer.sent] == ["Core.Hello"]
    assert writer.sent[0][1]["client"] == "bastproxy"


def test_hello_waits_for_the_offer() -> None:
    writer = _connect(FakeWriter(gmcp_enabled=False))
    assert writer.sent == []


def test_supports_follow_hello_when_modules_are_registered() -> None:
    PROTOCOLS.api(ADD)(["Room", "Char 2"], owner_id="a")
    writer = _connect()
    assert writer.sent[1] == ("Core.Supports.Set", ["char 2", "room 1"])


def test_union_add_readd_merge_and_remove() -> None:
    writer = _connect()
    sets = lambda: [d for p, d in writer.sent if p == "Core.Supports.Set"]  # noqa: E731
    PROTOCOLS.api(ADD)(["Char 1"], owner_id="a")
    assert sets() == [["char 1"]]
    PROTOCOLS.api(ADD)(["char 1"], owner_id="b")  # same union, no re-send
    PROTOCOLS.api(ADD)(["Char 1"], owner_id="a")
    assert sets() == [["char 1"]]
    PROTOCOLS.api(ADD)(["Char 3", "Room"], owner_id="b")  # version merge
    assert sets()[-1] == ["char 3", "room 1"]
    PROTOCOLS.api(REMOVE)(["Room"], owner_id="b")
    assert sets()[-1] == ["char 3"]
    PROTOCOLS.api(REMOVE_OWNER)("b")
    assert sets()[-1] == ["char 1"]
    PROTOCOLS.api(REMOVE)(owner_id="a")
    assert sets()[-1] == []
    assert PROTOCOLS.api(SUPPORTS)() == []


def test_supports_are_not_sent_before_the_hello() -> None:
    PROTOCOLS.api(ADD)(["Char"], owner_id="a")
    assert PROTOCOLS.api(SUPPORTS)() == ["char 1"]
    writer = _connect(FakeWriter(gmcp_enabled=False))
    PROTOCOLS.api(ADD)(["Room"], owner_id="a")
    assert writer.sent == []


def test_add_defaults_the_owner_to_the_caller() -> None:
    PROTOCOLS.api(ADD)(["Char"])
    assert len(PROTOCOLS._owner_modules) == 1
    owner = next(iter(PROTOCOLS._owner_modules))
    PROTOCOLS.api(REMOVE_OWNER)(owner)
    assert PROTOCOLS.api(SUPPORTS)() == []


def test_add_ignores_invalid_modules() -> None:
    assert PROTOCOLS.api(ADD)(["bad entry here", "Char"], owner_id="a") == ["char 1"]
    assert PROTOCOLS.api(ADD)([], owner_id="b") == []
    assert "b" not in PROTOCOLS._owner_modules


# messages -------------------------------------------------------------------


def test_gmcp_message_records_caches_and_raises(isolated: FakeApi) -> None:
    PROTOCOLS.on_mud_gmcp("Char.Vitals", {"hp": 5})
    [record] = _messages()
    assert (record.protocol, record.package, record.data) == ("GMCP", "Char.Vitals", {"hp": 5})
    assert (record.direction, record.link) == ("received", "mud")
    assert PROTOCOLS.api(GMCP_CACHE)("Char.Vitals") == {"hp": 5}
    assert isolated.raised == [(MUD_GMCP_EVENT, {"package": "Char.Vitals", "data": {"hp": 5}})]


def test_msdp_message_raises_once_per_variable(isolated: FakeApi) -> None:
    PROTOCOLS.on_mud_msdp({"HEALTH": "5", "ROOM": {"NAME": "Hall"}})
    assert sorted(r.package for r in _messages()) == ["HEALTH", "ROOM"]
    assert all(r.protocol == "MSDP" for r in _messages())
    assert isolated.raised == [
        (MUD_MSDP_EVENT, {"variable": "HEALTH", "data": "5"}),
        (MUD_MSDP_EVENT, {"variable": "ROOM", "data": {"NAME": "Hall"}}),
    ]
    assert PROTOCOLS.api(MSDP_CACHE)() == {"HEALTH": "5", "ROOM": {"NAME": "Hall"}}
    assert PROTOCOLS.api(MSDP_CACHE)("HEALTH") == "5"
    assert PROTOCOLS.api(MSDP_CACHE)("NOPE") is None


def test_event_data_is_a_copy(isolated: FakeApi) -> None:
    PROTOCOLS.on_mud_gmcp("Char.Vitals", {"hp": 5})
    isolated.raised[0][1]["data"]["hp"] = 0
    assert PROTOCOLS.api(GMCP_CACHE)("Char.Vitals") == {"hp": 5}
    PROTOCOLS.api(GMCP_CACHE)("Char.Vitals")["hp"] = 1
    assert PROTOCOLS.api(GMCP_CACHE)("Char.Vitals") == {"hp": 5}


def test_gmcp_dict_updates_merge_in_the_cache() -> None:
    PROTOCOLS.on_mud_gmcp("Char.Vitals", {"hp": 5, "mp": 1})
    PROTOCOLS.on_mud_gmcp("Char.Vitals", {"hp": 4})
    assert PROTOCOLS.api(GMCP_CACHE)("Char.Vitals") == {"hp": 4, "mp": 1}
    PROTOCOLS.on_mud_gmcp("Char.Vitals", "text")
    assert PROTOCOLS.api(GMCP_CACHE)("Char.Vitals") == "text"


def test_core_messages_are_recorded_but_not_cached_or_raised(isolated: FakeApi) -> None:
    PROTOCOLS.on_mud_gmcp("Core.Goodbye", None)
    PROTOCOLS.on_mud_gmcp("core.ping", None)
    assert len(_messages()) == 2
    assert PROTOCOLS.api(GMCP_CACHE)() == {}
    assert isolated.raised == []


def test_a_key_past_the_cap_is_raised_but_not_cached(
    monkeypatch: pytest.MonkeyPatch, isolated: FakeApi, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(oob, "CACHE_MAX_ENTRIES", 2)
    with caplog.at_level(logging.WARNING):
        for name in ("A.One", "A.Two", "A.Three", "A.Four"):
            PROTOCOLS.on_mud_gmcp(name, 1)
    assert sorted(PROTOCOLS.api(GMCP_CACHE)()) == ["A.One", "A.Two"]
    assert len(isolated.raised) == 4
    assert len([r for r in caplog.records if "not cached" in r.getMessage()]) == 1
    PROTOCOLS.on_mud_gmcp("A.One", 2)  # an existing key still updates
    assert PROTOCOLS.api(GMCP_CACHE)("A.One") == 2


def test_a_failing_event_does_not_stop_the_message(
    monkeypatch: pytest.MonkeyPatch, isolated: FakeApi
) -> None:
    def boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("callback failed")

    monkeypatch.setattr(isolated, "_raise", boom)
    PROTOCOLS.on_mud_gmcp("Char.Vitals", {"hp": 1})
    assert len(_messages()) == 1


def test_no_event_when_the_events_plugin_is_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.undo()  # the real API: the events plugin is not loaded here
    PROTOCOLS.on_mud_gmcp("Char.Vitals", {"hp": 1})
    assert PROTOCOLS.api(GMCP_CACHE)("Char.Vitals") == {"hp": 1}


def test_disconnect_clears_the_state_and_the_next_connection_says_hello() -> None:
    first = _connect()
    PROTOCOLS.on_mud_gmcp("Char.Vitals", {"hp": 1})
    PROTOCOLS.on_mud_msdp({"HEALTH": "1"})
    assert [p for p, _ in first.sent] == ["Core.Hello"]
    PROTOCOLS.mud_disconnected()
    assert PROTOCOLS.api(GMCP_CACHE)() == {}
    assert PROTOCOLS.api(MSDP_CACHE)() == {}
    second = _connect()
    assert [p for p, _ in second.sent] == ["Core.Hello"]


# the real MUD link -------------------------------------------------------------


@asynccontextmanager
async def mud_link(frames: list[bytes]) -> AsyncIterator[tuple[ScriptedMud, Any]]:
    """Connect a ``MudTelnetClient`` to a scripted MUD that offers GMCP and MSDP.

    The MUD sends ``frames`` once it has received the proxy's ``Core.Hello``.
    """
    done = asyncio.Event()

    async def script(mud: ScriptedMud, writer: asyncio.StreamWriter) -> None:
        writer.write(IAC + WILL + GMCP + IAC + WILL + MSDP)
        await writer.drain()
        await mud.wait_for(lambda: b"Core.Hello" in mud.received)
        for frame in frames:
            writer.write(frame)
        await writer.drain()
        await done.wait()

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
            yield mud, writer
        finally:
            done.set()
            writer.close()
            PROTOCOLS.mud_disconnected()


async def test_link_accepts_both_protocols_and_sends_one_hello() -> None:
    async with mud_link([]) as (mud, _writer):
        await mud.wait_for(lambda: b"Core.Hello" in mud.received)
        await asyncio.sleep(0.2)
        assert IAC + DO + GMCP in mud.received
        assert IAC + DO + MSDP in mud.received
        assert mud.received.count(b"Core.Hello") == 1
        assert b"bastproxy" in mud.received
        assert b"telnetlib3" not in mud.received


async def test_link_gmcp_message_makes_one_event_and_one_record(isolated: FakeApi) -> None:
    frames = [ScriptedMud.gmcp_frame("Char.Vitals", {"hp": 7})]
    async with mud_link(frames):
        await wait_until(lambda: len(isolated.raised) == 1)
    assert isolated.raised == [(MUD_GMCP_EVENT, {"package": "Char.Vitals", "data": {"hp": 7}})]
    [record] = _messages()
    assert (record.protocol, record.package, str(record.direction), record.link) == (
        "GMCP",
        "Char.Vitals",
        "received",
        "mud",
    )


async def test_link_msdp_message_with_two_variables_makes_two_events(isolated: FakeApi) -> None:
    frames = [ScriptedMud.msdp_frame({"HEALTH": "7", "ROOM": ["a", "b"]})]
    async with mud_link(frames):
        await wait_until(lambda: len(isolated.raised) == 2)
    assert {args["variable"] for _, args in isolated.raised} == {"HEALTH", "ROOM"}
    assert len(_messages()) == 2


async def test_link_drops_malformed_messages_and_keeps_going(
    isolated: FakeApi, caplog: pytest.LogCaptureFixture
) -> None:
    frames = [
        IAC + bytes([250]) + GMCP + b"Char.Vitals {not json SECRETPAYLOAD" + IAC + bytes([240]),
        IAC
        + bytes([250])
        + MSDP
        + bytes([1])
        + b"A"
        + bytes([2])
        + bytes([3])
        + IAC
        + bytes([240]),
        ScriptedMud.gmcp_frame("Char.Vitals", {"hp": 1}),
    ]
    with caplog.at_level(logging.WARNING):
        async with mud_link(frames) as (_mud, writer):
            await wait_until(lambda: len(isolated.raised) == 1)
            assert not writer.is_closing()
    assert [args["package"] for _, args in isolated.raised] == ["Char.Vitals"]
    dropped = [r.getMessage() for r in caplog.records if "Dropped a" in r.getMessage()]
    assert len(dropped) == 2
    assert all("SECRETPAYLOAD" not in message for message in dropped)
    assert any("name=Char.Vitals" in message for message in dropped)


async def test_link_core_messages_are_not_cached(isolated: FakeApi) -> None:
    frames = [ScriptedMud.gmcp_frame("Core.Ping"), ScriptedMud.gmcp_frame("Room.Info", {"n": 1})]
    async with mud_link(frames):
        await wait_until(lambda: len(isolated.raised) == 1)
        assert sorted(PROTOCOLS.api(GMCP_CACHE)()) == ["Room.Info"]


async def test_link_supports_change_is_sent_to_the_mud() -> None:
    async with mud_link([]) as (mud, _writer):
        await mud.wait_for(lambda: b"Core.Hello" in mud.received)
        PROTOCOLS.api(ADD)(["Char 1"], owner_id="a")
        await mud.wait_for(lambda: b"Core.Supports.Set" in mud.received)
        assert b'["char 1"]' in mud.received


# the negotiation gate ----------------------------------------------------------


async def test_sb_on_a_link_without_the_option_is_dropped_before_decoding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[str] = []

    def spy(name: str) -> Callable[..., Any]:
        def decode(*_a: Any, **_k: Any) -> Any:
            called.append(name)
            raise AssertionError("decoder must not run")

        return decode

    monkeypatch.setattr(oob, "decode_gmcp", spy("gmcp"))
    monkeypatch.setattr(oob, "decode_msdp", spy("msdp"))
    async with proxy_server() as proxy:
        client = await proxy.connect()
        client.gmcp("Char.Login", {"name": "x"})
        client.msdp({"REPORT": "HEALTH"})
        await wait_until(
            lambda: (
                sum(
                    1
                    for r in RMANAGER.records.get("TelnetNegotiation", {}).values()
                    if r.command == "SB" and r.option in ("GMCP", "MSDP")
                )
                == 2
            )
        )
        await asyncio.sleep(0.1)
        await client.close()
    assert called == []
    assert _messages() == []


def test_the_gate_checks_either_direction() -> None:
    writer = neg_mod.RecordingTelnetWriter.__new__(neg_mod.RecordingTelnetWriter)
    writer.local_option = MagicMock()
    writer.remote_option = MagicMock()
    writer.environ_encoding = ""
    delivered: list[Any] = []
    for local, remote, expected in ((False, False, 0), (True, False, 1), (False, True, 1)):
        writer.local_option.enabled.return_value = local
        writer.remote_option.enabled.return_value = remote
        import collections

        buf = collections.deque([GMCP, b"Char.Vitals {}"])
        writer._handle_oob_sb(buf, GMCP, oob.decode_gmcp, delivered.append)
        assert len(delivered) == expected
        delivered.clear()

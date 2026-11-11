"""Tests for MSSP: the bounded decoder, the manager, the MUD link and the client links (#60).

The link tests drive real telnetlib3 negotiation, as ``test_protocols_clients.py`` does, and
reuse its ``mud_link``, ``join`` and ``settle`` helpers.
"""

import asyncio
import logging
from collections.abc import Callable, Iterator
from contextlib import AsyncExitStack
from typing import Any

import pytest
from telnetlib3.mud import mssp_decode, mssp_encode
from telnetlib3.telopt import DO, DONT, IAC, MSSP, WILL

from bastproxy.libs.net import oob
from bastproxy.libs.net.protocols import (
    EVENT_RAISE_API,
    MUD_MSSP_EVENT,
    PROTOCOLS,
)
from bastproxy.libs.records import RMANAGER
from tests.libs.net.clients import ScriptedClient, ScriptedMud, proxy_server, wait_until
from tests.libs.net.test_protocols_clients import join, mud_link, settle, world

MSSP_CACHE = "libs.net.protocols:mssp.cache.get"
TABLE: dict[str, str | list[str]] = {"NAME": "Test MUD", "PLAYERS": "3", "CODEBASE": ["a", "b"]}


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
    """Give each test empty records, a clean manager and a collecting event API."""
    monkeypatch.setattr(RMANAGER, "record_instances", {})
    monkeypatch.setattr(RMANAGER, "records", {})
    PROTOCOLS.mud_disconnected()
    PROTOCOLS._owner_modules.clear()
    fake = FakeApi(PROTOCOLS.api)
    monkeypatch.setattr(PROTOCOLS, "api", fake)
    yield fake
    PROTOCOLS.mud_disconnected()
    PROTOCOLS._owner_modules.clear()


def _messages(direction: str | None = None) -> list[Any]:
    found = list(RMANAGER.records.get("TelnetProtocolMessage", {}).values())
    return [r for r in found if r.protocol == "MSSP" and direction in (None, str(r.direction))]


def mssp_seen(client: ScriptedClient) -> list[dict[str, str | list[str]]]:
    """The MSSP tables a scripted client received."""
    return [mssp_decode(payload) for opt, payload in client.subnegotiations if opt == MSSP]


def payload(variables: dict[str, str | list[str]]) -> bytes:
    """The wire payload of a table."""
    return mssp_encode(variables)


async def offer_mssp(push: Callable[[bytes], None], writer: Any) -> None:
    """Have the scripted MUD offer MSSP and wait until the proxy's MUD link accepted it."""
    push(IAC + WILL + MSSP)
    await wait_until(lambda: bool(writer.remote_option.enabled(MSSP)))


# the decoder -----------------------------------------------------------------------------


def test_decoder_keeps_a_single_value_and_lists_multiple_values() -> None:
    assert oob.decode_mssp(payload(TABLE)) == TABLE


def test_decoder_accepts_a_name_with_a_space() -> None:
    assert oob.decode_mssp(payload({"CRAWL DELAY": "5"})) == {"CRAWL DELAY": "5"}


def test_decoder_skips_a_bad_name_and_keeps_the_rest(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger="bastproxy.libs.net.oob"):
        result = oob.decode_mssp(payload({"NAME": "x", "bad/name": "y", " lead": "z", "": "e"}))
    assert result == {"NAME": "x"}
    assert len([r for r in caplog.records if "MSSP skipped" in r.getMessage()]) == 1


@pytest.mark.parametrize("name", ["A", "a b", "A_B-C.D", "9lives", "x" * 64])
def test_valid_names(name: str) -> None:
    assert oob.valid_mssp_name(name)


@pytest.mark.parametrize("name", ["", " A", "_A", "x" * 65, "A\n", "A/B", "A:B"])
def test_invalid_names(name: str) -> None:
    assert not oob.valid_mssp_name(name)


def test_decoder_enforces_the_variable_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oob, "MSSP_MAX_VARIABLES", 3)
    result = oob.decode_mssp(payload({f"V{i}": str(i) for i in range(10)}))
    assert list(result) == ["V0", "V1", "V2"]


def test_decoder_enforces_the_value_count_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oob, "MSSP_MAX_VALUES", 2)
    assert oob.decode_mssp(payload({"A": ["1", "2", "3", "4"]})) == {"A": ["1", "2"]}


def test_decoder_skips_a_value_over_the_length_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oob, "MSSP_MAX_VALUE_LEN", 4)
    result = oob.decode_mssp(payload({"A": "toolong", "B": ["ok", "toolong", "fine"]}))
    assert result == {"B": ["ok", "fine"]}


def test_decoder_keeps_a_value_at_the_length_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oob, "MSSP_MAX_VALUE_LEN", 4)
    assert oob.decode_mssp(payload({"A": "abcd"})) == {"A": "abcd"}


def test_decoder_rejects_an_oversize_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oob, "OOB_MAX_PAYLOAD", 10)
    with pytest.raises(oob.OobDecodeError):
        oob.decode_mssp(payload({"NAME": "a longer value"}))


@pytest.mark.parametrize("data", [b"", b"no markers", payload({"bad/": "x"})])
def test_decoder_rejects_an_empty_or_fully_filtered_payload(data: bytes) -> None:
    with pytest.raises(oob.OobDecodeError):
        oob.decode_mssp(data)


# the manager -----------------------------------------------------------------------------


def test_a_table_makes_one_record_is_stored_and_raises_one_event(isolated: FakeApi) -> None:
    PROTOCOLS.on_mud_mssp(dict(TABLE))
    [record] = _messages()
    assert (record.package, record.data) == ("", TABLE)
    assert (str(record.direction), record.link) == ("received", "mud")
    assert PROTOCOLS.api(MSSP_CACHE)() == TABLE
    assert isolated.raised == [(MUD_MSSP_EVENT, {"data": TABLE})]


def test_the_event_carries_a_copy(isolated: FakeApi) -> None:
    PROTOCOLS.on_mud_mssp({"NAME": "x", "L": ["a"]})
    isolated.raised[0][1]["data"]["L"].append("changed")
    assert PROTOCOLS.api(MSSP_CACHE)() == {"NAME": "x", "L": ["a"]}
    PROTOCOLS.api(MSSP_CACHE)()["NAME"] = "changed"
    assert PROTOCOLS.api(MSSP_CACHE)("NAME") == "x"


def test_a_second_table_replaces_the_first(isolated: FakeApi) -> None:
    PROTOCOLS.on_mud_mssp({"NAME": "x", "OLD": "1"})
    PROTOCOLS.on_mud_mssp({"NAME": "y"})
    assert PROTOCOLS.api(MSSP_CACHE)() == {"NAME": "y"}
    assert len(isolated.raised) == 2


def test_the_cache_api_gives_the_table_one_variable_or_none() -> None:
    PROTOCOLS.on_mud_mssp(dict(TABLE))
    assert PROTOCOLS.api(MSSP_CACHE)() == TABLE
    assert PROTOCOLS.api(MSSP_CACHE)("CODEBASE") == ["a", "b"]
    assert PROTOCOLS.api(MSSP_CACHE)("NOPE") is None


def test_disconnect_clears_the_store() -> None:
    PROTOCOLS.on_mud_mssp(dict(TABLE))
    PROTOCOLS.mud_disconnected()
    assert PROTOCOLS.api(MSSP_CACHE)() == {}


def test_a_failing_event_raise_does_not_stop_the_store(
    monkeypatch: pytest.MonkeyPatch, isolated: FakeApi
) -> None:
    def boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("callback failed")

    monkeypatch.setattr(isolated, "_raise", boom)
    PROTOCOLS.on_mud_mssp(dict(TABLE))
    assert PROTOCOLS.api(MSSP_CACHE)() == TABLE
    assert len(_messages()) == 1


# the MUD link ----------------------------------------------------------------------------


async def test_the_mud_link_answers_will_mssp_with_do() -> None:
    async with mud_link() as (mud, push, writer):
        await offer_mssp(push, writer)
        await mud.wait_for(lambda: IAC + DO + MSSP in mud.received)


async def test_a_frame_from_the_mud_is_stored_and_raises_the_event(isolated: FakeApi) -> None:
    async with mud_link() as (_mud, push, writer):
        await offer_mssp(push, writer)
        push(ScriptedMud.mssp_frame(TABLE))
        await wait_until(lambda: len(isolated.raised) == 1)
        assert PROTOCOLS.api(MSSP_CACHE)() == TABLE
    assert isolated.raised == [(MUD_MSSP_EVENT, {"data": TABLE})]
    assert len(_messages("received")) == 1


async def test_an_oversize_frame_is_dropped_with_a_warning_and_a_later_one_is_stored(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, isolated: FakeApi
) -> None:
    monkeypatch.setattr(oob, "OOB_MAX_PAYLOAD", 40)
    async with mud_link() as (_mud, push, writer):
        await offer_mssp(push, writer)
        with caplog.at_level(logging.WARNING):
            push(ScriptedMud.mssp_frame({"NAME": "x" * 100}))
            push(ScriptedMud.mssp_frame({"NAME": "ok"}))
            await wait_until(lambda: len(isolated.raised) == 1)
            assert not writer.is_closing()
    assert PROTOCOLS._mssp == {"NAME": "ok"} or PROTOCOLS._mssp == {}  # cleared on disconnect
    assert isolated.raised == [(MUD_MSSP_EVENT, {"data": {"NAME": "ok"}})]
    dropped = [r for r in caplog.records if "Dropped a MSSP message" in r.getMessage()]
    assert len(dropped) == 1 and dropped[0].levelno == logging.WARNING


async def test_an_sb_on_a_link_without_mssp_is_dropped_before_decoding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[int] = []

    def decode(*_a: Any, **_k: Any) -> Any:
        called.append(1)
        raise AssertionError("decoder must not run")

    monkeypatch.setattr(oob, "decode_mssp", decode)
    async with proxy_server() as proxy:
        client = await proxy.connect()
        client.mssp({"NAME": "x"})
        await wait_until(
            lambda: any(
                r.command == "SB" and r.option == "MSSP"
                for r in RMANAGER.records.get("TelnetNegotiation", {}).values()
            )
        )
        await asyncio.sleep(0.1)
        await client.close()
    assert called == []
    assert _messages() == []


# the client links ------------------------------------------------------------------------


async def test_the_server_offers_mssp_and_the_flag_is_per_client() -> None:
    async with proxy_server(connections=True) as proxy, AsyncExitStack() as stack:
        _accepts, accepting = await join(stack, proxy, {MSSP})
        refuses, refusing = await join(stack, proxy, set())
        assert (WILL, MSSP) in refuses.commands
        assert accepting.mssp_enabled
        assert not refusing.mssp_enabled


async def test_the_option_callback_fires_on_do() -> None:
    async with proxy_server(connections=True) as proxy, AsyncExitStack() as stack:
        calls: list[tuple[bytes, bool]] = []
        client, conn = await join(stack, proxy, set())
        writer: Any = conn.writer
        writer.oob_option_callback = lambda opt, enabled: calls.append((opt, enabled))
        client.send(IAC + DO + MSSP)
        await wait_until(lambda: calls == [(MSSP, True)])
        client.send(IAC + DONT + MSSP)
        await wait_until(lambda: calls == [(MSSP, True), (MSSP, False)])


async def test_a_client_gets_the_stored_table_once_at_login() -> None:
    async with world() as (proxy, _mud, push, writer), AsyncExitStack() as stack:
        await offer_mssp(push, writer)
        push(ScriptedMud.mssp_frame(TABLE))
        await wait_until(lambda: PROTOCOLS._mssp == TABLE)
        client, conn = await join(stack, proxy, {MSSP}, login="full")
        await client.wait_for(lambda: bool(mssp_seen(client)))
        await settle()
        assert mssp_seen(client) == [TABLE]
        sent = [r for r in _messages("sent") if r.link == conn.uuid]
        assert len(sent) == 1 and sent[0].data == TABLE


async def test_a_view_only_client_gets_the_table_too() -> None:
    async with world() as (proxy, _mud, push, writer), AsyncExitStack() as stack:
        await offer_mssp(push, writer)
        push(ScriptedMud.mssp_frame(TABLE))
        await wait_until(lambda: PROTOCOLS._mssp == TABLE)
        client, _conn = await join(stack, proxy, {MSSP}, login="view")
        await client.wait_for(lambda: bool(mssp_seen(client)))
        assert mssp_seen(client) == [TABLE]


async def test_a_client_that_has_not_logged_in_or_refuses_gets_nothing() -> None:
    async with world() as (proxy, _mud, push, writer), AsyncExitStack() as stack:
        await offer_mssp(push, writer)
        push(ScriptedMud.mssp_frame(TABLE))
        await wait_until(lambda: PROTOCOLS._mssp == TABLE)
        waiting, _ = await join(stack, proxy, {MSSP})
        refusing, _ = await join(stack, proxy, set(), login="full")
        push(ScriptedMud.mssp_frame({"NAME": "second"}))
        await wait_until(lambda: PROTOCOLS._mssp == {"NAME": "second"})
        await settle()
        assert mssp_seen(waiting) == []
        assert mssp_seen(refusing) == []


async def test_a_do_after_login_gets_the_table_at_once() -> None:
    async with world() as (proxy, _mud, push, writer), AsyncExitStack() as stack:
        await offer_mssp(push, writer)
        push(ScriptedMud.mssp_frame(TABLE))
        await wait_until(lambda: PROTOCOLS._mssp == TABLE)
        client, _conn = await join(stack, proxy, set(), login="full")
        await settle()
        assert mssp_seen(client) == []
        client.send(IAC + DO + MSSP)
        await client.wait_for(lambda: bool(mssp_seen(client)))
        assert mssp_seen(client) == [TABLE]


async def test_a_table_that_arrives_later_goes_to_logged_in_clients() -> None:
    async with world() as (proxy, _mud, push, writer), AsyncExitStack() as stack:
        client, _conn = await join(stack, proxy, {MSSP}, login="full")
        await settle()
        assert mssp_seen(client) == []
        await offer_mssp(push, writer)
        push(ScriptedMud.mssp_frame(TABLE))
        await client.wait_for(lambda: bool(mssp_seen(client)))
        assert mssp_seen(client) == [TABLE]
        push(ScriptedMud.mssp_frame({"NAME": "new"}))
        await client.wait_for(lambda: len(mssp_seen(client)) == 2)
        assert mssp_seen(client)[1] == {"NAME": "new"}


async def test_core_supports_does_not_resend_mssp() -> None:
    async with world() as (proxy, _mud, push, writer), AsyncExitStack() as stack:
        await offer_mssp(push, writer)
        push(ScriptedMud.mssp_frame(TABLE))
        await wait_until(lambda: PROTOCOLS._mssp == TABLE)
        client, _conn = await join(stack, proxy, {MSSP}, login="full")
        await client.wait_for(lambda: bool(mssp_seen(client)))
        client.gmcp("Core.Supports.Set", ["Char 1"])
        await settle()
        assert len(mssp_seen(client)) == 1


async def test_mssp_from_a_client_changes_nothing(
    isolated: FakeApi, caplog: pytest.LogCaptureFixture
) -> None:
    async with proxy_server(connections=True) as proxy, AsyncExitStack() as stack:
        client, _conn = await join(stack, proxy, {MSSP}, login="full")
        with caplog.at_level(logging.DEBUG, logger="bastproxy.libs.net.negotiation"):
            client.mssp({"NAME": "from client"})
            await wait_until(
                lambda: any("Dropped an MSSP message" in r.getMessage() for r in caplog.records)
            )
        assert PROTOCOLS._mssp == {}
        assert isolated.raised == []
        assert _messages() == []

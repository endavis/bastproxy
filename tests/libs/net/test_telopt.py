"""Unit tests for plugin-owned telnet options: registration, events and sends (#566, ADR-0012)."""

from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock

import pytest
from telnetlib3.telopt import DO, GMCP, IAC, MSDP, NAWS, SB, SE, TTYPE, WILL, ZMP

from bastproxy.libs.net.protocols import EVENT_RAISE_API, PROTOCOLS
from bastproxy.libs.net.telopt import BUILTIN_OPTIONS, frame, telopt_event_specs
from bastproxy.libs.records import RMANAGER
from bastproxy.plugins._baseplugin import BasePlugin

OWNER = "plugins.test.a"
OTHER = "plugins.test.b"
REGISTER = "libs.net.protocols:telopt.register"
UNREGISTER = "libs.net.protocols:telopt.unregister"
UNREGISTER_OWNER = "libs.net.protocols:telopt.unregister.for.owner"
SEND = "libs.net.protocols:telopt.send"
GET = "libs.net.protocols:telopt.get"
FORWARD = "libs.net.protocols:telopt.forward.set"
ADD_EVENT = "plugins.core.events:event.add"


class _Opts(dict[bytes, bool]):
    def enabled(self, opt: bytes) -> bool:
        return bool(self.get(opt))


class FakeWriter:
    """Just enough of a telnet writer for the manager."""

    def __init__(self, enabled: bool = True, server: bool = False) -> None:
        self.remote_option = _Opts({bytes([102]): enabled})
        self.local_option = _Opts()
        self.pending_option = _Opts()
        self.peer_offered: set[bytes] = set()
        self.server = server
        self.closing = False
        self.link_id = "mud"
        self.raw: list[bytes] = []
        self.iacs: list[tuple[bytes, bytes]] = []

    def is_closing(self) -> bool:
        return self.closing

    def send_iac(self, data: bytes) -> None:
        self.raw.append(data)

    def iac(self, cmd: bytes, opt: bytes) -> bool:
        self.iacs.append((cmd, opt))
        return True


class FakeApi:
    """Wraps the real API; the events plugin is pretended loaded and its calls are collected."""

    def __init__(self, real: Any) -> None:
        self.real = real
        self.owner_id = real.owner_id
        self.raised: list[tuple[str, dict[str, Any]]] = []
        self.added: list[tuple[str, dict[str, str]]] = []

    def __call__(self, name: str) -> Any:
        if name == EVENT_RAISE_API:
            return self._raise
        if name == ADD_EVENT:
            return self._add
        if name == "libs.api:api.exists":
            return lambda api_name: (
                api_name in (EVENT_RAISE_API, ADD_EVENT) or self.real(name)(api_name)
            )
        return self.real(name)

    def _raise(self, event: str, event_args: dict[str, Any], calledfrom: str | None = None) -> None:
        self.raised.append((event, event_args))

    def _add(
        self,
        name: str,
        created_by: str,
        description: list[str] | None = None,
        arg_descriptions: dict[str, str] | None = None,
    ) -> None:
        self.added.append((name, arg_descriptions or {}))


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeApi]:
    """Give each test an empty record store, no registrations and a collecting API."""
    monkeypatch.setattr(RMANAGER, "record_instances", {})
    monkeypatch.setattr(RMANAGER, "records", {})
    PROTOCOLS.mud_disconnected()
    PROTOCOLS.telopt.reset()
    fake = FakeApi(PROTOCOLS.api)
    monkeypatch.setattr(PROTOCOLS, "api", fake)
    yield fake
    PROTOCOLS.mud_disconnected()
    PROTOCOLS.telopt.reset()


def _call(name: str, *args: Any, **kwargs: Any) -> Any:
    return PROTOCOLS.api(name)(*args, **kwargs)


def _records() -> list[Any]:
    return list(RMANAGER.records.get("TelnetProtocolMessage", {}).values())


# registration -----------------------------------------------------------------


def test_register_and_get() -> None:
    assert _call(REGISTER, 102, OWNER) is True
    info = _call(GET, 102)
    assert info["owner"] == OWNER
    assert (info["mud"], info["client"], info["forward"]) == (True, True, True)
    assert info["mud_enabled"] is False
    assert info["clients"] == []


def test_get_unregistered_is_none() -> None:
    assert _call(GET, 102) is None


def test_register_flags() -> None:
    assert _call(REGISTER, 102, OWNER, mud=False, client=False, forward=False)
    info = _call(GET, 102)
    assert (info["mud"], info["client"], info["forward"]) == (False, False, False)


def test_same_owner_updates_and_other_owner_is_refused() -> None:
    assert _call(REGISTER, 102, OWNER)
    assert _call(REGISTER, 102, OTHER) is False
    assert _call(REGISTER, 102, OWNER, forward=False) is True
    assert _call(GET, 102)["forward"] is False
    assert _call(GET, 102)["owner"] == OWNER


@pytest.mark.parametrize("opt", [GMCP, MSDP, NAWS, TTYPE, b"\x56", ZMP, b"\x01"])
def test_builtin_options_are_refused(opt: bytes) -> None:
    assert opt[0] in BUILTIN_OPTIONS
    assert _call(REGISTER, opt[0], OWNER) is False
    assert _call(GET, opt[0]) is None


@pytest.mark.parametrize("opt", [255, -1, 256, "102", None, 1.5, True])
def test_invalid_options_are_refused(opt: Any) -> None:
    assert _call(REGISTER, opt, OWNER) is False


def test_aardwolf_msp_and_atcp_stay_claimable() -> None:
    for opt in (102, 90, 200):
        assert opt not in BUILTIN_OPTIONS


def test_unregister_by_a_non_owner_is_refused() -> None:
    _call(REGISTER, 102, OWNER)
    assert _call(UNREGISTER, 102, OTHER) is False
    assert _call(GET, 102) is not None
    assert _call(UNREGISTER, 102, OWNER) is True
    assert _call(GET, 102) is None


def test_unregister_for_owner_keeps_other_owners() -> None:
    _call(REGISTER, 102, OWNER)
    _call(REGISTER, 150, OWNER)
    _call(REGISTER, 151, OTHER)
    _call(UNREGISTER_OWNER, OWNER)
    assert _call(GET, 102) is None
    assert _call(GET, 150) is None
    assert _call(GET, 151) is not None


def test_forward_set_only_by_the_owner() -> None:
    _call(REGISTER, 102, OWNER)
    assert _call(FORWARD, 102, False, OTHER) is False
    assert _call(GET, 102)["forward"] is True
    assert _call(FORWARD, 102, False, OWNER) is True
    assert _call(GET, 102)["forward"] is False
    assert _call(FORWARD, 150, False, OWNER) is False


def test_the_owner_defaults_to_the_caller(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(PROTOCOLS, "_caller_owner", lambda: OWNER)
    assert _call(REGISTER, 150) is True
    info = _call(GET, 150)
    assert info is not None
    assert info["owner"] == OWNER
    assert _call(FORWARD, 150, False) is True
    assert _call(UNREGISTER, 150) is True


def test_unload_hook_unregisters_the_plugin_options() -> None:
    calls: list[tuple[str, tuple[Any, ...]]] = []

    class _Api:
        def __call__(self, name: str) -> Any:
            return lambda *a, **_k: calls.append((name, a))

    plugin = MagicMock()
    plugin.plugin_id = "plugins.test.owner"
    plugin.is_reloading_f = False
    plugin.api = _Api()
    BasePlugin._phook_base_unitialize_hook(plugin)
    assert (UNREGISTER_OWNER, ("plugins.test.owner",)) in calls


def test_register_adds_the_four_events(isolated: FakeApi) -> None:
    _call(REGISTER, 102, OWNER)
    assert dict(isolated.added) == {
        "ev_libs.net.mud_telopt_102": {
            "option": "The telnet option number",
            "data": "The payload as bytes, IAC unescaped",
        },
        "ev_libs.net.mud_telopt_102_enabled": {"option": "The telnet option number"},
        "ev_libs.net.mud_telopt_102_disabled": {"option": "The telnet option number"},
        "ev_libs.net.client_telopt_102": {
            "option": "The telnet option number",
            "data": "The payload as bytes, IAC unescaped",
            "client_id": "The id of the client that sent it",
            "view_only": "True when the client is view-only",
        },
    }


def test_event_specs_are_named_by_number() -> None:
    names = [spec.name for spec in telopt_event_specs(7)]
    assert names == [
        "ev_libs.net.mud_telopt_7",
        "ev_libs.net.mud_telopt_7_enabled",
        "ev_libs.net.mud_telopt_7_disabled",
        "ev_libs.net.client_telopt_7",
    ]


# framing and sending ----------------------------------------------------------


def test_frame_matches_aardwolfs_example() -> None:
    assert frame(102, bytes([5, 1])) == bytes([255, 250, 102, 5, 1, 255, 240])
    assert frame(102, bytes([5, 1])) == IAC + SB + bytes([102, 5, 1]) + IAC + SE


def test_frame_escapes_iac() -> None:
    assert frame(102, bytes([1, 255, 2])) == bytes([255, 250, 102, 1, 255, 255, 2, 255, 240])


def test_send_writes_the_frame_and_records_it() -> None:
    _call(REGISTER, 102, OWNER)
    writer = FakeWriter()
    PROTOCOLS.mud_connected(writer)
    assert _call(SEND, 102, bytes([5, 1])) is True
    assert writer.raw == [bytes([255, 250, 102, 5, 1, 255, 240])]
    [rec] = _records()
    assert (rec.protocol, rec.package, str(rec.direction), rec.link) == (
        "TELOPT",
        "102",
        "sent",
        "mud",
    )
    assert rec.data == bytes([5, 1])


def test_send_escapes_a_payload_with_iac() -> None:
    _call(REGISTER, 102, OWNER)
    writer = FakeWriter()
    PROTOCOLS.mud_connected(writer)
    assert _call(SEND, 102, bytes([255]))
    assert writer.raw == [bytes([255, 250, 102, 255, 255, 255, 240])]


def test_send_refusals() -> None:
    assert _call(SEND, 102, b"\x01") is False  # not registered
    _call(REGISTER, 102, OWNER)
    assert _call(SEND, 102, b"\x01") is False  # no writer
    writer = FakeWriter(enabled=False)
    PROTOCOLS.mud_connected(writer)
    assert _call(SEND, 102, b"\x01") is False  # not enabled
    writer.remote_option[bytes([102])] = True
    assert _call(SEND, 102, "text") is False  # a str payload
    writer.closing = True
    assert _call(SEND, 102, b"\x01") is False  # closing
    assert writer.raw == []
    assert _records() == []


def test_register_asks_for_an_option_the_mud_offered_earlier() -> None:
    writer = FakeWriter(enabled=False)
    writer.peer_offered.add(bytes([102]))
    PROTOCOLS.mud_connected(writer)
    assert writer.iacs == []
    _call(REGISTER, 102, OWNER)
    assert writer.iacs == [(DO, bytes([102]))]


def test_register_sends_nothing_when_the_mud_never_offered() -> None:
    writer = FakeWriter(enabled=False)
    PROTOCOLS.mud_connected(writer)
    _call(REGISTER, 102, OWNER)
    assert writer.iacs == []


def test_unregister_keeps_the_mud_option_and_raises_disabled(isolated: FakeApi) -> None:
    _call(REGISTER, 102, OWNER)
    writer = FakeWriter()
    PROTOCOLS.mud_connected(writer)
    PROTOCOLS.telopt.on_enabled(writer, 102, True)
    isolated.raised.clear()
    assert _call(UNREGISTER, 102, OWNER)
    assert writer.iacs == []
    assert [e for e, _ in isolated.raised] == ["ev_libs.net.mud_telopt_102_disabled"]
    assert writer.remote_option.enabled(b"\x66")


def test_enabled_event_is_raised_once(isolated: FakeApi) -> None:
    _call(REGISTER, 102, OWNER)
    writer = FakeWriter()
    PROTOCOLS.mud_connected(writer)
    PROTOCOLS.telopt.on_enabled(writer, 102, True)
    PROTOCOLS.telopt.on_enabled(writer, 102, True)
    assert [e for e, _ in isolated.raised] == ["ev_libs.net.mud_telopt_102_enabled"]
    assert isolated.raised[0][1] == {"option": 102}


def test_mud_disconnect_raises_disabled_for_enabled_options(isolated: FakeApi) -> None:
    _call(REGISTER, 102, OWNER)
    writer = FakeWriter()
    PROTOCOLS.mud_connected(writer)
    PROTOCOLS.telopt.on_enabled(writer, 102, True)
    isolated.raised.clear()
    PROTOCOLS.mud_disconnected()
    assert [e for e, _ in isolated.raised] == ["ev_libs.net.mud_telopt_102_disabled"]


def _login(monkeypatch: pytest.MonkeyPatch, link: FakeWriter, uuid: str = "c1") -> MagicMock:
    """Put a fake logged-in connection holding ``link`` into the manager's clients."""
    link.link_id = uuid
    conn = MagicMock()
    conn.uuid = uuid
    conn.writer = link
    monkeypatch.setitem(PROTOCOLS.telopt._clients, uuid, conn)
    return conn


def test_will_offer_to_logged_in_clients_on_register(monkeypatch: pytest.MonkeyPatch) -> None:
    link = FakeWriter(server=True)
    link.remote_option.clear()
    PROTOCOLS.telopt.attach(link)
    _login(monkeypatch, link)
    _call(REGISTER, 102, OWNER)
    assert link.iacs == [(WILL, bytes([102]))]
    assert PROTOCOLS.telopt.client_options() == [102]


def test_no_offer_to_an_attached_client_that_has_not_logged_in() -> None:
    link = FakeWriter(server=True)
    link.remote_option.clear()
    PROTOCOLS.telopt.attach(link)
    _call(REGISTER, 102, OWNER)
    assert link.iacs == []


def test_client_ready_offers_registered_client_options(monkeypatch: pytest.MonkeyPatch) -> None:
    _call(REGISTER, 102, OWNER)
    _call(REGISTER, 90, OWNER, client=False)
    link = FakeWriter(server=True)
    conn = _login(monkeypatch, link)
    PROTOCOLS.telopt.client_ready(conn)
    assert link.iacs == [(WILL, bytes([102]))]


def test_client_ready_skips_closing_enabled_and_pending_links(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _call(REGISTER, 102, OWNER)
    closing = FakeWriter(server=True)
    closing.closing = True
    enabled = FakeWriter(server=True)
    enabled.local_option[bytes([102])] = True
    pending = FakeWriter(server=True)
    pending.pending_option[WILL + bytes([102])] = True
    for i, link in enumerate((closing, enabled, pending)):
        PROTOCOLS.telopt.client_ready(_login(monkeypatch, link, f"c{i}"))
    assert closing.iacs == enabled.iacs == pending.iacs == []


def test_client_logged_in_follows_the_manager_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    link = FakeWriter(server=True)
    link.link_id = "c9"
    assert PROTOCOLS.telopt.client_logged_in(link) is False
    _login(monkeypatch, link, "c9")
    assert PROTOCOLS.telopt.client_logged_in(link) is True


ENABLED_102 = "ev_libs.net.mud_telopt_102_enabled"
DISABLED_102 = "ev_libs.net.mud_telopt_102_disabled"


def test_enabled_before_writer_raises_nothing_until_mud_connected(isolated: FakeApi) -> None:
    _call(REGISTER, 102, OWNER)
    writer = FakeWriter()
    PROTOCOLS.telopt.on_enabled(writer, 102, True)
    assert isolated.raised == []
    PROTOCOLS.mud_connected(writer)
    assert [e for e, _ in isolated.raised] == [ENABLED_102]


def test_send_from_enabled_handler_reaches_the_writer(
    isolated: FakeApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    _call(REGISTER, 102, OWNER)
    writer = FakeWriter()
    results: list[bool] = []

    def raise_args(event: str, data: dict[str, Any], _key: str) -> None:
        results.append(PROTOCOLS.telopt.send(102, bytes([7, 1])))

    monkeypatch.setattr(PROTOCOLS.telopt, "_raise_args", raise_args)
    PROTOCOLS.telopt.on_enabled(writer, 102, True)
    PROTOCOLS.mud_connected(writer)
    assert results == [True]
    assert writer.raw == [frame(102, bytes([7, 1]))]


def test_mud_connected_skips_option_no_longer_enabled(isolated: FakeApi) -> None:
    _call(REGISTER, 102, OWNER)
    writer = FakeWriter(enabled=False)
    PROTOCOLS.telopt.on_enabled(writer, 102, True)
    PROTOCOLS.telopt.on_enabled(writer, 102, False)
    PROTOCOLS.mud_connected(writer)
    assert isolated.raised == []


def test_mud_connected_skips_option_not_for_the_mud(isolated: FakeApi) -> None:
    _call(REGISTER, 102, OWNER, mud=False)
    PROTOCOLS.mud_connected(FakeWriter())
    assert isolated.raised == []


def test_stale_writer_calls_are_ignored(isolated: FakeApi) -> None:
    _call(REGISTER, 102, OWNER)
    current = FakeWriter(enabled=False)
    PROTOCOLS.mud_connected(current)
    PROTOCOLS.telopt.on_enabled(FakeWriter(), 102, True)
    assert isolated.raised == []
    PROTOCOLS.telopt.on_enabled(current, 102, True)
    isolated.raised.clear()
    PROTOCOLS.telopt.on_enabled(FakeWriter(), 102, False)
    assert isolated.raised == []


def test_late_disconnect_race_gives_one_disabled_and_one_enabled(isolated: FakeApi) -> None:
    _call(REGISTER, 102, OWNER)
    old, new = FakeWriter(), FakeWriter()
    PROTOCOLS.mud_connected(old)
    PROTOCOLS.telopt.on_enabled(old, 102, True)
    PROTOCOLS.telopt.on_enabled(new, 102, True)
    PROTOCOLS.mud_disconnected()
    PROTOCOLS.mud_connected(new)
    assert [e for e, _ in isolated.raised] == [ENABLED_102, DISABLED_102, ENABLED_102]


def test_send_declines_are_logged_with_reason(
    isolated: FakeApi, caplog: pytest.LogCaptureFixture
) -> None:
    _call(REGISTER, 102, OWNER)
    secret = b"payload-bytes-xyz"
    caplog.set_level("DEBUG", logger="bastproxy.libs.net.telopt")
    manager = PROTOCOLS.telopt
    assert not manager.send("x", secret)
    assert not manager.send(103, secret)
    assert not manager.send(102, "text")
    assert not manager.send(102, secret)
    writer = FakeWriter()
    PROTOCOLS.mud_connected(writer)
    writer.closing = True
    assert not manager.send(102, secret)
    writer.closing = False
    writer.remote_option[bytes([102])] = False
    assert not manager.send(102, secret)
    assert not manager.send_client("x", secret)
    assert not manager.send_client(103, secret)
    assert not manager.send_client(102, "text")
    assert not manager.send_client(102, secret)
    text = caplog.text
    for reason in (
        "not an option number",
        "not registered",
        "not bytes",
        "no MUD writer",
        "closing",
        "has not enabled it",
        "no logged-in client",
    ):
        assert reason in text
    assert "payload-bytes-xyz" not in text


# reload keeps the MUD option (#586) -------------------------------------------


def _enabled_then_unregistered(isolated: FakeApi) -> FakeWriter:
    _call(REGISTER, 102, OWNER)
    writer = FakeWriter()
    writer.peer_offered = {bytes([102])}
    PROTOCOLS.mud_connected(writer)
    PROTOCOLS.telopt.on_enabled(writer, 102, True)
    assert _call(UNREGISTER, 102, OWNER)
    isolated.raised.clear()
    writer.iacs.clear()
    return writer


def test_reregister_raises_enabled_at_once_without_do(isolated: FakeApi) -> None:
    writer = _enabled_then_unregistered(isolated)
    assert _call(REGISTER, 102, OWNER)
    assert [e for e, _ in isolated.raised] == [ENABLED_102]
    assert writer.iacs == []
    info = _call(GET, 102)
    assert info is not None
    assert info["mud_enabled"] is True
    assert _call(SEND, 102, b"\x05\x01") is True


def test_reregister_by_another_owner_raises_enabled_at_once(isolated: FakeApi) -> None:
    writer = _enabled_then_unregistered(isolated)
    assert _call(REGISTER, 102, OTHER)
    assert [e for e, _ in isolated.raised] == [ENABLED_102]
    assert writer.iacs == []


def test_register_update_does_not_raise_enabled_twice(isolated: FakeApi) -> None:
    _call(REGISTER, 102, OWNER)
    writer = FakeWriter()
    PROTOCOLS.mud_connected(writer)
    PROTOCOLS.telopt.on_enabled(writer, 102, True)
    assert _call(REGISTER, 102, OWNER, forward=False)
    assert [e for e, _ in isolated.raised] == [ENABLED_102]


def test_register_for_clients_only_does_not_raise_enabled(isolated: FakeApi) -> None:
    PROTOCOLS.mud_connected(FakeWriter())
    assert _call(REGISTER, 102, OWNER, mud=False)
    assert isolated.raised == []


def test_reregister_asks_with_do_when_the_mud_turned_it_off(isolated: FakeApi) -> None:
    writer = _enabled_then_unregistered(isolated)
    writer.remote_option[bytes([102])] = False
    assert _call(REGISTER, 102, OWNER)
    assert writer.iacs == [(DO, bytes([102]))]
    assert isolated.raised == []

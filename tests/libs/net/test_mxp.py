"""Tests for MXP: the stripper, the modes, per-client rendering and the links (#61)."""

import asyncio
import re
import time
from collections.abc import Iterator
from contextlib import AsyncExitStack
from typing import Any
from unittest.mock import MagicMock

import pytest
from telnetlib3.telopt import DO, DONT, IAC, MXP, SB, SE, WILL

from bastproxy.libs.net import mxp
from bastproxy.libs.net.mxp import LOCKED_LINE, MxpMode
from bastproxy.libs.net.mxp import strip as strip_mxp
from bastproxy.libs.net.protocols import PROTOCOLS
from bastproxy.libs.records import RMANAGER
from bastproxy.libs.records.enums import LineType, Originated
from bastproxy.libs.records.rtypes.networkdata import NetworkDataLine
from tests.libs.net.clients import ScriptedClient, wait_until
from tests.libs.net.test_protocols_clients import join, settle, world

ESC = "\x1b"
SB_MXP = IAC + SB + MXP + IAC + SE


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(RMANAGER, "record_instances", {})
    monkeypatch.setattr(RMANAGER, "records", {})
    PROTOCOLS.mud_disconnected()
    PROTOCOLS._owner_modules.clear()
    yield
    PROTOCOLS.mud_disconnected()
    PROTOCOLS._owner_modules.clear()


# strip ---------------------------------------------------------------------------------


def test_strip_removes_a_tag() -> None:
    assert strip_mxp('You see a <send href="get sword">sword</send>.') == "You see a sword."


def test_strip_decodes_the_standard_entities() -> None:
    assert strip_mxp("&lt;&gt;&amp;&quot;&#65;") == '<>&"A'


@pytest.mark.parametrize(
    "text", ["&custom;", "&#99999999;", "a & b", "&" + "x" * 40 + ";", "&#27;", "&#;"]
)
def test_strip_keeps_other_entities(text: str) -> None:
    assert strip_mxp(text) == text


@pytest.mark.parametrize("text", ["HP < 50", "a <3 b", "x <", "1 << 2"])
def test_strip_keeps_a_lone_less_than(text: str) -> None:
    assert strip_mxp(text) == text


def test_a_quoted_greater_than_does_not_end_a_tag() -> None:
    text = "<!ELEMENT x '<color red>' FLAG=\"a>b\">after"
    assert strip_mxp(text) == "after"
    assert strip_mxp('<a b="don\'t">x</a>') == "x"


def test_an_unterminated_tag_stays() -> None:
    assert strip_mxp("go <send") == "go <send"


def test_a_tag_over_the_length_limit_stays(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mxp, "MXP_MAX_TAG_LENGTH", 10)
    assert strip_mxp("<send " + "x" * 20 + ">") == "<send " + "x" * 20 + ">"
    assert strip_mxp("<send x>") == ""


def test_many_unterminated_fragments_return() -> None:
    text = "<a" * 100_000
    start = time.monotonic()
    assert strip_mxp(text) == text
    assert time.monotonic() - start < 30


def test_mode_escapes_are_removed_and_colour_is_kept() -> None:
    text = f"{ESC}[1z{ESC}[2z{ESC}[7z{ESC}[20z{ESC}[1;31mred{ESC}[0m"
    assert strip_mxp(text) == f"{ESC}[1;31mred{ESC}[0m"


def test_a_locked_line_is_literal_but_loses_its_escapes() -> None:
    assert strip_mxp(f"{ESC}[2z<b>&lt;", MxpMode.LOCKED) == "<b>&lt;"
    assert strip_mxp("<b>&lt;x", MxpMode.LOCKED) == "<b>&lt;x"


def test_an_unlock_in_the_middle_of_a_locked_line_strips_what_follows() -> None:
    assert strip_mxp(f"<b>a{ESC}[1z<b>c", MxpMode.LOCKED) == "<b>ac"


def test_a_lock_in_the_middle_makes_what_follows_literal() -> None:
    assert strip_mxp(f"<b>a{ESC}[2z<b>c") == "a<b>c"


# modes ----------------------------------------------------------------------------------


def mode(text: str, ended: bool = True) -> MxpMode | None:
    return PROTOCOLS.mxp_line_mode(text, ended=ended, enabled=True)


def test_the_default_mode_is_open() -> None:
    assert mode("hello") is MxpMode.OPEN


def test_a_default_lock_applies_to_the_next_lines() -> None:
    assert mode(f"{ESC}[7zhi") is MxpMode.OPEN
    assert mode("next") is MxpMode.LOCKED
    assert mode(f"{ESC}[3znow") is MxpMode.LOCKED
    assert mode("after") is MxpMode.OPEN


def test_a_line_lock_lasts_one_line() -> None:
    mode(f"{ESC}[2zlocked")
    assert mode("next") is MxpMode.OPEN


def test_a_partial_line_carries_its_mode() -> None:
    mode(f"{ESC}[2zpart", ended=False)
    assert mode("rest") is MxpMode.LOCKED
    assert mode("new line") is MxpMode.OPEN


def test_disabled_returns_none_and_resets() -> None:
    mode(f"{ESC}[7z")
    assert PROTOCOLS.mxp_line_mode("x", ended=True, enabled=False) is None
    assert mode("x") is MxpMode.OPEN


def test_disconnect_resets_the_modes() -> None:
    mode(f"{ESC}[7z")
    PROTOCOLS.mud_disconnected()
    assert mode("x") is MxpMode.OPEN


def test_sync_escape() -> None:
    assert mxp.sync_escape(MxpMode.OPEN) == ""
    assert mxp.sync_escape(MxpMode.SECURE) == f"{ESC}[6z"
    assert mxp.sync_escape(MxpMode.LOCKED) == f"{ESC}[7z"


# render_for_client -----------------------------------------------------------------------


def _line(text: str, mode_: MxpMode | None, originated: Originated = Originated.MUD) -> Any:
    line = NetworkDataLine(text, originated=originated)
    line.mxp_mode = mode_
    return line


def test_render_all_four_combinations() -> None:
    tagged = _line("a <b>x</b>", MxpMode.OPEN)
    plain = _line("#BP: hi <b>", None, Originated.INTERNAL)
    assert mxp.render_for_client(tagged, True) == "a <b>x</b>"
    assert mxp.render_for_client(plain, True) == LOCKED_LINE + "#BP: hi <b>"
    assert mxp.render_for_client(tagged, False) == "a x"
    assert mxp.render_for_client(plain, False) == "#BP: hi <b>"


def test_render_literal_text_cannot_unlock_itself() -> None:
    text = 'plain \x1b[0z<send href="x">y</send> \x1b[1234567z<b>z</b>'
    plain = _line(text, None, Originated.INTERNAL)
    rendered = mxp.render_for_client(plain, True)
    assert rendered == LOCKED_LINE + 'plain <send href="x">y</send> <b>z</b>'


def test_render_literal_text_locks_every_line() -> None:
    plain = _line("one <b>\r\ntwo <i>\nthree\r\n", None, Originated.INTERNAL)
    rendered = mxp.render_for_client(plain, True)
    assert rendered == (
        LOCKED_LINE + "one <b>\r\n" + LOCKED_LINE + "two <i>\n" + LOCKED_LINE + "three\r\n"
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a\n\r<b>", "a\n" + LOCKED_LINE + "\r" + LOCKED_LINE + "<b>"),
        ("a\r<b>", "a\r" + LOCKED_LINE + "<b>"),
        ("a\n\n<b>", "a\n" + LOCKED_LINE + "\n" + LOCKED_LINE + "<b>"),
    ],
)
def test_render_literal_text_locks_after_every_line_end(text: str, expected: str) -> None:
    rendered = mxp.render_for_client(_line(text, None, Originated.INTERNAL), True)
    assert rendered == LOCKED_LINE + expected


@pytest.mark.parametrize(
    "text",
    ["\x1b[\x1b[0zz<b>", "\x1b\x1b[0z<b>", "x\x1b[\x1b[\x1b[\x1b[0zzzz<b>", "\x1b[\x1b[z<b>"],
)
def test_render_literal_text_leaves_no_mode_escape_after_nesting(text: str) -> None:
    rendered = mxp.render_for_client(_line(text, None, Originated.INTERNAL), True)
    assert isinstance(rendered, str)
    assert rendered.startswith(LOCKED_LINE)
    assert re.search(r"\x1b\[[0-9]*z", rendered[len(LOCKED_LINE) :]) is None
    assert rendered.endswith("<b>")


def test_render_literal_text_keeps_ansi_colour() -> None:
    text = "\x1b[1;31mred\x1b[0m <b>"
    assert mxp.render_for_client(_line(text, None, Originated.INTERNAL), True) == LOCKED_LINE + text


def test_render_literal_text_is_unchanged_for_a_client_without_mxp() -> None:
    text = "one \x1b[0z<b>\ntwo"
    assert mxp.render_for_client(_line(text, None, Originated.INTERNAL), False) == text


def test_strip_look_ahead_is_limited_per_line(monkeypatch: pytest.MonkeyPatch) -> None:
    used_total = 0
    real_tag_end = mxp._tag_end

    def counting(text: str, start: int, last_gt: int, budget: int) -> tuple[int, int]:
        nonlocal used_total
        end, used = real_tag_end(text, start, last_gt, budget)
        used_total += used
        return end, used

    monkeypatch.setattr(mxp, "_tag_end", counting)
    text = ("<a" * 1000 + "'>" + "x" * 2100) * 8 + ">"
    strip_mxp(text)
    assert used_total <= mxp.MXP_SCAN_FACTOR * len(text) + mxp.MXP_MAX_TAG_LENGTH


def test_strip_look_ahead_limit_leaves_normal_lines_alone() -> None:
    text = 'You see <send href="get sword" hint="a \'sharp\' sword">a sword</send>. ' * 200
    assert strip_mxp(text) == "You see a sword. " * 200


def test_render_leaves_telnet_commands_alone() -> None:
    line = NetworkDataLine(IAC + WILL + MXP, line_type=LineType.COMMAND_TELNET)
    assert mxp.render_for_client(line, True) == IAC + WILL + MXP
    assert mxp.render_for_client(line, False) == IAC + WILL + MXP


# NetworkDataLine -----------------------------------------------------------------------


def test_mxp_mode_is_tracked_locked_and_copied() -> None:
    line = _line("x", MxpMode.SECURE)
    new = NetworkDataLine("y")
    line.copy_attributes(new)
    assert new.mxp_mode is MxpMode.SECURE
    line.lock()
    with pytest.raises(RuntimeError):
        line.mxp_mode = None


def test_noansi_and_colorcoded_strip_mxp_only_with_a_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(NetworkDataLine, "api", staticmethod(lambda _name: lambda text: text))
    assert _line("a <b>x</b>", MxpMode.OPEN).noansi == "a x"
    assert _line("a <b>x</b>", MxpMode.OPEN).colorcoded == "a x"
    assert _line("a <b>x</b>", None).noansi == "a <b>x</b>"
    assert _line("a <b>x</b>", MxpMode.LOCKED).noansi == "a <b>x</b>"


# MUD link ---------------------------------------------------------------------------------


async def test_the_mud_link_accepts_mxp_and_keeps_no_data() -> None:
    async with world() as (_proxy, mud, push, writer):
        push(IAC + WILL + MXP)
        await mud.wait_for(lambda: IAC + DO + MXP in mud.received)
        await wait_until(lambda: writer.remote_option.enabled(MXP) is True)
        push(SB_MXP)
        await settle()
        assert not writer.ctx.mxp_data


async def test_mud_read_sets_mxp_mode_on_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    from bastproxy.libs.net import mud
    from bastproxy.libs.net.mud import MudConnection, MudTelnetReader

    seen: list[Any] = []

    def factory(data: Any) -> Any:
        return lambda: seen.extend(data)

    monkeypatch.setattr(mud, "ProcessDataToClient", factory)
    conn = MudConnection("127.0.0.1", "4000")
    conn.connected = True
    conn.writer = MagicMock()
    conn.writer.remote_option.enabled.return_value = True
    reader = MudTelnetReader(fn_encoding=lambda **_kw: "utf8")
    reader.feed_data(f"{ESC}[7zone\r\ntwo <b>\r\n".encode())
    reader.feed_eof()
    conn.reader = reader
    await asyncio.wait_for(conn.mud_read(), 5)
    assert [x.mxp_mode for x in seen] == [MxpMode.OPEN, MxpMode.LOCKED]


async def test_mud_read_without_a_writer_has_no_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    from bastproxy.libs.net import mud
    from bastproxy.libs.net.mud import MudConnection, MudTelnetReader

    seen: list[Any] = []
    monkeypatch.setattr(mud, "ProcessDataToClient", lambda data: lambda: seen.extend(data))
    conn = MudConnection("127.0.0.1", "4000")
    conn.connected = True
    reader = MudTelnetReader(fn_encoding=lambda **_kw: "utf8")
    reader.feed_data(b"hello <b>\r\n")
    reader.feed_eof()
    conn.reader = reader
    await asyncio.wait_for(conn.mud_read(), 5)
    assert [x.mxp_mode for x in seen] == [None]


# client links -----------------------------------------------------------------------------


async def test_an_mxp_client_is_offered_mxp_and_gets_one_sb() -> None:
    async with world() as (proxy, _mud, _push, _writer), AsyncExitStack() as stack:
        client, conn = await join(stack, proxy, {MXP})
        assert (WILL, MXP) in client.commands
        await wait_until(lambda: conn.mxp_enabled)
        await wait_until(lambda: [o for o, _ in client.subnegotiations].count(MXP) == 1)
        await settle()
        assert [o for o, _ in client.subnegotiations].count(MXP) == 1
        sent = [
            r
            for r in RMANAGER.records.get("TelnetNegotiation", {}).values()
            if r.option == "MXP" and r.command == "SB" and str(r.direction) == "sent"
        ]
        assert len(sent) == 1 and sent[0].link == conn.uuid
        client.send(IAC + DONT + MXP)
        await wait_until(lambda: not conn.mxp_enabled)


async def test_a_client_that_refuses_gets_no_sb() -> None:
    async with world() as (proxy, _mud, _push, _writer), AsyncExitStack() as stack:
        client, conn = await join(stack, proxy, set())
        await settle()
        assert MXP not in [o for o, _ in client.subnegotiations]
        assert conn.mxp_enabled is False


def _enqueue(conn: Any, line: NetworkDataLine) -> None:
    conn.send_queue.put_nowait(line)


async def _start_writers(stack: AsyncExitStack, *conns: Any) -> None:
    for conn in conns:
        conn.connected = True
        task = asyncio.create_task(conn.client_write())
        stack.callback(task.cancel)


def _text(client: ScriptedClient) -> str:
    return client.text.decode("utf8", "replace")


async def test_client_write_renders_per_client_and_logs_what_was_written(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async with world() as (proxy, _mud, _push, _writer), AsyncExitStack() as stack:
        with_mxp, conn_a = await join(stack, proxy, {MXP}, login="full")
        without, conn_b = await join(stack, proxy, set(), login="full")
        await wait_until(lambda: conn_a.mxp_enabled)
        await _start_writers(stack, conn_a, conn_b)
        with caplog.at_level("INFO"):
            for conn in (conn_a, conn_b):
                _enqueue(conn, _line("a <b>x</b>\r\n", MxpMode.OPEN))
            await with_mxp.wait_for(lambda: "a <b>x</b>" in _text(with_mxp))
            await without.wait_for(lambda: "a x" in _text(without))
        assert "<b>" not in _text(without)
        logged = [r.getMessage() for r in caplog.records if r.name == conn_b.data_logger.name]
        assert any("a x" in m and "<b>" not in m for m in logged)


async def test_two_clients_get_their_own_copy_of_one_line_and_of_bp_output() -> None:
    tagged = 'You see a <send href="get sword">sword</send> &amp; a shield.'
    async with world() as (proxy, _mud, push, writer), AsyncExitStack() as stack:
        push(IAC + WILL + MXP)
        await wait_until(lambda: writer.remote_option.enabled(MXP) is True)
        with_mxp, conn_a = await join(stack, proxy, {MXP}, login="full")
        without, conn_b = await join(stack, proxy, set(), login="full")
        await wait_until(lambda: conn_a.mxp_enabled)
        await _start_writers(stack, conn_a, conn_b)
        # what mud_read makes of the MUD's line
        line = _line(tagged, PROTOCOLS.mxp_line_mode(tagged, ended=True, enabled=True))
        line.lock()
        for conn in (conn_a, conn_b):
            _enqueue(conn, line)
        await with_mxp.wait_for(lambda: "shield" in _text(with_mxp))
        await without.wait_for(lambda: "shield" in _text(without))
        assert tagged in _text(with_mxp)
        assert "You see a sword & a shield." in _text(without)
        for conn in (conn_a, conn_b):
            _enqueue(conn, _line("#BP: hello\r\n", None, Originated.INTERNAL))
        await with_mxp.wait_for(lambda: "#BP: hello" in _text(with_mxp))
        await without.wait_for(lambda: "#BP: hello" in _text(without))
        assert f"{LOCKED_LINE}#BP: hello" in _text(with_mxp)
        assert ESC not in _text(without)


async def test_mode_sync_reaches_an_mxp_client_only_when_the_default_is_not_open() -> None:
    async with world() as (proxy, _mud, _push, _writer), AsyncExitStack() as stack:
        open_client, _ = await join(stack, proxy, {MXP}, login="full")
        await settle()
        assert f"{ESC}[7z" not in _text(open_client)
        PROTOCOLS.mxp_line_mode(f"{ESC}[7z", ended=True, enabled=True)
        locked_client, _ = await join(stack, proxy, {MXP}, login="full")
        plain_client, _ = await join(stack, proxy, set(), login="full")
        await locked_client.wait_for(lambda: f"{ESC}[7z" in _text(locked_client))
        await settle()
        assert ESC not in _text(plain_client)

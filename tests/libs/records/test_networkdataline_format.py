"""Tests for the NetworkDataLine formatting helpers (#239)."""

import pytest

from bastproxy.libs.api import API
from bastproxy.libs.records.rtypes.networkdata import NetworkDataLine

from .conftest import StandIns

ANSICODE = "plugins.core.colors:colorcode.to.ansicode"


def _identity_ansicode() -> None:
    API("test239").add("plugins.core.colors", "colorcode.to.ansicode", lambda s: s, force=True)


def test_format_internal_with_preamble(plugin_stand_ins: StandIns) -> None:
    line = NetworkDataLine("hello")
    line.format()
    assert line.line == "ANSI(@C#BP@w: hello)\r\n"


def test_format_internal_without_preamble(plugin_stand_ins: StandIns) -> None:
    line = NetworkDataLine("hello", preamble=False)
    line.format()
    assert line.line == "ANSI(hello)\r\n"
    assert "preamble.get" not in plugin_stand_ins.api_calls


def test_format_client_line_fixes_double_separator(plugin_stand_ins: StandIns) -> None:
    line = NetworkDataLine("a||b", originated="client")
    line.format()
    assert line.line == "ANSI(a|b)\r\n"


def test_format_telnet_bytes_untouched(plugin_stand_ins: StandIns) -> None:
    line = NetworkDataLine(b"\xff\xfb", originated="client", line_type="COMMAND-TELNET")
    line.format()
    assert line.line == b"\xff\xfb"


def test_format_without_line_endings(plugin_stand_ins: StandIns) -> None:
    line = NetworkDataLine("hello", originated="mud", had_line_endings=False)
    line.format()
    assert line.line == "ANSI(hello)"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a@wb", "@r@ra@w@r@rb@w"),
        ("@wa", "@r@w@r@ra@w"),
        ("plain", "@rplain@w"),
        ("", ""),
    ],
)
def test_color_line_with_color(plugin_stand_ins: StandIns, text: str, expected: str) -> None:
    _identity_ansicode()
    line = NetworkDataLine(text, originated="mud", color="@r")
    line.color_line()
    assert line.line == expected


def test_color_line_without_color_converts_only(plugin_stand_ins: StandIns) -> None:
    line = NetworkDataLine("plain", originated="mud")
    line.color_line()
    assert line.line == "ANSI(plain)"


def test_color_line_early_returns(plugin_stand_ins: StandIns) -> None:
    telnet = NetworkDataLine(b"\xff", originated="mud", line_type="COMMAND-TELNET", color="@r")
    telnet.color_line()
    assert telnet.line == b"\xff"

    API._class_api.pop(ANSICODE, None)
    line = NetworkDataLine("plain", originated="mud", color="@r")
    line.color_line()
    assert line.line == "plain"


def test_add_preamble_internal_io(plugin_stand_ins: StandIns) -> None:
    line = NetworkDataLine("hello")
    line.add_preamble()
    assert line.line == "@C#BP@w: hello"


def test_add_preamble_error(plugin_stand_ins: StandIns) -> None:
    line = NetworkDataLine("hello")
    line.add_preamble(error=True)
    assert line.line == "@R#BP@w: hello"


def test_add_preamble_skips_mud_line(plugin_stand_ins: StandIns) -> None:
    line = NetworkDataLine("hello", originated="mud")
    line.add_preamble()
    assert line.line == "hello"
    assert plugin_stand_ins.api_calls == []


def test_fix_double_command_seperator() -> None:
    doubled = NetworkDataLine("a||b", originated="client")
    doubled.fix_double_command_seperator()
    assert doubled.line == "a|b"
    assert doubled.line_modified is True

    single = NetworkDataLine("a|b", originated="client")
    single.fix_double_command_seperator()
    assert single.line == "a|b"
    assert single.line_modified is False

    raw = NetworkDataLine(b"a||b", originated="client", line_type="COMMAND-TELNET")
    raw.fix_double_command_seperator()
    assert raw.line == b"a||b"


def test_str_of_io_line_is_text(plugin_stand_ins: StandIns) -> None:
    assert str(NetworkDataLine("hello", preamble=False)) == "hello"


@pytest.mark.parametrize("raw", [b"\xff\xfb\x01", bytearray(b"\xff\xfb\x01")])
def test_str_of_telnet_bytes_line_is_lossless(
    plugin_stand_ins: StandIns, raw: bytes | bytearray
) -> None:
    line = NetworkDataLine(raw, originated="client", line_type="COMMAND-TELNET")
    assert str(line) == "\xff\xfb\x01"
    assert str(line).encode("latin-1") == b"\xff\xfb\x01"


def _telnet_line(raw: bytes | bytearray) -> NetworkDataLine:
    return NetworkDataLine(raw, originated="client", line_type="COMMAND-TELNET")


def test_bytearray_line_is_stored_as_bytes_snapshot(plugin_stand_ins: StandIns) -> None:
    raw = bytearray(b"\xff\xfb\x01")
    line = _telnet_line(raw)
    assert type(line.line) is bytes
    assert type(line.original_line) is bytes
    raw.append(0x02)
    assert line.line == b"\xff\xfb\x01"
    assert line.original_line == b"\xff\xfb\x01"


def test_bytearray_assigned_to_line_is_stored_as_bytes(plugin_stand_ins: StandIns) -> None:
    line = _telnet_line(b"\xff\xfb\x01")
    before = len(line.updates)
    new = bytearray(b"\xff\xfc\x01")
    line.line = new  # type: ignore[assignment]
    assert type(line.line) is bytes
    assert line.line == b"\xff\xfc\x01"
    assert len(line.updates) > before
    assert line.original_line == b"\xff\xfb\x01"
    new.append(0x02)
    assert line.line == b"\xff\xfc\x01"


def test_bytearray_assigned_to_locked_line_raises(plugin_stand_ins: StandIns) -> None:
    line = _telnet_line(b"\xff\xfb\x01")
    line.lock()
    with pytest.raises(RuntimeError):
        line.line = bytearray(b"\xff\xfc\x01")  # type: ignore[assignment]
    assert line.line == b"\xff\xfb\x01"

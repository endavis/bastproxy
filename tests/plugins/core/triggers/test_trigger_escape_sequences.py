"""Triggers match the visible text, whatever terminal sequences surround it (#549)."""

# Third Party
import pytest

from .conftest import Harness

OSC8_BEL = "\x1b[2J\x1b]8;;http://x\x07link\x1b]8;;\x07 \x1b[31mred"
OSC8_ST = "\x1b]8;;http://x\x1b\\link\x1b]8;;\x1b\\ \x1b[31mred"
DCS = "\x1bPq#0;2;0;0;0\x1b\\link red"


@pytest.mark.parametrize("raw", [OSC8_BEL, OSC8_ST, DCS])
def test_plain_trigger_fires_through_non_colour_sequences(harness: Harness, raw: str) -> None:
    harness.add("t", r"^link red$")
    assert harness.send(raw) == ["t"]


def test_cursor_anchored_trigger_fires(harness: Harness) -> None:
    harness.add("t", r"^You hit")
    assert harness.send("\x1b[10;1HYou hit") == ["t"]


def test_colour_trigger_fires_through_non_colour_sequences(harness: Harness) -> None:
    harness.add("t", r"^link @rred$", matchcolor=True)
    assert harness.send(OSC8_BEL) == ["t"]


def test_bold_colour_trigger_fires_after_clear(harness: Harness) -> None:
    harness.add("t", r"^@RYou hit", matchcolor=True)
    assert harness.send("\x1b[1;31m\x1b[2JYou hit") == ["t"]


def test_client_output_is_unchanged(harness: Harness) -> None:
    raw = "\x1b[10;1H\x1b[2J\x1b]8;;http://x\x07link\x1b]8;;\x07\x1bPq\x1b\\ red"
    harness.add("t", r"^link red$")
    assert harness.send(raw, ansi=raw) == ["t"]
    assert harness.line.line == raw

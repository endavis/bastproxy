"""Triggers skip the MUD's echo of a line the proxy sent, once (#545)."""

# Project
from bastproxy.libs.records.enums import LineType, Originated
from bastproxy.libs.records.rtypes.networkdata import NetworkDataLine

from .conftest import Harness


def sent(
    harness: Harness,
    text: str,
    *,
    originated: Originated = Originated.INTERNAL,
    line_type: LineType = LineType.IO,
) -> None:
    """Run one sent line through the real ev_to_mud_data_read callback."""
    line = NetworkDataLine(text, originated=originated, line_type=line_type)
    harness.current_record = {"line": line}
    harness._eventcb_record_sent()


def test_echo_of_plugin_sent_line_does_not_fire(harness: Harness) -> None:
    harness.add("t", r"^look$")
    sent(harness, "look")
    assert harness.send("look") == []
    assert harness.line.send is True


def test_second_identical_line_fires(harness: Harness) -> None:
    harness.add("t", r"^look$")
    sent(harness, "look")
    harness.send("look")
    assert harness.send("look") == ["t"]


def test_line_with_nothing_recorded_fires(harness: Harness) -> None:
    harness.add("t", r"^look$")
    assert harness.send("look") == ["t"]


def test_client_sent_line_is_not_recorded(harness: Harness) -> None:
    harness.add("t", r"^look$")
    sent(harness, "look", originated=Originated.CLIENT)
    assert harness.send("look") == ["t"]


def test_telnet_sent_line_is_not_recorded(harness: Harness) -> None:
    sent(harness, "look", line_type=LineType.COMMAND_TELNET)
    assert len(harness._echoes) == 0


def test_ansi_and_line_endings_are_stripped(harness: Harness) -> None:
    harness.add("t", r"^look$")
    sent(harness, "\x1b[31mlook\x1b[0m\r\n")
    assert harness.send("look\x1b[32m", ansi="\x1b[32mlook\x1b[0m") == []


def test_different_text_fires_and_entry_stays(harness: Harness) -> None:
    harness.add("t", r"^look")
    sent(harness, "look")
    assert harness.send("look at sword") == ["t"]
    assert harness.send("look") == []


def test_two_sends_skip_two_echoes(harness: Harness) -> None:
    harness.add("t", r"^look$")
    sent(harness, "look")
    sent(harness, "look")
    assert harness.send("look") == []
    assert harness.send("look") == []
    assert harness.send("look") == ["t"]


def test_beall_and_all_still_fire(harness: Harness) -> None:
    harness.add("t", r"^look$")
    sent(harness, "look")
    harness.listeners.add(harness.item("beall", "plugins.core.triggers").event_name)
    harness.listeners.add(harness.item("all", "plugins.core.triggers").event_name)
    assert harness.send("look") == ["beall", "all"]


def test_empty_sent_line_is_not_recorded(harness: Harness) -> None:
    sent(harness, "\r\n")
    assert len(harness._echoes) == 0

"""Triggers see MXP-stripped text when the line carries an MXP mode (#61)."""

from bastproxy.libs.net.mxp import MxpMode
from bastproxy.libs.records.enums import Originated
from bastproxy.libs.records.rtypes.networkdata import NetworkDataLine

from .conftest import Harness

TEXT = "You see a <send>sword</send>."


def _run(
    harness: Harness, line: NetworkDataLine, regex: str, matchcolor: bool = False
) -> list[str]:
    """Run ``_eventcb_check_trigger`` for one trigger on ``regex``; return what it raised."""
    harness.add(f"t{len(harness.triggers)}", regex, matchcolor=matchcolor)
    harness.line = line
    harness.current_record = {"line": line}
    before = len(harness.raised)
    harness._eventcb_check_trigger()
    return [args["trigger_name"] for _name, args in harness.raised[before:]]


def _line(text: str, mode: MxpMode | None) -> NetworkDataLine:
    line = NetworkDataLine(text, originated=Originated.MUD)
    line.mxp_mode = mode
    return line


def test_a_trigger_fires_for_a_tagged_line(harness: Harness) -> None:
    assert len(_run(harness, _line(TEXT, MxpMode.OPEN), r"^You see a sword\.$")) == 1


def test_a_matchcolor_trigger_fires_without_the_tags(harness: Harness) -> None:
    assert (
        len(_run(harness, _line(TEXT, MxpMode.OPEN), r"^You see a sword\.$", matchcolor=True)) == 1
    )


def test_a_line_without_a_mode_keeps_its_tags(harness: Harness) -> None:
    assert _run(harness, _line(TEXT, None), r"^You see a sword\.$") == []
    assert len(_run(harness, _line(TEXT, None), r"^You see a <send>sword</send>\.$")) == 1

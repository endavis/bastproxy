"""Triggers see MXP-stripped text when the line carries an MXP mode (#61)."""

import re
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs.net.mxp import MxpMode
from bastproxy.libs.records.enums import Originated
from bastproxy.libs.records.rtypes.networkdata import NetworkDataLine
from bastproxy.plugins.core.colors.plugin._colors import ColorsPlugin
from bastproxy.plugins.core.triggers.plugin._triggers import TriggersPlugin

TEXT = "You see a <send>sword</send>."


@pytest.fixture(autouse=True)
def colors_api(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give lines the real colors code for ``noansi`` and ``colorcoded``."""
    colors = MagicMock()
    colors.plugin_id = "plugins.core.colors"
    table = {
        "plugins.core.colors:ansicode.strip": lambda text: ColorsPlugin._api_ansicode_strip(
            colors, text
        ),
        "plugins.core.colors:ansicode.to.colorcode": lambda text: (
            ColorsPlugin._api_ansicode_to_colorcode(colors, text)
        ),
    }
    monkeypatch.setattr(NetworkDataLine, "api", staticmethod(lambda name: table[name]))


def _run(line: NetworkDataLine, regex: str, matchcolor: bool = False) -> list[Any]:
    """Run ``_eventcb_check_trigger`` for one trigger on ``regex``; return what it raised."""
    raised: list[Any] = []
    quiet = SimpleNamespace(raisetrigger=lambda _args: None)
    trigger = SimpleNamespace(
        enabled=True,
        matchcolor=matchcolor,
        original_regex_compiled=re.compile(regex),
        argtypes=None,
        stopevaluating=False,
        raisetrigger=raised.append,
    )
    stub = MagicMock()
    stub.plugin_id = "plugins.core.triggers"
    stub.beall_id, stub.all_id, stub.emptyline_id = "beall", "all", "empty"
    stub.triggers = {"beall": quiet, "all": quiet, "empty": quiet, "t1": trigger}
    stub.regexes = {"reg_1": {"hits": 0, "triggers": ["t1"]}}
    stub.created_regex = {"created_regex_compiled": re.compile(f"(?P<reg_1>{regex})")}
    stub.process_match = lambda data_line, ids: TriggersPlugin.process_match(stub, data_line, ids)
    stub.api = lambda name: lambda: {"line": line}
    TriggersPlugin._eventcb_check_trigger(stub)
    return raised


def _line(text: str, mode: MxpMode | None) -> NetworkDataLine:
    line = NetworkDataLine(text, originated=Originated.MUD)
    line.mxp_mode = mode
    return line


def test_a_trigger_fires_for_a_tagged_line() -> None:
    assert len(_run(_line(TEXT, MxpMode.OPEN), r"^You see a sword\.$")) == 1


def test_a_matchcolor_trigger_fires_without_the_tags() -> None:
    assert len(_run(_line(TEXT, MxpMode.OPEN), r"^You see a sword\.$", matchcolor=True)) == 1


def test_a_line_without_a_mode_keeps_its_tags() -> None:
    assert _run(_line(TEXT, None), r"^You see a sword\.$") == []
    assert len(_run(_line(TEXT, None), r"^You see a <send>sword</send>\.$")) == 1

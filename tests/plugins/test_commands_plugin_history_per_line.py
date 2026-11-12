"""A line's history decision does not reach the next line of the same input (#390)."""

from typing import Any
from unittest.mock import MagicMock

from bastproxy.libs.records.rtypes.networkdata import NetworkDataLine
from bastproxy.plugins.core.commands.plugin._commands import CommandsPlugin


def _run_input(lines: list[str], unknown: set[str]) -> list[str]:
    """Run each line through `_eventcb_check_for_command` sharing one flag.

    Returns the lines recorded in the history. A line in `unknown` behaves like
    an unknown `#bp` command: it sets the shared flag to False.
    """
    shared: dict[str, Any] = {"showinhistory": True, "client_id": None}
    current: dict[str, Any] = {}
    recorded: list[str] = []

    def api(name: str) -> Any:
        if name == "plugins.core.settings:setting.get":
            return lambda plugin_id, key: "#bp"
        if name == "plugins.core.events:event.current.record.get":
            return lambda: current["record"]
        raise AssertionError(name)

    stub = MagicMock()
    stub.plugin_id = "plugins.core.commands"
    stub.api = api
    stub.current_input_event = None
    stub.add_command_to_history.side_effect = recorded.append

    def run_internal() -> None:
        record = current["record"]
        record["showinhistory"] = record["line"].line not in unknown

    stub.run_internal_command_from_event.side_effect = run_internal

    for text in lines:
        # one record per line, but the flag lives in the shared event arguments
        record = _SharedFlagRecord(shared, NetworkDataLine(text, originated="client"))
        current["record"] = record
        CommandsPlugin._eventcb_check_for_command(stub)
    return recorded


class _SharedFlagRecord(dict):
    """Record whose `showinhistory` is stored in a dict shared across lines."""

    def __init__(self, shared: dict[str, Any], line: NetworkDataLine) -> None:
        super().__init__()
        self._shared = shared
        self["line"] = line

    def __getitem__(self, key: str) -> Any:
        if key == "showinhistory":
            return self._shared[key]
        return super().__getitem__(key)

    def __setitem__(self, key: str, value: Any) -> None:
        if key == "showinhistory":
            self._shared[key] = value
        else:
            super().__setitem__(key, value)


def test_line_after_unknown_command_is_recorded() -> None:
    """`#bp.nope.x|lookD` records `lookD`; the unknown command itself is not."""
    assert _run_input(["#bp.nope.x", "lookD"], {"#bp.nope.x"}) == ["lookD"]


def test_line_before_unknown_command_is_recorded() -> None:
    """`lookC|#bp.nope.x` still records `lookC`."""
    assert _run_input(["lookC", "#bp.nope.x"], {"#bp.nope.x"}) == ["lookC"]


def test_lines_around_unknown_command_are_recorded() -> None:
    """Every ordinary line is recorded whatever comes before it."""
    lines = ["lookA", "#bp.nope.x", "lookB", "#bp.nope.y", "lookC"]
    assert _run_input(lines, {"#bp.nope.x", "#bp.nope.y"}) == ["lookA", "lookB", "lookC"]

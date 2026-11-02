# Project: bastproxy
# Filename: tests/plugins/test_watch_plugin.py
#
# File Description: Tests for the watch plugin's client input matching
#
# By: Bast
"""Unit tests for `WatchPlugin._eventcb_check_command`.

Issue #55: the callback passed the `NetworkDataLine` record to `re.match`
instead of its text, so a registered watch never fired.

"""

import re
from typing import Any
from unittest.mock import MagicMock

from bastproxy.libs.records.rtypes.networkdata import NetworkDataLine
from bastproxy.plugins.core.watch.plugin._watch import WatchPlugin


def _run(line: NetworkDataLine, regex: str = r"^say (?P<what>\w+)") -> tuple[Any, MagicMock]:
    """Run the callback against `line` with one watch registered.

    Returns the stub plugin and the `raise.event` mock.
    """
    raise_event = MagicMock()

    def api(name: str) -> Any:
        if name == "plugins.core.events:get.current.event.record":
            return lambda: {"line": line}
        if name == "plugins.core.events:raise.event":
            return raise_event
        raise AssertionError(name)

    stub = MagicMock()
    stub.plugin_id = "plugins.core.watch"
    stub.api = api
    stub.watch_data = {
        "sayw": {
            "compiled": re.compile(regex),
            "eventname": "ev_watch_sayw",
            "hits": 0,
        }
    }
    WatchPlugin._eventcb_check_command(stub)
    return stub, raise_event


def test_matching_line_raises_event_with_text() -> None:
    """A matching client line raises the watch event with text, not the record."""
    stub, raise_event = _run(NetworkDataLine("say hi", originated="client"))

    assert stub.watch_data["sayw"]["hits"] == 1
    raise_event.assert_called_once()
    assert raise_event.call_args.args == ("ev_watch_sayw",)
    match_args = raise_event.call_args.kwargs["event_args"]
    assert match_args["data"] == "say hi"
    assert isinstance(match_args["data"], str)
    assert match_args["matched"] == {"what": "hi"}
    assert match_args["cmdname"] == "cmd_sayw"


def test_non_matching_line_does_not_fire() -> None:
    """A line that does not match leaves hits at zero and raises nothing."""
    stub, raise_event = _run(NetworkDataLine("look", originated="client"))

    assert stub.watch_data["sayw"]["hits"] == 0
    raise_event.assert_not_called()


def test_telnet_command_line_is_skipped() -> None:
    """A COMMAND-TELNET line is not matched even if its text would match."""
    stub, raise_event = _run(
        NetworkDataLine("say hi", originated="client", line_type="COMMAND-TELNET"),
        regex=r"^say",
    )

    assert stub.watch_data["sayw"]["hits"] == 0
    raise_event.assert_not_called()

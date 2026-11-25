# Project: bastproxy
# Filename: tests/plugins/client/actions/test_actions_send_input_path.py
#
# File Description: Input-path test for the mud send target of actions
#
# By: Bast
"""Input-path test for an action with the `mud` target (#774)."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from .conftest import StandIns
from .test_actions_input_path import _wire


@pytest.mark.usefixtures("split_regex")
def test_mud_action_sends_to_the_mud_without_dispatching(
    plugin_stand_ins: StandIns, tmp_path: Path
) -> None:
    """A `mud` action sends its raw text to the connection and runs no command."""
    wired = _wire(plugin_stand_ins, tmp_path)
    assert wired.actions._api_action_add("a", r"(.*)", "say %1|#bp.x", send="mud")
    record = {
        "trigger_name": "a",
        "groups": ("#bp.y",),
        "matches": {},
        "line": SimpleNamespace(noansi="x"),
    }
    wired.actions.api.table["plugins.core.events:event.current.record.get"] = lambda: record
    wired.actions._trigger_matched()
    assert wired.sent == ["say #bp.y|#bp.x"]
    assert wired.dispatched == []
    assert wired.history == []

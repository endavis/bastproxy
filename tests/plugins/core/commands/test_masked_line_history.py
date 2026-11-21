"""A line typed with echo off is not recorded in history, lastcmd or the debug log (#695)."""

import logging
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from bastproxy.plugins.core.commands.plugin import _commands
from bastproxy.plugins.core.commands.plugin._commands import CommandsPlugin

PID = "plugins.core.commands"
TEXT = "secret-line-text"


def _stub(line: str, mask_log: bool) -> tuple[MagicMock, dict[str, Any], dict[str, Any]]:
    settings: dict[str, Any] = {
        "lastcmd": "previous",
        "cmdcount": 3,
        "cmdprefix": "#bp",
        "spamcount": 20,
        "historysize": 10,
    }
    record: dict[str, Any] = {
        "line": SimpleNamespace(line=line, mask_log=mask_log, internal=False),
        "showinhistory": True,
    }
    stub = MagicMock()
    stub.plugin_id = PID
    stub.current_input_event = None
    stub.command_history_data = []

    def api(name: str) -> Any:
        if name == "plugins.core.settings:setting.get":
            return lambda _pid, key: settings[key]
        if name == "plugins.core.settings:setting.set":
            return lambda _pid, key, value: settings.__setitem__(key, value)
        if name == "plugins.core.events:event.current.record.get":
            return lambda: record
        raise AssertionError(name)

    stub.api = api
    stub.pass_through_command_from_event = lambda: CommandsPlugin.pass_through_command_from_event(
        stub
    )
    stub.add_command_to_history = lambda cmd: CommandsPlugin.add_command_to_history(stub, cmd)
    return stub, settings, record


def _check(stub: MagicMock) -> None:
    CommandsPlugin._eventcb_check_for_command(stub)


def test_masked_line_is_not_added_to_history() -> None:
    stub, _, _ = _stub(TEXT, mask_log=True)
    _check(stub)
    assert stub.command_history_data == []
    stub.command_history_dict.sync.assert_not_called()


def test_masked_line_is_not_stored_in_lastcmd_and_count_resets() -> None:
    stub, settings, _ = _stub(TEXT, mask_log=True)
    _check(stub)
    assert settings["lastcmd"] == ""
    assert settings["cmdcount"] == 0


def _logged_text(line: str, mask_log: bool, caplog: pytest.LogCaptureFixture) -> str:
    """Run the check with DEBUG captured (get_logger would pin the level to INFO)."""
    stub, _, _ = _stub(line, mask_log=mask_log)
    test_logger = logging.getLogger("test_masked_line_history")
    with (
        caplog.at_level(logging.DEBUG, logger=test_logger.name),
        patch.object(_commands, "get_logger", return_value=test_logger),
        patch.object(_commands, "SendDataDirectlyToMud"),
    ):
        _check(stub)
    return caplog.text


def test_masked_line_does_not_appear_in_debug_log(caplog: pytest.LogCaptureFixture) -> None:
    assert TEXT not in _logged_text(TEXT, True, caplog)


def test_unmasked_line_is_in_debug_log(caplog: pytest.LogCaptureFixture) -> None:
    """The capture sees the line when it is not masked, so the masked case is not vacuous."""
    assert TEXT in _logged_text(TEXT, False, caplog)


def test_masked_line_never_triggers_repeat_check() -> None:
    stub, settings, _ = _stub("", mask_log=True)
    settings["lastcmd"] = ""
    settings["cmdcount"] = 19
    with patch.object(_commands, "SendDataDirectlyToMud") as sender:
        _check(stub)
    sender.assert_not_called()
    assert settings["cmdcount"] == 0


def test_unmasked_line_is_still_recorded() -> None:
    stub, settings, _ = _stub("look", mask_log=False)
    _check(stub)
    assert stub.command_history_data == ["look"]
    stub.command_history_dict.sync.assert_called_once_with()
    assert settings["lastcmd"] == "look"
    assert settings["cmdcount"] == 0

"""Tests for #782: the command prefix matches in any case."""

# Standard Library
from typing import Any
from unittest.mock import MagicMock

# 3rd Party
import pytest

# Project
from bastproxy.libs.records.rtypes.networkdata import NetworkDataLine
from bastproxy.plugins.core.commands.plugin._commands import CommandSplit, CommandsPlugin

from .test_find_command_lookup import _stub


def _run(text: str) -> MagicMock:
    line = NetworkDataLine(text, originated="client")
    record: dict[str, Any] = {"line": line, "showinhistory": False}

    def api(name: str) -> Any:
        if name == "plugins.core.settings:setting.get":
            return lambda plugin_id, key: "#bp"
        if name == "plugins.core.events:event.current.record.get":
            return lambda: record
        raise AssertionError(name)

    stub = MagicMock()
    stub.plugin_id = "plugins.core.commands"
    stub.api = api
    stub.current_input_event = None
    CommandsPlugin._eventcb_check_for_command(stub)
    return stub


@pytest.mark.parametrize("text", ["#BP.core.proxy.info", "#Bp.core.proxy.info", "  #BP.x"])
def test_upper_case_prefix_runs_a_command(text: str) -> None:
    stub = _run(text)
    stub.run_internal_command_from_event.assert_called_once()
    stub.pass_through_command_from_event.assert_not_called()


def test_prefix_later_in_the_line_passes_through() -> None:
    stub = _run("say #bp")
    stub.pass_through_command_from_event.assert_called_once()
    stub.run_internal_command_from_event.assert_not_called()


def test_find_command_normalizes_the_prefix() -> None:
    stub = _stub()
    stub.find_command_split_command_string.return_value = CommandSplit(
        False, "", "", "Bad Package", ["core", ""], ""
    )
    CommandsPlugin.find_command(stub, "#BP.core.proxy.info")
    stub.find_command_split_command_string.assert_called_once_with("#bp.core.proxy.info")


@pytest.mark.parametrize("line", ["#BP", "#BP.", "#Bp.plugins", "#BP.plugins."])
def test_prefix_only_in_any_case_shows_package_help(line: str) -> None:
    stub = _stub()
    stub.find_command_only_prefix.return_value = ["packages"]
    result = CommandsPlugin.find_command(stub, line)
    assert result.message == ["packages"]

"""Missing-argument messages reach the user and records.list -c needs a value (#685)."""

import argparse
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.plugins.debug.plugins.plugin._plugins import PluginsPlugin
from bastproxy.plugins.debug.records.plugin import _records
from bastproxy.plugins.debug.records.plugin._records import RecordPlugin

PLUGIN_COMMANDS = [
    "_command_dump",
    "_command_hooks",
    "_command_summary",
    "_command_detail",
    "_command_stats",
]


def _parser(func: Any) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    for arg in func.command_data.arguments:
        parser.add_argument(*arg["args"], **arg["kwargs"])
    return parser


@pytest.mark.parametrize("command", PLUGIN_COMMANDS)
def test_plugin_argument_is_optional(command: str) -> None:
    assert _parser(getattr(PluginsPlugin, command)).parse_args([]).plugin == ""


@pytest.mark.parametrize("command", PLUGIN_COMMANDS)
def test_empty_plugin_gives_message(command: str) -> None:
    stub = MagicMock()

    def api(name: str) -> Callable[..., Any]:
        if name == "plugins.core.commands:command.current.args.get":
            return lambda: {"plugin": "", "object": "", "detailed": False}
        raise AssertionError(name)

    stub.api = api
    result = getattr(PluginsPlugin, command)(stub)
    assert result.success is False
    expected = (
        "Please enter a plugin id" if command == "_command_dump" else "Please enter a plugin name"
    )
    assert result.message == [expected]


def test_list_recordtype_optional() -> None:
    assert _parser(RecordPlugin._command_list).parse_args([]).recordtype == ""


def test_list_count_default_and_value() -> None:
    parser = _parser(RecordPlugin._command_list)
    assert parser.parse_args(["NetworkData"]).count == 10
    assert parser.parse_args(["NetworkData", "-c", "5"]).count == 5


def test_list_count_requires_value() -> None:
    with pytest.raises(SystemExit):
        _parser(RecordPlugin._command_list).parse_args(["NetworkData", "-c"])


def test_list_without_type_shows_valid_types(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_records.RMANAGER, "get_types", lambda: [("NetworkData", 1)])
    stub = MagicMock()

    def api(name: str) -> Callable[..., Any]:
        if name == "plugins.core.commands:output.line.length.get":
            return lambda: 10
        if name == "plugins.core.settings:setting.get":
            return lambda *_: "@x"
        if name == "plugins.core.commands:command.current.args.get":
            return lambda: {"recordtype": "", "count": 10}
        raise AssertionError(name)

    stub.api = api
    result = RecordPlugin._command_list(stub)
    assert result.message == ["Valid Types:", "    NetworkData"]

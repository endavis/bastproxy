"""Tests for #778: a plugin's default command runs on a bare ``#bp.<plugin>``."""

# Standard Library
import logging
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

# 3rd Party
import pytest

# Project
from bastproxy.plugins.core.commands.libs import _command
from bastproxy.plugins.core.commands.libs._command import CommandClass
from bastproxy.plugins.core.commands.plugin import _commands
from bastproxy.plugins.core.commands.plugin._commands import CommandSplit, CommandsPlugin

from .test_add_by_func_bad_placeholder import _FakeCommands, _FakeTarget, _make
from .test_find_command_lookup import PID, _stub

PLUGIN = "plugins.client.aliases"


def _item(name: str, *, default: bool) -> Any:
    return SimpleNamespace(
        default=default, show_in_history=True, full_cmd=f"{PLUGIN}.{name}", name=name
    )


def _find_stub(items: dict[str, Any], match: str | None = None) -> MagicMock:
    stub = _stub(
        {
            f"{PID}:command.data.get": lambda _pid: items,
            "plugins.core.fuzzy:string.match.best": lambda *_a, **_k: match,
        }
    )
    stub.error_command_not_found_in_plugin.return_value = ["plugin help"]
    return stub


def _split(command: str, args: str) -> CommandSplit:
    return CommandSplit(True, "plugins.client", PLUGIN, "", ["client", "aliases", command], args)


def test_bare_plugin_runs_default() -> None:
    items = {"add": _item("add", default=False), "list": _item("list", default=True)}
    stub = _find_stub(items)
    stub.find_command_split_command_string.return_value = _split("", "")

    result = CommandsPlugin.find_command(stub, "#bp.client.aliases")

    assert result.command is items["list"]
    assert result.message == []
    assert result.notes.endswith("(default)")
    stub.error_command_not_found_in_plugin.assert_not_called()


def test_default_gets_the_arguments() -> None:
    items = {"list": _item("list", default=True)}
    stub = _find_stub(items)
    stub.find_command_split_command_string.return_value = _split("", "orc")

    result = CommandsPlugin.find_command(stub, "#bp.client.aliases orc")

    assert result.command is items["list"]
    assert result.args == "orc"


def test_no_default_shows_plugin_help() -> None:
    stub = _find_stub({"list": _item("list", default=False)})
    stub.find_command_split_command_string.return_value = _split("", "")
    stub.api = _stub(
        {
            f"{PID}:command.data.get": lambda _pid: {"list": _item("list", default=False)},
            "plugins.core.fuzzy:string.match.best": lambda *_a, **_k: None,
        }
    ).api

    result = CommandsPlugin.find_command(stub, "#bp.client.aliases")

    assert result.command is None
    assert result.message == ["plugin help"]
    stub.error_command_not_found_in_plugin.assert_called_once_with(PLUGIN, "")


def test_lone_help_shows_plugin_help_not_default() -> None:
    stub = _find_stub({"list": _item("list", default=True)})
    stub.find_command_split_command_string.return_value = _split("", "help")

    result = CommandsPlugin.find_command(stub, "#bp.client.aliases help")

    assert result.command is None
    assert result.message == ["plugin help"]


def test_typed_command_wins_over_default() -> None:
    items = {"add": _item("add", default=False), "list": _item("list", default=True)}
    stub = _find_stub(items, match="add")
    stub.find_command_split_command_string.return_value = _split("add", "x y")

    result = CommandsPlugin.find_command(stub, "#bp.client.aliases add x y")

    assert result.command is items["add"]


def _update_stub() -> MagicMock:
    stub = MagicMock()
    stub.plugin_id = "plugins.core.commands"
    stub.api = MagicMock()
    stub.api.startup = True
    stub.api.side_effect = lambda name: lambda *a, **k: True
    stub.command_data = {}
    stub.saved_command_counts = {}
    stub.saved_command_stats = {}
    return stub


def _cmd(*, default: bool) -> Any:
    return SimpleNamespace(count=0, stats=None, default=default)


def test_second_default_is_registered_without_the_flag(
    caplog: pytest.LogCaptureFixture,
) -> None:
    stub = _update_stub()
    first = _cmd(default=True)
    second = _cmd(default=True)
    stub.command_data[PLUGIN] = {"a": first}

    with caplog.at_level(logging.ERROR):
        assert CommandsPlugin.update_command(stub, PLUGIN, "b", second) is True

    assert stub.command_data[PLUGIN]["b"] is second
    assert second.default is False
    assert first.default is True
    assert any(
        r.levelno == logging.ERROR and PLUGIN in r.getMessage() and "a" in r.getMessage()
        for r in caplog.records
    )


def test_reregistering_the_same_default_is_not_a_conflict(
    caplog: pytest.LogCaptureFixture,
) -> None:
    stub = _update_stub()
    stub.command_data[PLUGIN] = {"a": _cmd(default=True)}
    again = _cmd(default=True)

    with caplog.at_level(logging.ERROR):
        CommandsPlugin.update_command(stub, PLUGIN, "a", again)

    assert again.default is True
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


def test_command_class_default_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_command, "API", MagicMock())
    parser = MagicMock()
    assert CommandClass("p", "n", lambda: None, parser).default is False
    assert CommandClass("p", "n", lambda: None, parser, default=True).default is True


def test_add_command_default_reaches_command_class(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[Any] = []

    class _Capture:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.kwargs = kwargs
            seen.append(self)

    monkeypatch.setattr(_commands, "CommandClass", _Capture)
    monkeypatch.setattr(_commands, "log_to", lambda *args, **kwargs: None)
    target = _FakeTarget()
    func = _make(target, "_command_list")
    func.__func__.command_data.command["kwargs"]["default"] = True  # type: ignore[attr-defined]

    fake = _FakeCommands()
    CommandsPlugin._api_command_add_by_func(fake, func)

    assert seen[0].kwargs["default"] is True

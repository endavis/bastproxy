"""Tests for #862: default commands are gone, a bare plugin shows its help."""

# Standard Library
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

# 3rd Party
import pytest

# Project
from bastproxy.plugins.core.commands.libs import _command
from bastproxy.plugins.core.commands.libs._command import CommandClass
from bastproxy.plugins.core.commands.libs._utils import AddCommand
from bastproxy.plugins.core.commands.plugin._commands import CommandSplit, CommandsPlugin

from .test_find_command_lookup import PID, _stub

PLUGIN = "plugins.client.aliases"


def _item(name: str) -> Any:
    return SimpleNamespace(show_in_history=True, full_cmd=f"{PLUGIN}.{name}", name=name)


def _find_stub(items: dict[str, Any], match: str | None = None) -> MagicMock:
    fuzzy = MagicMock(return_value=match)
    stub = _stub(
        {
            f"{PID}:command.data.get": lambda _pid: items,
            "plugins.core.fuzzy:string.match.best": fuzzy,
        }
    )
    stub.error_command_not_found_in_plugin.return_value = ["plugin help"]
    stub.fuzzy = fuzzy
    return stub


def _split(command: str, args: str) -> CommandSplit:
    return CommandSplit(True, "plugins.client", PLUGIN, "", ["client", "aliases", command], args)


def test_bare_plugin_shows_help() -> None:
    stub = _find_stub({"list": _item("list")})
    stub.find_command_split_command_string.return_value = _split("", "")

    result = CommandsPlugin.find_command(stub, "#bp.client.aliases")

    assert result.command is None
    assert result.message == ["plugin help"]
    stub.error_command_not_found_in_plugin.assert_called_once_with(PLUGIN, "")


def test_bare_plugin_with_args_shows_help() -> None:
    stub = _find_stub({"list": _item("list")})
    stub.find_command_split_command_string.return_value = _split("", "orc")

    result = CommandsPlugin.find_command(stub, "#bp.client.aliases orc")

    assert result.command is None
    assert result.message == ["plugin help"]


def test_bare_plugin_help_word_shows_help() -> None:
    stub = _find_stub({"list": _item("list")})
    stub.find_command_split_command_string.return_value = _split("", "help")

    result = CommandsPlugin.find_command(stub, "#bp.client.aliases help")

    assert result.command is None
    assert result.message == ["plugin help"]
    stub.fuzzy.assert_not_called()


def test_bare_plugin_with_one_command_shows_help() -> None:
    items = {"list": _item("list")}
    stub = _find_stub(items, match="list")
    stub.find_command_split_command_string.return_value = _split("", "")

    result = CommandsPlugin.find_command(stub, "#bp.client.aliases")

    assert result.command is None
    assert result.message == ["plugin help"]
    stub.fuzzy.assert_not_called()


def test_typed_command_still_found() -> None:
    items = {"add": _item("add"), "list": _item("list")}
    stub = _find_stub(items, match="add")
    stub.find_command_split_command_string.return_value = _split("add", "x y")

    result = CommandsPlugin.find_command(stub, "#bp.client.aliases add x y")

    assert result.command is items["add"]
    assert result.args == "x y"


@pytest.mark.parametrize("value", [True, False])
def test_add_command_rejects_default(value: bool) -> None:
    with pytest.raises(TypeError, match="default"):
        AddCommand(default=value)


def test_add_command_accepts_other_kwargs() -> None:
    @AddCommand(literal_args=True, shelp="short")
    def _command_x() -> None:
        pass

    kwargs = _command_x.command_data.command["kwargs"]
    assert kwargs["literal_args"] is True
    assert kwargs["shelp"] == "short"


def test_command_class_rejects_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_command, "API", MagicMock())
    parser = MagicMock()
    with pytest.raises(TypeError):
        CommandClass("p", "n", lambda: None, parser, default=True)  # type: ignore[call-arg]
    assert not hasattr(CommandClass("p", "n", lambda: None, parser), "default")

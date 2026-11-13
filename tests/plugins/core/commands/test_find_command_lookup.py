"""Lookup of a command from client input: find_command and its split helper (#401)."""

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins.core.commands.plugin._commands import (
    CommandLookup,
    CommandSplit,
    CommandsPlugin,
)

PID = "plugins.core.commands"


def _stub(handlers: dict[str, Callable[..., Any]] | None = None) -> MagicMock:
    """Build a plugin stub whose api returns `handlers[name]` or a no-op returning []."""
    table: dict[str, Callable[..., Any]] = {
        "plugins.core.settings:setting.get": lambda _pid, _key: "#bp",
    }
    table.update(handlers or {})
    stub = MagicMock()
    stub.plugin_id = PID

    def api(name: str) -> Callable[..., Any]:
        return table.get(name, lambda *_a, **_k: [])

    stub.api = api
    return stub


def test_only_prefix_returns_package_help() -> None:
    """A bare prefix shows the package list and finds no command."""
    stub = _stub()
    stub.find_command_only_prefix.return_value = ["packages"]

    for line in ("#bp", "#bp.", "#bp.plugins", "#bp.plugins."):
        result = CommandsPlugin.find_command(stub, line)
        assert result == CommandLookup(None, "", False, "Proxy Help", ["packages"])
    stub.find_command_split_command_string.assert_not_called()


def test_bad_package_shows_package_error() -> None:
    """A split that reports `Bad Package` returns the package error page."""
    stub = _stub()
    stub.find_command_split_command_string.return_value = CommandSplit(
        False,
        "",
        "",
        "Bad Package",
        ["zzz", ""],
        "",
    )
    stub.error_package_not_found.return_value = ["bad package page"]

    result = CommandsPlugin.find_command(stub, "#bp.zzz")

    assert result.command is None
    assert result.notes == "#bp.zzz"
    assert result.message == ["bad package page"]
    stub.error_package_not_found.assert_called_once_with("zzz")


def test_bad_plugin_shows_plugin_error() -> None:
    """A split that reports `Bad Plugin` returns the plugin error page for the package."""
    stub = _stub()
    stub.find_command_split_command_string.return_value = CommandSplit(
        False,
        "plugins.core",
        "",
        "Bad Plugin",
        ["core", "zzz"],
        "",
    )
    stub.error_plugin_not_found.return_value = ["bad plugin page"]

    result = CommandsPlugin.find_command(stub, "#bp.core.zzz")

    assert result.command is None
    assert result.message == ["bad plugin page"]
    stub.error_plugin_not_found.assert_called_once_with("zzz", "plugins.core")


def test_unknown_command_shows_command_error() -> None:
    """No fuzzy match in the plugin returns the plugin's command list page."""
    stub = _stub(
        {
            f"{PID}:command.data.get": lambda _pid: {"list": SimpleNamespace()},
            "plugins.core.fuzzy:string.match.best": lambda *_a, **_k: None,
        }
    )
    stub.find_command_split_command_string.return_value = CommandSplit(
        True,
        "plugins.core",
        "plugins.core.commands",
        "",
        ["core", "commands", "zzz"],
        "",
    )
    stub.error_command_not_found_in_plugin.return_value = ["no such command"]

    result = CommandsPlugin.find_command(stub, "#bp.core.commands.zzz")

    assert result.command is None
    assert result.message == ["no such command"]
    stub.error_command_not_found_in_plugin.assert_called_once_with("plugins.core.commands", "zzz")


def test_found_command_returns_command_args_and_history_flag() -> None:
    """A match returns the command, its arguments and its show_in_history flag."""
    item: Any = SimpleNamespace(show_in_history=False, full_cmd="plugins.core.commands.list")
    stub = _stub(
        {
            f"{PID}:command.data.get": lambda _pid: {"list": item},
            "plugins.core.fuzzy:string.match.best": lambda *_a, **_k: "list",
        }
    )
    stub.find_command_split_command_string.return_value = CommandSplit(
        True,
        "plugins.core",
        "plugins.core.commands",
        "",
        ["core", "commands", "li"],
        "-h",
    )

    result = CommandsPlugin.find_command(stub, "#bp.core.commands.li -h")

    assert result.command is item
    assert result.args == "-h"
    assert result.show_in_history is False
    assert result.notes == "found plugins.core.commands.list"
    assert result.message == []


def _split(line: str, match: tuple[str, str]) -> CommandSplit:
    stub = _stub({"libs.plugins.loader:plugin.id.match": lambda _id, active_only: match})
    return CommandsPlugin.find_command_split_command_string(stub, line)


def test_split_found_plugin() -> None:
    """The prefix and a leading `plugins` are removed and arguments are split off."""
    result = _split(
        "#bp.plugins.core.commands.list -c x", ("plugins.core", "plugins.core.commands")
    )

    assert (result.found, result.error) == (True, "")
    assert (result.package, result.plugin) == ("plugins.core", "plugins.core.commands")
    assert result.parts == ["core", "commands", "list"]
    assert result.args == "-c x"


def test_split_single_element_is_padded() -> None:
    """A single element after the prefix gets an empty second element."""
    result = _split("#bp.core", ("plugins.core", ""))

    assert result.parts == ["core", ""]
    assert result.args == ""


def test_split_bad_plugin() -> None:
    """A matching package with no matching plugin is `Bad Plugin`."""
    result = _split("#bp.core.zzz", ("plugins.core", ""))

    assert (result.found, result.error) == (False, "Bad Plugin")


def test_split_bad_package() -> None:
    """No matching package is `Bad Package`."""
    result = _split("#bp.zzz.yyy", ("", ""))

    assert (result.found, result.error) == (False, "Bad Package")

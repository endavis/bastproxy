"""The result classes of find_command and its split helper (#426)."""

import dataclasses
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs.plugins.loader import PluginIdMatch
from bastproxy.plugins.core.commands.plugin._commands import (
    CommandLookup,
    CommandSplit,
    CommandsPlugin,
)

PID = "plugins.core.commands"


def _stub(apis: dict[str, Any] | None = None) -> MagicMock:
    apis = apis or {}

    def api(name: str) -> Any:
        if name == "plugins.core.settings:setting.get":
            return lambda pid, key: "#bp"
        return apis[name]

    stub = MagicMock()
    stub.plugin_id = PID
    stub.api = api
    return stub


def test_dataclass_fields_and_slots() -> None:
    """Both classes carry the documented fields and use slots."""
    assert [f.name for f in dataclasses.fields(CommandSplit)] == [
        "found",
        "package",
        "plugin",
        "error",
        "parts",
        "args",
    ]
    assert [f.name for f in dataclasses.fields(CommandLookup)] == [
        "command",
        "args",
        "show_in_history",
        "notes",
        "message",
    ]
    lookup = CommandLookup(None, "", False, "", [])
    with pytest.raises(AttributeError):
        lookup.extra = 1  # type: ignore[attr-defined]
    assert not hasattr(CommandSplit(True, "", "", "", [], ""), "__dict__")


@pytest.mark.parametrize(
    ("match", "error"),
    [
        (PluginIdMatch("plugins.core", "plugins.core.commands"), ""),
        (PluginIdMatch("plugins.core", ""), "Bad Plugin"),
        (PluginIdMatch(), "Bad Package"),
    ],
)
def test_split_returns_commandsplit(match: PluginIdMatch, error: str) -> None:
    """The split helper returns a CommandSplit with the matching error text."""
    stub = _stub({"libs.plugins.loader:plugin.id.match": lambda _id, active_only: match})
    result = CommandsPlugin.find_command_split_command_string(stub, "#bp.core.commands.list x")
    assert isinstance(result, CommandSplit)
    assert result.error == error
    assert result.found is (error == "")
    assert result.args == "x"


def test_find_command_returns_lookup_on_every_path() -> None:
    """Help prefix, bad package, bad plugin, unknown command and found all give a CommandLookup."""
    item: Any = SimpleNamespace(show_in_history=True, full_cmd="plugins.core.commands.list")
    stub = _stub(
        {
            f"{PID}:command.data.get": lambda _pid: {"list": item},
            "plugins.core.fuzzy:string.match.best": lambda text, *_a, **_k: (
                "list" if text == "list" else None
            ),
        }
    )
    stub.find_command_only_prefix.return_value = ["help"]
    stub.error_package_not_found.return_value = ["pkg"]
    stub.error_plugin_not_found.return_value = ["plug"]
    stub.error_command_not_found_in_plugin.return_value = ["cmd"]

    def split(error: str, parts: list[str]) -> CommandSplit:
        found = error == ""
        return CommandSplit(found, "plugins.core", PID, error, parts, "")

    results = [CommandsPlugin.find_command(stub, "#bp")]
    stub.find_command_split_command_string.return_value = split("Bad Package", ["zzz", ""])
    results.append(CommandsPlugin.find_command(stub, "#bp.zzz"))
    stub.find_command_split_command_string.return_value = split("Bad Plugin", ["core", "zzz"])
    results.append(CommandsPlugin.find_command(stub, "#bp.core.zzz"))
    stub.find_command_split_command_string.return_value = split("", ["core", "commands", "nope"])
    results.append(CommandsPlugin.find_command(stub, "#bp.core.commands.nope"))
    stub.find_command_split_command_string.return_value = split("", ["core", "commands", "list"])
    results.append(CommandsPlugin.find_command(stub, "#bp.core.commands.list"))

    assert all(isinstance(r, CommandLookup) for r in results)
    assert [r.message for r in results] == [["help"], ["pkg"], ["plug"], ["cmd"], []]
    assert [r.command for r in results] == [None, None, None, None, item]
    assert results[-1].show_in_history is True

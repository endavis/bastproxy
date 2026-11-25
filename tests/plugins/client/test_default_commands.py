"""Tests for #778: the client plugins mark one command as their default."""

# Standard Library
from collections.abc import Callable
from typing import Any

# 3rd Party
import pytest

# Project
from bastproxy.plugins.client.actions.plugin._actions import ActionsPlugin
from bastproxy.plugins.client.aliases.plugin._aliases import AliasesPlugin
from bastproxy.plugins.client.loop.plugin._loop import LoopPlugin
from bastproxy.plugins.client.substitutes.plugin._substitutes import SubstitutesPlugin
from bastproxy.plugins.client.variables.plugin._variables import VariablesPlugin
from bastproxy.plugins.core.pluginm.plugin._pluginm import PluginManager

CASES: list[tuple[type, str, str]] = [
    (AliasesPlugin, "_command_list", "list"),
    (ActionsPlugin, "_command_list", "list"),
    (SubstitutesPlugin, "_command_list", "list"),
    (VariablesPlugin, "_command_list", "list"),
    (LoopPlugin, "_command_run", "run"),
    (PluginManager, "_command_list", "list"),
]


def _is_default(func: Callable[..., Any]) -> bool:
    data = getattr(func, "command_data", None)
    return bool(data is not None and data.command["kwargs"].get("default") is True)


@pytest.mark.parametrize(("cls", "attr", "name"), CASES)
def test_default_command_is_marked(cls: type, attr: str, name: str) -> None:
    func = getattr(cls, attr)
    assert _is_default(func)
    assert func.command_data.command.get("name", name).strip() == name


@pytest.mark.parametrize(("cls", "attr", "name"), CASES)
def test_no_other_command_is_default(cls: type, attr: str, name: str) -> None:
    others = [
        member
        for member_name in dir(cls)
        if member_name.startswith("_command_") and member_name != attr
        for member in [getattr(cls, member_name)]
        if _is_default(member)
    ]
    assert others == []

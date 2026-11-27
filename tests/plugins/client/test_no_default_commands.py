"""Tests for #862: no client plugin marks a command as its default."""

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


def _kwargs(func: Callable[..., Any]) -> dict[str, Any]:
    data = getattr(func, "command_data", None)
    return dict(data.command["kwargs"]) if data is not None else {}


@pytest.mark.parametrize(("cls", "attr", "name"), CASES)
def test_command_has_no_default(cls: type, attr: str, name: str) -> None:
    func = getattr(cls, attr)
    kwargs = _kwargs(func)
    assert "default" not in kwargs
    if cls is not PluginManager:
        assert kwargs.get("literal_args") is True
    assert func.command_data.command.get("name", name).strip() == name


@pytest.mark.parametrize(("cls", "attr", "name"), CASES)
def test_no_command_in_plugin_has_default(cls: type, attr: str, name: str) -> None:
    for member_name in dir(cls):
        if member_name.startswith("_command_"):
            member = getattr(cls, member_name)
            assert "default" not in _kwargs(member)

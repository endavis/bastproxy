# Project: bastproxy
# Filename: tests/libs/plugins/test_plugin_id_match.py
#
# File Description: Tests for the PluginIdMatch the plugin.id.match API returns
#
# By: Bast
"""Tests for ``PluginIdMatch`` and ``PluginLoader._api_plugin_id_match`` (issue #426)."""

from __future__ import annotations

import dataclasses
from typing import Any
from unittest.mock import MagicMock

from bastproxy.libs.plugins.loader import PluginIdMatch, PluginLoader

FUZZY = "plugins.core.fuzzy:string.match.best"
PACKAGES = ("plugins.core", "plugins.test")
LOADED = ("plugins.core.commands", "plugins.core.api")


def _stub(package: str, plugin: str) -> tuple[MagicMock, dict[str, MagicMock]]:
    """Build a loader stub whose fuzzy matcher answers package then plugin."""
    apis: dict[str, MagicMock] = {
        "libs.plugins.loader:package.list": MagicMock(return_value=list(PACKAGES)),
        "libs.plugins.loader:plugin.list.loaded": MagicMock(return_value=list(LOADED)),
        FUZZY: MagicMock(side_effect=[package, plugin]),
    }

    def api(name: str) -> Any:
        return apis[name]

    stub = MagicMock()
    stub.api = api
    return stub, apis


def test_dataclass_shape() -> None:
    """The class is slotted, defaults to empty strings and orders package first."""
    assert not hasattr(PluginIdMatch(), "__dict__")
    assert PluginIdMatch() == PluginIdMatch("", "")
    assert [f.name for f in dataclasses.fields(PluginIdMatch)] == ["package", "plugin"]


def test_no_dot_returns_empty_without_fuzzy() -> None:
    """Input with no dot cannot name a package and plugin."""
    stub, apis = _stub("", "")
    result = PluginLoader._api_plugin_id_match(stub, "core")
    assert result == PluginIdMatch()
    assert isinstance(result, PluginIdMatch)
    apis[FUZZY].assert_not_called()


def test_unmatched_package_skips_plugin_lookup() -> None:
    """An unmatched package returns the empty match and never lists plugins."""
    stub, apis = _stub("", "")
    result = PluginLoader._api_plugin_id_match(stub, "zzz.yyy")
    assert result == PluginIdMatch()
    assert isinstance(result, PluginIdMatch)
    apis["libs.plugins.loader:plugin.list.loaded"].assert_not_called()


def test_empty_plugin_part() -> None:
    """A matched package with an empty plugin part returns an empty plugin."""
    stub, apis = _stub("plugins.core", "")
    result = PluginLoader._api_plugin_id_match(stub, "core.")
    assert result == PluginIdMatch("plugins.core", "")
    assert isinstance(result, PluginIdMatch)
    apis["libs.plugins.loader:plugin.list.loaded"].assert_not_called()


def test_matched_package_unmatched_plugin() -> None:
    """The fuzzy matcher returns an empty string for no plugin match."""
    stub, _apis = _stub("plugins.core", "")
    result = PluginLoader._api_plugin_id_match(stub, "core.zzz")
    assert result == PluginIdMatch("plugins.core", "")
    assert isinstance(result, PluginIdMatch)


def test_full_match_and_fuzzy_arguments() -> None:
    """A full match returns both ids and passes the scorer and cutoff through."""
    stub, apis = _stub("plugins.core", "plugins.core.commands")
    result = PluginLoader._api_plugin_id_match(stub, "core.comm", active_only=True)
    assert result == PluginIdMatch("plugins.core", "plugins.core.commands")
    assert isinstance(result, PluginIdMatch)
    apis["libs.plugins.loader:package.list"].assert_called_once_with(True)
    package_call, plugin_call = apis[FUZZY].call_args_list
    assert package_call.args == ("plugins.core", PACKAGES)
    assert package_call.kwargs == {"scorer": "token_set_ratio", "score_cutoff": 90}
    assert plugin_call.args == ("plugins.core.comm", LOADED)
    assert plugin_call.kwargs == {"scorer": "token_set_ratio"}

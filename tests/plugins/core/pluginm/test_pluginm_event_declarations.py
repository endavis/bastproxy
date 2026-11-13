"""Tests for the events the plugin manager declares (#466)."""

from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins.core.pluginm.plugin._pluginm import PluginManager


def _declared() -> dict[str, dict[str, Any]]:
    declared: dict[str, dict[str, Any]] = {}

    def event_add(name: str, _owner: str, **kwargs: Any) -> None:
        declared[name] = kwargs["arg_descriptions"]

    stub = MagicMock()
    stub.plugin_id = "plugins.core.pluginm"
    stub.api = lambda name: event_add if name == "plugins.core.events:event.add" else MagicMock()
    PluginManager._phook_initialize(stub)
    return declared


def test_loaded_and_unloaded_declare_only_plugin_id() -> None:
    declared = _declared()
    assert set(declared["ev_plugin_loaded"]) == {"plugin_id"}
    assert set(declared["ev_plugin_unloaded"]) == {"plugin_id"}


def test_plugin_stats_declares_plugin_id_and_stats() -> None:
    assert set(_declared()["ev_plugin_stats"]) == {"plugin_id", "stats"}

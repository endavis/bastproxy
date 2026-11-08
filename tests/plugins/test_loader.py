# Project: bastproxy
# Filename: tests/plugins/test_loader.py
#
# File Description: Tests for the plugin loader
#
# By: Bast
"""Unit tests for `bastproxy.libs.plugins.loader`.

These tests pin down the removal of the dead `check_dependencies` parameter
from `PluginLoader._api_plugin_load` (the `plugin.load` API). See issue #8.

"""

import inspect

from bastproxy.libs.plugins.loader import PluginLoader


class TestLoadPluginsSignature:
    """Tests for the `_api_plugin_load` / `plugin.load` API signature."""

    def test_load_plugins_has_no_check_dependencies_parameter(self) -> None:
        """`_api_plugin_load` must not accept a `check_dependencies` argument.

        The parameter was accepted but never read (dead code); it was removed
        in issue #8 rather than wired up to real dependency resolution.

        """
        signature = inspect.signature(PluginLoader._api_plugin_load)
        assert "check_dependencies" not in signature.parameters

    def test_load_plugins_expected_parameters(self) -> None:
        """`_api_plugin_load` keeps its remaining, expected parameters."""
        signature = inspect.signature(PluginLoader._api_plugin_load)
        assert list(signature.parameters) == ["self", "plugins_to_load", "exit_on_error"]

    def test_load_plugins_rejects_check_dependencies_keyword(self) -> None:
        """Binding `check_dependencies=...` now raises `TypeError`.

        This documents the API change called out in issue #8: an external
        plugin calling `plugin.load(..., check_dependencies=...)` now gets a
        `TypeError` instead of being silently ignored. Binding the signature
        (rather than instantiating `PluginLoader` and calling the method)
        avoids pulling in the full plugin API runtime for this check.

        """
        signature = inspect.signature(PluginLoader._api_plugin_load)
        try:
            signature.bind(object(), [], check_dependencies=True)
        except TypeError:
            pass
        else:
            raise AssertionError("expected TypeError for removed check_dependencies kwarg")

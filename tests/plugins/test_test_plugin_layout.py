# Project: bastproxy
# Filename: tests/plugins/test_test_plugin_layout.py
#
# File Description: Tests that every plugin uses the plugin/ sub-package layout
#
# By: Bast
"""Tests for the layout of the plugins under ``plugins/test`` (issue #98).

The loader imports the plugin class from ``<package>.plugin``
(``PluginInfo.plugin_class_import_location``). These tests discover every
bundled plugin and check that import step, then check the three test plugins
that used the old flat layout.

Covered of the ``plugin.load`` success criterion: discovery, metadata parsing
(``update_from_init``), the module import the loader performs in
``_import_single_plugin`` and the command lookup the commands plugin performs
(``_command_`` prefix plus ``command_data``). Instantiation and the initialize
hooks need the running proxy (API, event and settings plugins) and are not
exercised here.

"""

import types
from pathlib import Path
from typing import Any

import pytest

from bastproxy.libs.plugins import imputils
from bastproxy.libs.plugins.plugininfo import PluginInfo

PLUGINS_DIR = Path(__file__).resolve().parents[2] / "src" / "bastproxy" / "plugins"
PREFIX = "bastproxy.plugins."
LAYOUT_PLUGINS = ["test.cmddec", "test._sqldb", "test.exception"]


def _discover() -> tuple[list[dict[str, Any]], dict[str, tuple]]:
    """Discover the bundled plugins the way the loader does."""
    _, plugins, errors = imputils.find_packages_and_plugins(PLUGINS_DIR, PREFIX)
    return plugins, errors


def _info_for(plugin: dict[str, Any]) -> PluginInfo:
    """Build a PluginInfo from a discovered plugin dict, with metadata parsed."""
    info = PluginInfo(plugin["plugin_id"])
    info.package_init_file_path = plugin["package_init_file_path"]
    info.package_path = plugin["package_path"]
    info.package_import_location = plugin["package_import_location"]
    info.update_from_init()
    return info


def _by_suffix(suffix: str) -> dict[str, Any]:
    plugins, _ = _discover()
    matches = [p for p in plugins if p["package_import_location"] == PREFIX + suffix]
    assert matches, f"{suffix} was not discovered as a plugin"
    return matches[0]


def test_discovery_has_no_import_errors() -> None:
    """Plugin discovery reports no import errors."""
    _, errors = _discover()
    assert errors == {}


def test_every_plugin_imports_from_plugin_subpackage() -> None:
    """Each discovered plugin's ``.plugin`` module imports and exposes ``Plugin``."""
    plugins, _ = _discover()
    assert plugins
    failures: list[str] = []
    for plugin in plugins:
        info = _info_for(plugin)
        result = imputils.importmodule(info.plugin_class_import_location)
        if not result["success"]:
            failures.append(f"{info.plugin_id}: {result['exception']!r}")
        elif not hasattr(result["module"], "Plugin"):
            failures.append(f"{info.plugin_id}: no Plugin")
    assert failures == []


@pytest.mark.parametrize("suffix", LAYOUT_PLUGINS)
def test_layout_plugin_is_discovered_and_loads(suffix: str) -> None:
    """The three moved plugins are discovered, have metadata and import."""
    info = _info_for(_by_suffix(suffix))
    assert info.import_errors == []
    assert info.name
    assert info.purpose
    assert (info.package_path / "plugin" / "__init__.py").is_file()
    result = imputils.importmodule(info.plugin_class_import_location)
    assert result["success"], result["exception"]
    assert info.plugin_class_import_location == f"{PREFIX}{suffix}.plugin"
    assert hasattr(result["module"], "Plugin")


def _command_names(cls: type) -> list[str]:
    """Names the commands plugin would register for a plugin class."""
    return [
        name
        for name, attr in vars(cls).items()
        if isinstance(attr, types.FunctionType)
        and name.startswith("_command_")
        and hasattr(attr, "command_data")
    ]


def test_cmddec_registers_command_raise() -> None:
    """cmddec's command carries the ``_command_`` prefix so it is registered."""
    info = _info_for(_by_suffix("test.cmddec"))
    module = imputils.importmodule(info.plugin_class_import_location)["module"]
    assert _command_names(module.Plugin) == ["_command_raise"]
    assert not hasattr(module.Plugin, "cmd_raise")


def test_exception_lists_command_raise() -> None:
    """The exception plugin's command is still listed after the move."""
    info = _info_for(_by_suffix("test.exception"))
    module = imputils.importmodule(info.plugin_class_import_location)["module"]
    assert _command_names(module.Plugin) == ["_command_raise"]


def test_sqldb_initialize_creates_statdb(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``_sqldb`` initialize builds its database from the base class and data dir."""
    from types import SimpleNamespace

    from bastproxy.libs.api import API
    from bastproxy.plugins._baseplugin import BasePlugin
    from bastproxy.plugins.core.sqldb.libs._sqlite import Sqldb

    monkeypatch.setattr(BasePlugin, "initialize", lambda self: None)
    info = _info_for(_by_suffix("test._sqldb"))
    module = imputils.importmodule(info.plugin_class_import_location)["module"]

    # A real API instance: ``api(name)`` returns an APIItem, which must be called
    # to get the Sqldb class (as the sqldb plugin's ``_api_baseclass`` does).
    real_api = API("plugins.test._sqldb")
    real_api.add("plugins.core.sqldb", "baseclass", lambda: Sqldb, instance=True)

    fake = SimpleNamespace(
        api=real_api,
        plugin_id="plugins.test._sqldb",
        plugin_info=SimpleNamespace(data_directory=tmp_path),
    )
    module.Plugin.initialize(fake)
    assert isinstance(fake.statdb, Sqldb)
    assert (tmp_path / "stats.sqlite").exists()


def test_every_test_plugin_has_plugin_subpackage() -> None:
    """Every plugin under plugins/test has a plugin/ sub-package."""
    missing = [
        d.name
        for d in (PLUGINS_DIR / "test").iterdir()
        if d.is_dir() and d.name != "__pycache__" and not (d / "plugin" / "__init__.py").is_file()
    ]
    assert missing == []

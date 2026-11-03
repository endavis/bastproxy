# Project: bastproxy
# Filename: tests/libs/plugins/test_failed_load_cleanup.py
#
# File Description: Tests that a failed plugin load leaves no modules behind
#
# By: Bast
"""Tests for the failed-load cleanup in ``_api_load_plugins`` (issue #111)."""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from bastproxy.libs.plugins import imputils
from bastproxy.libs.plugins.loader import PluginLoader, plugin_module_names
from bastproxy.libs.plugins.plugininfo import PluginInfo

ROOT_PKG = "zzfailload111"
PACKAGE = f"{ROOT_PKG}.test.zzfail"
PLUGIN_ID = PACKAGE

_BROKEN_INIT = (
    "class Plugin:\n"
    "    def __init__(self, plugin_id, plugin_info):\n"
    "        raise RuntimeError('boom')\n"
)
_BROKEN_INITIALIZE = (
    "class Plugin:\n"
    "    def __init__(self, plugin_id, plugin_info):\n"
    "        pass\n\n"
    "    def initialize(self):\n"
    "        raise RuntimeError('boom')\n"
)
_GOOD = (
    "VERSION = 'fixed'\n\n\n"
    "class Plugin:\n"
    "    version = VERSION\n\n"
    "    def __init__(self, plugin_id, plugin_info):\n"
    "        self.info = plugin_info\n\n"
    "    def initialize(self):\n"
    "        # the real BasePlugin flags itself loaded through the API\n"
    "        self.info.runtime_info.is_loaded = True\n"
)


def _write_plugin(root: Path, code: str) -> None:
    """Write (or rewrite) the throwaway plugin package under ``root``."""
    plugin_dir = root / ROOT_PKG / "test" / "zzfail"
    (plugin_dir / "plugin").mkdir(parents=True, exist_ok=True)
    (root / ROOT_PKG / "__init__.py").write_text("")
    (root / ROOT_PKG / "test" / "__init__.py").write_text("")
    (plugin_dir / "__init__.py").write_text(
        'PLUGIN_NAME = "zzfail"\n'
        'PLUGIN_PURPOSE = "repro"\n'
        'PLUGIN_AUTHOR = "Bast"\n'
        "PLUGIN_VERSION = 1\n"
    )
    (plugin_dir / "plugin" / "__init__.py").write_text(
        "from ._plugin import Plugin\n\n__all__ = ['Plugin']\n"
    )
    (plugin_dir / "plugin" / "_plugin.py").write_text(code)


def _plugin_modules() -> list[str]:
    return plugin_module_names(PACKAGE)


def _make_loader(root: Path, monkeypatch: pytest.MonkeyPatch) -> PluginLoader:
    monkeypatch.syspath_prepend(str(root))
    _, found, _ = imputils.find_packages_and_plugins(root / ROOT_PKG, f"{ROOT_PKG}.")
    assert [p["plugin_id"] for p in found] == [PACKAGE]

    plugin_info = PluginInfo(plugin_id=PLUGIN_ID)
    plugin_info.package_init_file_path = found[0]["package_init_file_path"]
    plugin_info.package_path = found[0]["package_path"]
    plugin_info.package_import_location = found[0]["package_import_location"]

    loader = PluginLoader.__new__(PluginLoader)
    loader.api = MagicMock()
    loader.plugins_info = {PLUGIN_ID: plugin_info}
    loader.weak_references_to_modules = {}
    return loader


@pytest.fixture
def make_loader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[Path, Callable[[str], PluginLoader]]]:
    """Return a throwaway root and a factory-built loader; clean sys.modules after."""

    def _factory(code: str) -> PluginLoader:
        _write_plugin(tmp_path, code)
        return _make_loader(tmp_path, monkeypatch)

    yield tmp_path, _factory
    for name in [n for n in sys.modules if n == ROOT_PKG or n.startswith(f"{ROOT_PKG}.")]:
        del sys.modules[name]


@pytest.mark.parametrize("broken", [_BROKEN_INIT, _BROKEN_INITIALIZE])
def test_failed_load_leaves_no_modules_and_reload_gets_new_code(
    make_loader: tuple[Path, Callable[[str], PluginLoader]], broken: str
) -> None:
    """A failed instantiate/initialize removes every plugin module; a retry reimports."""
    root, factory = make_loader
    loader = factory(broken)

    result = loader._api_load_plugins([PLUGIN_ID])
    assert result["bad_plugins"] == [PLUGIN_ID]
    assert _plugin_modules() == []

    _write_plugin(root, _GOOD)
    result = loader._api_load_plugins([PLUGIN_ID])
    assert result["bad_plugins"] == []
    info = loader.plugins_info[PLUGIN_ID]
    assert sys.modules[info.plugin_class_import_location].Plugin.version == "fixed"


def test_plugin_module_names_matches_package_and_children_only() -> None:
    """The helper matches the package and its children, not sibling prefixes."""
    names = ["zzhelper111", "zzhelper111.a", "zzhelper111.a.b", "zzhelper1112", "zzhelper11"]
    for name in names:
        sys.modules[name] = MagicMock()
    try:
        assert sorted(plugin_module_names("zzhelper111")) == [
            "zzhelper111",
            "zzhelper111.a",
            "zzhelper111.a.b",
        ]
    finally:
        for name in names:
            del sys.modules[name]

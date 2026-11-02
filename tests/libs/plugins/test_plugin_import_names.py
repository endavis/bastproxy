# Project: bastproxy
# Filename: tests/libs/plugins/test_plugin_import_names.py
#
# File Description: Tests that plugin modules are imported under one name only
#
# By: Bast
"""Tests for the single import name of plugin modules (issue #95).

A plugin is imported under its real package name only, so reload picks up
changed code and unload leaves nothing behind in ``sys.modules``.

"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs.plugins import imputils
from bastproxy.libs.plugins.loader import PluginLoader
from bastproxy.libs.plugins.plugininfo import PluginInfo

ROOT_PKG = "zzimport95"
ALIAS_PKG = "zzalias95"
PACKAGE = f"{ROOT_PKG}.test.zzrepro"
# The plugin ID differs from the package name, as in bastproxy where the ID is
# ``plugins.…`` and the package is ``bastproxy.plugins.…``.
PLUGIN_ID = f"{ALIAS_PKG}.test.zzrepro"


def _write_plugin(root: Path, version: str) -> None:
    """Write (or rewrite) the throwaway plugin package under ``root``."""
    plugin_dir = root / ROOT_PKG / "test" / "zzrepro"
    (plugin_dir / "plugin").mkdir(parents=True, exist_ok=True)
    (root / ROOT_PKG / "__init__.py").write_text("")
    # a namespace alias like the ID prefix: the alias resolves to the real tree
    (root / ALIAS_PKG).mkdir(exist_ok=True)
    (root / ALIAS_PKG / "__init__.py").write_text(f"__path__ = [{str(root / ROOT_PKG)!r}]\n")
    (root / ROOT_PKG / "test" / "__init__.py").write_text("")
    (plugin_dir / "__init__.py").write_text(
        'PLUGIN_NAME = "zzrepro"\n'
        'PLUGIN_PURPOSE = "repro"\n'
        'PLUGIN_AUTHOR = "Bast"\n'
        "PLUGIN_VERSION = 1\n"
    )
    (plugin_dir / "plugin" / "__init__.py").write_text(
        "from ._plugin import Plugin\n\n__all__ = ['Plugin']\n"
    )
    (plugin_dir / "plugin" / "_plugin.py").write_text(
        f"VERSION = {version!r}\n\n\nclass Plugin:\n    version = VERSION\n"
    )


def _plugin_modules() -> list[str]:
    return [name for name in sys.modules if "zzrepro" in name]


@pytest.fixture
def plugin_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[PluginLoader, Path]]:
    """Return a loader stub with one discovered throwaway plugin and its root."""
    _write_plugin(tmp_path, "v7")
    monkeypatch.syspath_prepend(str(tmp_path))
    _, found, _ = imputils.find_packages_and_plugins(tmp_path / ROOT_PKG, f"{ROOT_PKG}.")
    assert [p["plugin_id"] for p in found] == [PACKAGE]

    plugin_info = PluginInfo(plugin_id=PLUGIN_ID)
    plugin_info.package_init_file_path = found[0]["package_init_file_path"]
    plugin_info.package_path = found[0]["package_path"]
    plugin_info.package_import_location = found[0]["package_import_location"]

    loader = PluginLoader.__new__(PluginLoader)
    loader.api = MagicMock()
    loader.plugins_info = {PLUGIN_ID: plugin_info}
    loader.weak_references_to_modules = {}
    try:
        yield loader, tmp_path
    finally:
        for name in [n for n in sys.modules if n.startswith((ROOT_PKG, ALIAS_PKG))]:
            del sys.modules[name]


def _import(loader: PluginLoader) -> Any:
    assert loader._import_single_plugin(PLUGIN_ID)
    info = loader.plugins_info[PLUGIN_ID]
    return sys.modules[info.plugin_class_import_location].Plugin


def test_class_import_location_is_real_package_name(
    plugin_env: tuple[PluginLoader, Path],
) -> None:
    """The class import location derives from the package, not the plugin ID."""
    loader, _ = plugin_env
    info = loader.plugins_info[PLUGIN_ID]
    assert info.plugin_class_import_location == f"{PACKAGE}.plugin"
    assert PluginInfo(plugin_id="plugins.core.commands").plugin_class_import_location == ""


def test_load_imports_under_one_name(plugin_env: tuple[PluginLoader, Path]) -> None:
    """After a load every plugin module is in sys.modules once, under its package name."""
    loader, _ = plugin_env
    _import(loader)
    modules = _plugin_modules()
    assert all(name.startswith(f"{ROOT_PKG}.") for name in modules)
    assert f"{PACKAGE}.plugin._plugin" in modules


def test_reload_runs_changed_code(plugin_env: tuple[PluginLoader, Path]) -> None:
    """After unload and load again, the changed code is the code that runs."""
    loader, root = plugin_env
    assert _import(loader).version == "v7"

    for expected in ("version-eight", "version-number-nine"):
        assert loader._api_unload_plugin(PLUGIN_ID)
        _write_plugin(root, expected)
        assert _import(loader).version == expected


def test_unload_leaves_no_modules(plugin_env: tuple[PluginLoader, Path]) -> None:
    """After unload none of the plugin's modules remain in sys.modules."""
    loader, _ = plugin_env
    _import(loader)
    assert loader._api_unload_plugin(PLUGIN_ID)
    assert _plugin_modules() == []

# Project: bastproxy
# Filename: tests/libs/plugins/test_module_cleanup.py
#
# File Description: Tests for deletemodule and CANRELOAD-aware cleanup
#
# By: Bast
"""Tests for module cleanup (issue #129)."""

from __future__ import annotations

import sys
import types
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from bastproxy.libs.plugins import imputils
from bastproxy.libs.plugins.loader import (
    PluginLoader,
    plugin_module_names,
    reloadable_plugin_module_names,
)
from bastproxy.libs.plugins.plugininfo import PluginInfo

PKG = "zzcleanup129"


@pytest.fixture
def fake_modules() -> Iterator[list[str]]:
    """Register fake modules and remove them afterwards."""
    added: list[str] = []
    yield added
    for name in added:
        sys.modules.pop(name, None)


def _add(added: list[str], name: str, **attrs: object) -> None:
    mod = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    sys.modules[name] = mod
    added.append(name)


def test_deletemodule_deletes_name_containing_baseplugin(fake_modules: list[str]) -> None:
    """A user module whose name merely contains 'baseplugin' is deleted."""
    name = f"{PKG}.mine.mybaseplugin"
    _add(fake_modules, name)
    assert imputils.deletemodule(name) is True
    assert name not in sys.modules


def test_deletemodule_keeps_bundled_baseplugin_and_submodules() -> None:
    """The bundled _baseplugin package and its submodules are never deleted."""
    import bastproxy.plugins._baseplugin  # noqa: F401

    base = "bastproxy.plugins._baseplugin"
    children = [n for n in sys.modules if n.startswith(f"{base}.")]
    assert children
    for name in [base, *children]:
        assert imputils.deletemodule(name) is False
        assert name in sys.modules


def test_deletemodule_modules_to_keep_prefix_not_substring(fake_modules: list[str]) -> None:
    """modules_to_keep matches the package and its children, not substrings."""
    keep = f"{PKG}.keep"
    names = [keep, f"{keep}.sub", f"{keep}er", f"{PKG}.x.keep"]
    for name in names:
        _add(fake_modules, name)
    assert imputils.deletemodule(keep, [keep]) is False
    assert imputils.deletemodule(f"{keep}.sub", [keep]) is False
    assert imputils.deletemodule(f"{keep}er", [keep]) is True
    assert imputils.deletemodule(f"{PKG}.x.keep", [keep]) is True


def test_reloadable_names_skip_canreload_false(fake_modules: list[str]) -> None:
    """Modules with CANRELOAD = False are excluded from the reloadable names."""
    _add(fake_modules, f"{PKG}.p")
    _add(fake_modules, f"{PKG}.p.keepme", CANRELOAD=False)
    _add(fake_modules, f"{PKG}.p.other")
    assert sorted(reloadable_plugin_module_names(f"{PKG}.p")) == [f"{PKG}.p", f"{PKG}.p.other"]


def test_failed_load_cleanup_keeps_canreload_false_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The failed-load cleanup leaves a CANRELOAD = False module in sys.modules."""
    root_pkg = "zzcanreload129"
    package = f"{root_pkg}.test.zzfail"
    plugin_dir = tmp_path / root_pkg / "test" / "zzfail"
    (plugin_dir / "plugin").mkdir(parents=True)
    (tmp_path / root_pkg / "__init__.py").write_text("")
    (tmp_path / root_pkg / "test" / "__init__.py").write_text("")
    (plugin_dir / "__init__.py").write_text(
        'PLUGIN_NAME = "zzfail"\nPLUGIN_PURPOSE = "repro"\n'
        'PLUGIN_AUTHOR = "Bast"\nPLUGIN_VERSION = 1\n'
    )
    (plugin_dir / "plugin" / "__init__.py").write_text(
        "from ._plugin import Plugin\n\n__all__ = ['Plugin']\n"
    )
    (plugin_dir / "plugin" / "_plugin.py").write_text(
        "from . import _keep  # noqa: F401\n\n\n"
        "class Plugin:\n"
        "    def __init__(self, plugin_id, plugin_info):\n"
        "        raise RuntimeError('boom')\n"
    )
    (plugin_dir / "plugin" / "_keep.py").write_text("CANRELOAD = False\n")

    monkeypatch.syspath_prepend(str(tmp_path))
    _, found, _ = imputils.find_packages_and_plugins(tmp_path / root_pkg, f"{root_pkg}.")
    info = PluginInfo(plugin_id=package)
    info.package_init_file_path = found[0]["package_init_file_path"]
    info.package_path = found[0]["package_path"]
    info.package_import_location = found[0]["package_import_location"]
    loader = PluginLoader.__new__(PluginLoader)
    loader.api = MagicMock()
    loader.plugins_info = {package: info}
    loader.weak_references_to_modules = {}
    try:
        result = loader._api_plugin_load([package])
        assert result["bad_plugins"] == [package]
        assert plugin_module_names(package) == [f"{package}.plugin._keep"]
    finally:
        for name in plugin_module_names(root_pkg):
            del sys.modules[name]

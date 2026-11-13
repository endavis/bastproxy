# Project: bastproxy
# Filename: tests/libs/plugins/test_user_plugins.py
#
# File Description: Tests that user plugins load from BASTPROXY_HOME/plugins
#
# By: Bast
"""Tests for user plugins under the ``userplugins`` import root (issue #110)."""

from __future__ import annotations

import importlib.util
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs.api import API
from bastproxy.libs.plugins import imputils
from bastproxy.libs.plugins.loader import PluginLoader
from bastproxy.libs.plugins.plugininfo import PluginInfo
from bastproxy.plugins.core.pluginm.plugin._pluginm import _package_description

ROOT = "userplugins"


def _write_plugin(root: Path, package: str, name: str, version: str = "v1") -> None:
    """Write a throwaway plugin ``root/package/name``."""
    pkg_dir = root / package
    plugin_dir = pkg_dir / name
    (plugin_dir / "plugin").mkdir(parents=True, exist_ok=True)
    (pkg_dir / "__init__.py").write_text("")
    (plugin_dir / "__init__.py").write_text(
        f'PLUGIN_NAME = "{name}"\n'
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


def _clean_modules() -> None:
    for name in [n for n in sys.modules if n == ROOT or n.startswith(f"{ROOT}.")]:
        del sys.modules[name]


@pytest.fixture(autouse=True)
def clean_user_root() -> Iterator[None]:
    """Remove every ``userplugins`` module before and after each test."""
    _clean_modules()
    yield
    _clean_modules()


def _loader(user_dir: Path, bundled_dir: Path | None = None) -> PluginLoader:
    loader = PluginLoader.__new__(PluginLoader)
    loader.api = MagicMock()
    loader.plugins_info = {}
    loader.weak_references_to_modules = {}
    loader.base_plugin_dir = user_dir
    loader.plugin_search_paths = []
    if bundled_dir is not None:
        loader.plugin_search_paths.append(
            {
                "path": bundled_dir,
                "import_prefix": "zzbundled110.",
                "id_prefix": "plugins.",
                "source": "bundled",
            }
        )
    loader.plugin_search_paths.append(
        {
            "path": user_dir,
            "import_prefix": f"{ROOT}.",
            "id_prefix": "plugins.",
            "source": "user",
        }
    )
    return loader


def test_register_import_root(tmp_path: Path) -> None:
    """The root is a package module, and a second call refreshes ``__path__``."""
    module = imputils.register_import_root(ROOT, tmp_path)
    assert sys.modules[ROOT] is module
    assert module.__path__ == [str(tmp_path)]

    other = tmp_path / "other"
    other.mkdir()
    again = imputils.register_import_root(ROOT, other)
    assert again is module
    assert module.__path__ == [str(other)]


def test_user_plugin_is_discovered(tmp_path: Path) -> None:
    """A user tree ``mine/zzu`` is found with a ``plugins.`` ID and no errors."""
    _write_plugin(tmp_path, "mine", "zzu")
    loader = _loader(tmp_path)
    result = loader._discover_plugins()
    plugins = result.plugins
    assert result.errors == {}
    assert [p["plugin_id"] for p in plugins] == ["plugins.mine.zzu"]
    assert plugins[0]["package_import_location"] == f"{ROOT}.mine.zzu"


def test_user_plugin_in_bundled_package_is_refused(tmp_path: Path) -> None:
    """A user plugin in a bundled package is refused; the bundled one is kept."""
    bundled = tmp_path / "bundled"
    user = tmp_path / "user"
    _write_plugin(bundled / "zzbundled110", "core", "zzb")
    (bundled / "zzbundled110" / "__init__.py").write_text("")
    _write_plugin(user, "core", "zzu")
    _write_plugin(user, "mine", "zzok")
    sys.path.insert(0, str(bundled))
    try:
        loader = _loader(user, bundled / "zzbundled110")
        plugins = loader._discover_plugins().plugins
    finally:
        sys.path.remove(str(bundled))
        for name in [n for n in sys.modules if n.startswith("zzbundled110")]:
            del sys.modules[name]
    ids = [p["plugin_id"] for p in plugins]
    assert "plugins.core.zzb" in ids
    assert "plugins.core.zzu" not in ids
    assert "plugins.mine.zzok" in ids
    assert ids.index("plugins.core.zzb") < ids.index("plugins.mine.zzok")


def test_bundled_searched_first() -> None:
    """The real loader lists bundled plugins before the user path."""
    loader = PluginLoader()
    sources = [s["source"] for s in loader.plugin_search_paths]
    assert sources == ["bundled", "user"]


def test_user_plugin_imports_unloads_and_reloads(tmp_path: Path) -> None:
    """A user plugin imports, unloads cleanly and reloads with changed code."""
    _write_plugin(tmp_path, "mine", "zzu", "v1")
    loader = _loader(tmp_path)
    plugins = loader._discover_plugins().plugins
    info = PluginInfo(plugin_id=plugins[0]["plugin_id"])
    info.package_init_file_path = plugins[0]["package_init_file_path"]
    info.package_path = plugins[0]["package_path"]
    info.package_import_location = plugins[0]["package_import_location"]
    loader.plugins_info = {info.plugin_id: info}

    def _import() -> Any:
        assert loader._import_single_plugin(info.plugin_id)
        return sys.modules[info.plugin_class_import_location].Plugin

    assert _import().version == "v1"
    assert loader._api_plugin_unload(info.plugin_id)
    assert [n for n in sys.modules if n.startswith(f"{ROOT}.mine.zzu")] == []

    _write_plugin(tmp_path, "mine", "zzu", "version-two")
    assert _import().version == "version-two"


def test_plugin_paths() -> None:
    """The user plugin folder exists and differs from the data plugin folder."""
    home = Path(os.environ["BASTPROXY_HOME"]).expanduser().resolve()
    assert home / "plugins" == API.BASEPLUGINPATH
    assert API.BASEPLUGINPATH.is_dir()
    assert API.BASEPLUGINPATH != API.BASEDATAPLUGINPATH


def test_package_description() -> None:
    """The package description comes from the package of the plugin."""
    core = PluginInfo(plugin_id="plugins.core.commands")
    core.package_import_location = "bastproxy.plugins.core.commands"
    assert _package_description(core) == "Plugins that implement core functionality"

    none = PluginInfo(plugin_id="plugins.nopkg.x")
    none.package_import_location = "userplugins.nopkg.x"
    assert _package_description(none) == ""


def test_top_level_plugins_shim_is_gone() -> None:
    """The top-level ``plugins`` import package no longer exists."""
    # tests/plugins can itself resolve as ``plugins`` under pytest's rootdir import
    # mode, so check the package source tree instead of the bare name.
    spec = importlib.util.find_spec("plugins")
    src_root = Path(imputils.__file__).resolve().parents[3]
    locations = [Path(p).resolve() for p in (spec.submodule_search_locations or [])] if spec else []
    assert not any(loc.is_relative_to(src_root) for loc in locations)
    assert not (src_root / "plugins").exists()

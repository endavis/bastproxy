# Project: bastproxy
# Filename: tests/libs/plugins/test_user_plugins.py
#
# File Description: Tests that user plugins load from BASTPROXY_HOME/plugins
#
# By: Bast
"""Tests for user plugins under the ``userplugins`` import root (issue #110)."""

from __future__ import annotations

import importlib.util
import logging
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


OWN_ROOTS = ("mine", "zz824own", "zz824ok", "zz824bad", "zz824ns", "zz824x", "zz824def")


def _clean_modules() -> None:
    for name in list(sys.modules):
        top = name.split(".")[0]
        if top == ROOT or top in OWN_ROOTS or imputils.is_registered_package_root(top):
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
    assert plugins[0]["package_import_location"] == "mine.zzu"


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
    assert [n for n in sys.modules if n.startswith("mine.zzu")] == []

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


def test_discovered_plugin_ids_are_plugin_ids(tmp_path: Path) -> None:
    """Discovery stores ``PluginId`` values in ``p["plugin_id"]`` (issue #436)."""
    from bastproxy.libs.plugins.pluginid import PluginId

    _write_plugin(tmp_path, "mine", "zzp")
    plugins = _loader(tmp_path)._discover_plugins().plugins
    assert [type(p["plugin_id"]) for p in plugins] == [PluginId]
    assert plugins[0]["plugin_id"].package == "plugins.mine"


def _own_plugin_with_libs(root: Path, package: str, name: str) -> None:
    """Write ``package/name`` whose plugin imports ``package._libs``."""
    _write_plugin(root, package, name)
    (root / package / "__init__.py").write_text("SHARED = 1\n")
    (root / package / "_libs").mkdir()
    (root / package / "_libs" / "__init__.py").write_text('VALUE = "ok"\n')
    (root / package / name / "plugin" / "_plugin.py").write_text(
        f"from {package}._libs import VALUE\n\n\nclass Plugin:\n    value = VALUE\n"
    )


def test_own_name_package_self_import(tmp_path: Path) -> None:
    """A user package imports under its own name and sees its own modules."""
    _own_plugin_with_libs(tmp_path, "zz824own", "zzp")
    loader = _loader(tmp_path)
    result = loader._discover_plugins()
    assert result.errors == {}
    plugins = result.plugins
    assert [str(p["plugin_id"]) for p in plugins] == ["plugins.zz824own.zzp"]
    assert plugins[0]["package_import_location"] == "zz824own.zzp"
    assert sys.modules["zz824own"].__path__ == [str(tmp_path / "zz824own")]
    assert sys.modules["zz824own"].SHARED == 1

    info = PluginInfo(plugin_id=plugins[0]["plugin_id"])
    info.package_init_file_path = plugins[0]["package_init_file_path"]
    info.package_path = plugins[0]["package_path"]
    info.package_import_location = plugins[0]["package_import_location"]
    loader.plugins_info = {info.plugin_id: info}
    assert loader._import_single_plugin(info.plugin_id)
    assert sys.modules[info.plugin_class_import_location].Plugin.value == "ok"


def test_own_name_no_sys_path_change(tmp_path: Path) -> None:
    """Own-name registration leaves ``sys.path`` and ``sys.meta_path`` alone."""
    _own_plugin_with_libs(tmp_path, "zz824own", "zzp")
    path_before = list(sys.path)
    meta_before = list(sys.meta_path)
    _loader(tmp_path)._discover_plugins()
    assert sys.path == path_before
    assert sys.meta_path == meta_before


def test_own_name_rediscovery_reuses_root(tmp_path: Path) -> None:
    """A second discovery keeps the plugin and the same package module."""
    _own_plugin_with_libs(tmp_path, "zz824own", "zzp")
    loader = _loader(tmp_path)
    loader._discover_plugins()
    first = sys.modules["zz824own"]
    again = loader._discover_plugins().plugins
    assert [str(p["plugin_id"]) for p in again] == ["plugins.zz824own.zzp"]
    assert sys.modules["zz824own"] is first


def test_stdlib_name_refused(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """A folder named like a stdlib module is refused and the stdlib module kept."""
    _write_plugin(tmp_path, "json", "zzp")
    _write_plugin(tmp_path, "zz824ok", "zzq")
    stdlib_json = sys.modules["json"]
    with caplog.at_level(logging.ERROR):
        plugins = _loader(tmp_path)._discover_plugins().plugins
    ids = [str(p["plugin_id"]) for p in plugins]
    assert ids == ["plugins.zz824ok.zzq"]
    assert sys.modules["json"] is stdlib_json
    assert not imputils.is_registered_package_root("json")
    assert any("json" in r.getMessage() and r.levelno == logging.ERROR for r in caplog.records)


def test_bundled_name_refused_not_registered(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A folder named like a bundled package is refused per plugin, never registered."""
    bundled = tmp_path / "bundled"
    user = tmp_path / "user"
    _write_plugin(bundled / "zzbundled110", "core", "zzb")
    (bundled / "zzbundled110" / "__init__.py").write_text("")
    _write_plugin(user, "core", "zzu")
    sys.path.insert(0, str(bundled))
    try:
        loader = _loader(user, bundled / "zzbundled110")
        with caplog.at_level(logging.ERROR):
            ids = [str(p["plugin_id"]) for p in loader._discover_plugins().plugins]
    finally:
        sys.path.remove(str(bundled))
        for name in [n for n in sys.modules if n.startswith("zzbundled110")]:
            del sys.modules[name]
    assert ids == ["plugins.core.zzb"]
    assert any("collides with a bundled" in r.getMessage() for r in caplog.records)
    assert not imputils.is_registered_package_root("core")


def test_own_name_init_error(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """A package whose ``__init__`` raises is logged, recorded and skipped."""
    _write_plugin(tmp_path, "zz824bad", "zzp")
    (tmp_path / "zz824bad" / "__init__.py").write_text('raise RuntimeError("boom")\n')
    _write_plugin(tmp_path, "zz824ok", "zzq")
    with caplog.at_level(logging.ERROR):
        result = _loader(tmp_path)._discover_plugins()
    assert "zz824bad" in result.errors
    assert "zz824bad" not in sys.modules
    assert [str(p["plugin_id"]) for p in result.plugins] == ["plugins.zz824ok.zzq"]
    assert any("zz824bad" in r.getMessage() for r in caplog.records)


def test_folder_without_init_ignored(tmp_path: Path) -> None:
    """A namespace-style folder (no ``__init__.py``) yields no plugins and is not registered."""
    _write_plugin(tmp_path, "zz824ns", "zzp")
    (tmp_path / "zz824ns" / "__init__.py").unlink()
    result = _loader(tmp_path)._discover_plugins()
    assert result.plugins == []
    assert "zz824ns" not in sys.modules


def test_non_identifier_folder_stays_userplugins(tmp_path: Path) -> None:
    """A folder whose name cannot be imported by name keeps the userplugins route."""
    _write_plugin(tmp_path, "zz824-x", "zzp")
    plugins = _loader(tmp_path)._discover_plugins().plugins
    assert [p["package_import_location"] for p in plugins] == [f"{ROOT}.zz824-x.zzp"]


def test_own_name_unload_reload(tmp_path: Path) -> None:
    """An own-name plugin unloads, keeps its package root and reloads new code."""
    _write_plugin(tmp_path, "zz824own", "zzp", "v1")
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
    assert [n for n in sys.modules if n.startswith("zz824own.zzp")] == []
    assert "zz824own" in sys.modules

    _write_plugin(tmp_path, "zz824own", "zzp", "version-two")
    assert _import().version == "version-two"


def test_register_package_root(tmp_path: Path) -> None:
    """The package is built from the folder's ``__init__`` and reused or replaced."""
    first_dir = tmp_path / "a"
    first_dir.mkdir()
    (first_dir / "__init__.py").write_text("X = 1\n")
    module = imputils.register_package_root("zz824x", first_dir)
    assert module.__spec__ is not None
    assert Path(str(module.__spec__.origin)) == first_dir / "__init__.py"
    assert module.__path__ == [str(first_dir)]
    assert imputils.is_registered_package_root("zz824x")
    assert imputils.register_package_root("zz824x", first_dir) is module

    second_dir = tmp_path / "b"
    second_dir.mkdir()
    (second_dir / "__init__.py").write_text("X = 2\n")
    replaced = imputils.register_package_root("zz824x", second_dir)
    assert replaced is not module
    assert replaced.X == 2


def test_register_package_root_cleans_up_on_error(tmp_path: Path) -> None:
    """A raising ``__init__`` leaves nothing in ``sys.modules``."""
    (tmp_path / "__init__.py").write_text("raise ValueError('bad')\n")
    with pytest.raises(ValueError, match="bad"):
        imputils.register_package_root("zz824x", tmp_path)
    assert "zz824x" not in sys.modules


def test_find_packages_include_skips_others(tmp_path: Path) -> None:
    """``include`` scans only the named folders and imports no other."""
    _write_plugin(tmp_path, "zz824def", "zzp")
    _write_plugin(tmp_path, "zz824ok", "zzq")
    imputils.register_import_root(ROOT, tmp_path)
    scan = imputils.find_packages_and_plugins(tmp_path, f"{ROOT}.", include={"zz824def"})
    assert [p["package_import_location"] for p in scan.plugins] == [f"{ROOT}.zz824def.zzp"]
    assert f"{ROOT}.zz824ok" not in sys.modules

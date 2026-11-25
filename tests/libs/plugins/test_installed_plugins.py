# Project: bastproxy
# Filename: tests/libs/plugins/test_installed_plugins.py
#
# File Description: Tests that plugins load from installed packages (entry points)
#
# By: Bast
"""Tests for plugins discovered through the ``bastproxy.plugins`` entry-point group (#579)."""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterator
from importlib.metadata import EntryPoint
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs.plugins import imputils
from bastproxy.libs.plugins import loader as loader_module
from bastproxy.libs.plugins.loader import PluginLoader, installed_plugin_search_paths
from bastproxy.libs.plugins.plugininfo import PluginInfo
from tests.libs.plugins.test_user_plugins import ROOT, _write_plugin

GROUP = "bastproxy.plugins"
PREFIXES = (
    "userplugins",
    "zzinst",
    "zzinst579",
    "zzinst579b",
    "zzbundled579",
    "zzbroken579",
    "zzmod579",
)


def _ep(name: str, value: str) -> EntryPoint:
    return EntryPoint(name=name, value=value, group=GROUP)


def _clean_modules() -> None:
    for name in [n for n in sys.modules if n.split(".")[0] in PREFIXES]:
        del sys.modules[name]


@pytest.fixture(autouse=True)
def clean_modules() -> Iterator[None]:
    """Remove the throwaway modules before and after each test."""
    _clean_modules()
    yield
    _clean_modules()


def _loader(user_dir: Path, eps: list[EntryPoint], bundled_dir: Path | None = None) -> PluginLoader:
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
                "import_prefix": "zzbundled579.",
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
    loader.plugin_search_paths.extend(installed_plugin_search_paths(eps))
    return loader


def test_search_path_for_entry_point(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An entry yields the package dir, import prefix, ID prefix and source."""
    _write_plugin(tmp_path / "site", "zzinst579", "zzp")
    monkeypatch.syspath_prepend(str(tmp_path / "site"))
    paths = installed_plugin_search_paths([_ep("zzinst", "zzinst579")])
    assert paths == [
        {
            "path": tmp_path / "site" / "zzinst579",
            "import_prefix": "zzinst579.",
            "id_prefix": "plugins.zzinst.",
            "source": "installed",
        }
    ]


def test_discovery_matches_user_dir_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The ID comes from the entry name, the same as a user-dir copy of the package."""
    site = tmp_path / "site"
    _write_plugin(site, "zzinst579", "zzp")
    monkeypatch.syspath_prepend(str(site))
    loader = _loader(tmp_path / "user", [_ep("zzinst", "zzinst579")])
    plugins = loader._discover_plugins().plugins
    inst = [p for p in plugins if p["source"] == "installed"]
    assert [str(p["plugin_id"]) for p in inst] == ["plugins.zzinst.zzp"]
    assert inst[0]["package_import_location"] == "zzinst579.zzp"

    user_dir = tmp_path / "user2"
    _write_plugin(user_dir, "zzinst", "zzp")
    user = _loader(user_dir, [])._discover_plugins().plugins
    assert [str(p["plugin_id"]) for p in user] == ["plugins.zzinst.zzp"]


def test_broken_entries_are_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Broken entries log an error and are skipped while a valid one still works."""
    site = tmp_path / "site"
    _write_plugin(site, "zzinst579", "zzp")
    (site / "zzbroken579").mkdir()
    (site / "zzbroken579" / "__init__.py").write_text("raise RuntimeError('boom')\n")
    (site / "zzmod579.py").write_text("")
    monkeypatch.syspath_prepend(str(site))
    eps = [
        _ep("zzgood", "zzinst579"),
        _ep("zzmissing", "zznothere579"),
        _ep("zzbroken", "zzbroken579"),
        _ep("zzmod", "zzmod579"),
        _ep("dotted.name", "zzinst579"),
    ]
    with caplog.at_level("ERROR"):
        paths = installed_plugin_search_paths(eps)
    assert [p["id_prefix"] for p in paths] == ["plugins.zzgood."]
    assert len([r for r in caplog.records if r.levelname == "ERROR"]) == 4


def test_real_loader_sources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``PluginLoader()`` appends installed sources and survives a broken entry."""
    site = tmp_path / "site"
    _write_plugin(site, "zzinst579", "zzp")
    monkeypatch.syspath_prepend(str(site))
    eps = [_ep("zzinst", "zzinst579"), _ep("zzbad", "zznothere579")]
    monkeypatch.setattr(loader_module, "entry_points", lambda group: eps)
    loader = PluginLoader()
    assert [s["source"] for s in loader.plugin_search_paths] == ["bundled", "user", "installed"]


def test_user_overrides_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A user copy wins with a warning; an installed-only sibling is still found."""
    site = tmp_path / "site"
    _write_plugin(site, "zzinst579", "zzp")
    _write_plugin(site, "zzinst579", "zzsibling")
    monkeypatch.syspath_prepend(str(site))
    user = tmp_path / "user"
    _write_plugin(user, "zzinst", "zzp")
    loader = _loader(user, [_ep("zzinst", "zzinst579")])
    with caplog.at_level("WARNING"):
        plugins = loader._discover_plugins().plugins
    by_id = {str(p["plugin_id"]): p for p in plugins}
    assert by_id["plugins.zzinst.zzp"]["source"] == "user"
    assert by_id["plugins.zzinst.zzsibling"]["source"] == "installed"
    assert [
        r
        for r in caplog.records
        if r.levelname == "WARNING" and "plugins.zzinst.zzp" in r.getMessage()
    ]


def test_bundled_beats_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """An installed plugin in a bundled package is refused with an error."""
    bundled = tmp_path / "bundled"
    _write_plugin(bundled / "zzbundled579", "zzinst", "zzb")
    (bundled / "zzbundled579" / "__init__.py").write_text("")
    site = tmp_path / "site"
    _write_plugin(site, "zzinst579", "zzp")
    monkeypatch.syspath_prepend(str(bundled))
    monkeypatch.syspath_prepend(str(site))
    loader = _loader(tmp_path / "user", [_ep("zzinst", "zzinst579")], bundled / "zzbundled579")
    with caplog.at_level("ERROR"):
        plugins = loader._discover_plugins().plugins
    by_id = {str(p["plugin_id"]): p for p in plugins}
    assert by_id["plugins.zzinst.zzb"]["source"] == "bundled"
    assert "plugins.zzinst.zzp" not in by_id
    assert [r for r in caplog.records if r.levelname == "ERROR"]


def test_first_installed_entry_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Two entries with the same name resolve to the first in sort order, with an error."""
    site = tmp_path / "site"
    _write_plugin(site, "zzinst579", "zzp")
    _write_plugin(site, "zzinst579b", "zzp")
    monkeypatch.syspath_prepend(str(site))
    eps = [_ep("zzsame", "zzinst579b"), _ep("zzsame", "zzinst579")]
    loader = _loader(tmp_path / "user", eps)
    with caplog.at_level("ERROR"):
        plugins = loader._discover_plugins().plugins
    inst = [p for p in plugins if p["source"] == "installed"]
    assert len(inst) == 1
    assert [r for r in caplog.records if r.levelname == "ERROR"]


def test_installed_plugin_imports_unloads_and_reloads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An installed plugin imports, unloads and reloads with changed code."""
    site = tmp_path / "site"
    _write_plugin(site, "zzinst579", "zzp", "v1")
    monkeypatch.syspath_prepend(str(site))
    loader = _loader(tmp_path / "user", [_ep("zzinst", "zzinst579")])
    plugins = [p for p in loader._discover_plugins().plugins if p["source"] == "installed"]
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
    assert [n for n in sys.modules if n.startswith("zzinst579.zzp")] == []

    _write_plugin(site, "zzinst579", "zzp", "version-two")
    assert _import().version == "version-two"


def _installed_with_libs(site: Path) -> None:
    """Write the installed package ``zzinst579`` with plugins and a ``_libs`` module."""
    _write_plugin(site, "zzinst579", "zzp")
    _write_plugin(site, "zzinst579", "zzsibling")
    (site / "zzinst579" / "_libs").mkdir()
    (site / "zzinst579" / "_libs" / "__init__.py").write_text('ORIGIN = "installed"\n')


def test_installed_import_name_folder_stays_userplugins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A user folder named like an entry's import name overrides per plugin, not by shadowing."""
    site = tmp_path / "site"
    _installed_with_libs(site)
    monkeypatch.syspath_prepend(str(site))
    user = tmp_path / "user"
    _write_plugin(user, "zzinst579", "zzp")
    (user / "zzinst579" / "zzp" / "plugin" / "_plugin.py").write_text(
        "from zzinst579._libs import ORIGIN\n\n\nclass Plugin:\n    origin = ORIGIN\n"
    )
    loader = _loader(user, [_ep("zz824e", "zzinst579")])
    with caplog.at_level(logging.WARNING):
        result = loader._discover_plugins()
    by_loc = {p["package_import_location"]: p for p in result.plugins}
    assert f"{ROOT}.zzinst579.zzp" in by_loc
    assert by_loc[f"{ROOT}.zzinst579.zzp"]["source"] == "user"
    assert by_loc["zzinst579.zzsibling"]["source"] == "installed"
    assert not imputils.is_registered_package_root("zzinst579")
    assert any(r.levelno == logging.ERROR for r in caplog.records) is False

    plugin = by_loc[f"{ROOT}.zzinst579.zzp"]
    info = PluginInfo(plugin_id=plugin["plugin_id"])
    info.package_init_file_path = plugin["package_init_file_path"]
    info.package_path = plugin["package_path"]
    info.package_import_location = plugin["package_import_location"]
    loader.plugins_info = {info.plugin_id: info}
    assert loader._import_single_plugin(info.plugin_id)
    assert sys.modules[info.plugin_class_import_location].Plugin.origin == "installed"
    assert Path(str(sys.modules["zzinst579"].__file__)).is_relative_to(site)


def test_installed_entry_name_folder_stays_userplugins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A user folder named like the entry name keeps the per-plugin override."""
    site = tmp_path / "site"
    _write_plugin(site, "zzinst579", "zzp")
    monkeypatch.syspath_prepend(str(site))
    user = tmp_path / "user"
    _write_plugin(user, "zzinst", "zzp")
    with caplog.at_level(logging.WARNING):
        plugins = _loader(user, [_ep("zzinst", "zzinst579")])._discover_plugins().plugins
    assert [p["package_import_location"] for p in plugins] == [f"{ROOT}.zzinst.zzp"]
    assert any("overrides" in r.getMessage() for r in caplog.records)


def test_installed_value_name_folder_not_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A folder named like an installed import name is not refused by the name check."""
    site = tmp_path / "site"
    _write_plugin(site, "zzinst579", "zzp")
    monkeypatch.syspath_prepend(str(site))
    user = tmp_path / "user"
    _write_plugin(user, "zzinst579", "zzother")
    with caplog.at_level(logging.ERROR):
        plugins = _loader(user, [_ep("zz824e", "zzinst579")])._discover_plugins().plugins
    assert f"{ROOT}.zzinst579.zzother" in [p["package_import_location"] for p in plugins]
    assert not any(r.levelno == logging.ERROR for r in caplog.records)

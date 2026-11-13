# Project: bastproxy
# Filename: tests/libs/plugins/test_discovery_results.py
#
# File Description: Tests for the dataclasses plugin discovery returns
#
# By: Bast
"""Tests for ``DiscoveryResult`` and ``DependencyResolution`` (issue #426)."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from bastproxy.libs.plugins import imputils
from bastproxy.libs.plugins.dependency import DependencyResolution, PluginDependencyResolver
from bastproxy.libs.plugins.imputils import DiscoveryResult
from bastproxy.libs.plugins.plugininfo import PluginInfo
from tests.libs.plugins.test_dependency_resolver import _infos
from tests.libs.plugins.test_user_plugins import ROOT, _clean_modules, _loader, _write_plugin

SCAN_ROOT = "zzdiscres426"


@pytest.fixture(autouse=True)
def clean_modules() -> Iterator[None]:
    """Remove the throwaway modules before and after each test."""
    _clean_modules()
    yield
    _clean_modules()
    for name in [n for n in sys.modules if n == SCAN_ROOT or n.startswith(f"{SCAN_ROOT}.")]:
        del sys.modules[name]


def test_result_dataclasses_are_slotted() -> None:
    """Both result classes use ``slots=True``."""
    assert not hasattr(DiscoveryResult(), "__dict__")
    assert not hasattr(DependencyResolution(), "__dict__")


def test_discovery_result_defaults_are_not_shared() -> None:
    """Each ``DiscoveryResult`` gets its own empty containers."""
    first = DiscoveryResult()
    second = DiscoveryResult()
    assert (first.packages, first.plugins, first.errors) == ([], [], {})
    first.packages.append({"package_id": "x"})
    first.plugins.append({"plugin_id": "y"})
    first.errors["z"] = ()
    assert (second.packages, second.plugins, second.errors) == ([], [], {})


def test_find_packages_and_plugins_returns_discovery_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tree with one plugin and one plain package fills ``plugins`` and ``packages``."""
    _write_plugin(tmp_path / SCAN_ROOT, "mine", "zzp")
    plain = tmp_path / SCAN_ROOT / "plainpkg"
    plain.mkdir()
    (plain / "__init__.py").write_text("")
    (tmp_path / SCAN_ROOT / "__init__.py").write_text("")
    monkeypatch.syspath_prepend(str(tmp_path))

    result = imputils.find_packages_and_plugins(tmp_path / SCAN_ROOT, f"{SCAN_ROOT}.")

    assert isinstance(result, DiscoveryResult)
    assert [p["package_import_location"] for p in result.plugins] == [f"{SCAN_ROOT}.mine.zzp"]
    assert f"{SCAN_ROOT}.plainpkg" in [p["package_id"] for p in result.packages]
    assert result.errors == {}


def test_discover_plugins_returns_discovery_result(tmp_path: Path) -> None:
    """``_discover_plugins`` returns a ``DiscoveryResult`` that also lists the packages."""
    _write_plugin(tmp_path, "mine", "zzu")
    result = _loader(tmp_path)._discover_plugins()
    assert isinstance(result, DiscoveryResult)
    assert [p["plugin_id"] for p in result.plugins] == ["plugins.mine.zzu"]
    assert f"{ROOT}.mine" in [p["package_id"] for p in result.packages]
    assert result.errors == {}


def test_resolve_returns_dependency_resolution() -> None:
    """``resolve`` returns a ``DependencyResolution`` on success and on failure."""
    infos = _infos({"a": [], "b": ["a"], "c": ["nope"]})
    ok = PluginDependencyResolver(infos).resolve(["b"])
    assert isinstance(ok, DependencyResolution)
    assert (ok.order, ok.failed) == (["a", "b"], {})

    bad = PluginDependencyResolver(infos).resolve(["c"])
    assert isinstance(bad, DependencyResolution)
    assert bad.order == []
    assert set(bad.failed) == {"nope", "c"}


def test_check_file_is_valid_python_code(tmp_path: Path) -> None:
    """``None`` for valid code, the ``SyntaxError`` for invalid code."""
    info = PluginInfo("plugins.other.thing")
    good = tmp_path / "good.py"
    good.write_text("x = 1\n", encoding="utf-8")
    bad = tmp_path / "bad.py"
    bad.write_text("def (:\n", encoding="utf-8")
    assert info.check_file_is_valid_python_code(good) is None
    assert isinstance(info.check_file_is_valid_python_code(bad), SyntaxError)


def test_get_file_data_records_invalid_python_code(tmp_path: Path) -> None:
    """``get_file_data`` still records ``invalid_python_code`` and ``exception``."""
    (tmp_path / "bad.py").write_text("def (:\n", encoding="utf-8")
    info = PluginInfo("plugins.other.thing")
    info.package_path = tmp_path
    info.package_import_location = "pkg.thing"
    files = info.get_file_data()
    entry = files[tmp_path]["files"]["bad.py"] if tmp_path in files else None
    if entry is None:
        entry = next(iter(files.values()))["files"]["bad.py"]
    assert entry["invalid_python_code"] is True
    assert isinstance(entry["exception"], SyntaxError)
    assert info.is_valid_python_code is False

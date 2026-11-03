# Project: bastproxy
# Filename: tests/libs/plugins/test_plugininfo_file_data.py
#
# File Description: Tests for the PluginInfo.get_file_data cache and keys
#
# By: Bast
"""Tests that get_file_data caches unchanged files and keys dirs by relative path (#132)."""

from __future__ import annotations

import datetime
import os
from pathlib import Path
from unittest.mock import patch

from bastproxy.libs.plugins.plugininfo import PluginInfo


def _make_info(root: Path) -> PluginInfo:
    (root / "sub" / "deep").mkdir(parents=True)
    (root / "other" / "deep").mkdir(parents=True)
    for rel in (
        "__init__.py",
        "plugin.py",
        "sub/__init__.py",
        "sub/mod.py",
        "sub/deep/mod.py",
        "other/deep/mod.py",
    ):
        (root / rel).write_text("x = 1\n", encoding="utf-8")
    info = PluginInfo("plugins.other.thing")
    info.package_path = root
    info.package_import_location = "pkg.thing"
    return info


def _spy(info: PluginInfo) -> list[str]:
    calls: list[str] = []
    real = info.check_file_is_valid_python_code

    def wrapper(file: Path) -> tuple[bool, Exception | None]:
        calls.append(str(file.relative_to(info.package_path).as_posix()))
        return real(file)

    info.check_file_is_valid_python_code = wrapper  # type: ignore[method-assign]
    return calls


def test_second_scan_reparses_nothing(tmp_path: Path) -> None:
    info = _make_info(tmp_path)
    calls = _spy(info)
    first = info.get_file_data()
    assert len(calls) == 6
    calls.clear()
    second = info.get_file_data()
    assert calls == []
    assert second == first


def test_modified_file_is_the_only_one_reparsed(tmp_path: Path) -> None:
    info = _make_info(tmp_path)
    calls = _spy(info)
    info.get_file_data()
    calls.clear()
    target = tmp_path / "sub" / "mod.py"
    st = target.stat()
    os.utime(target, (st.st_atime, st.st_mtime + 10))
    info.get_file_data()
    assert calls == ["sub/mod.py"]


def test_same_named_dirs_in_different_parents_are_distinct(tmp_path: Path) -> None:
    info = _make_info(tmp_path)
    files = info.get_file_data()
    assert set(files) == {".", "sub", "sub/deep", "other/deep"}
    assert files["sub/deep"]["files"]["mod.py"]["full_path"] == tmp_path / "sub/deep/mod.py"
    assert files["other/deep"]["files"]["mod.py"]["full_path"] == tmp_path / "other/deep/mod.py"
    assert len(info.find_file_by_name("mod.py")) == 3


def test_init_files_included_with_package_import_location(tmp_path: Path) -> None:
    info = _make_info(tmp_path)
    files = info.get_file_data()
    assert files["."]["files"]["__init__.py"]["full_import_location"] == "pkg.thing"
    assert files["sub"]["files"]["__init__.py"]["full_import_location"] == "pkg.thing.sub"
    assert files["sub/deep"]["files"]["mod.py"]["full_import_location"] == "pkg.thing.sub.deep.mod"
    assert files["."]["files"]["plugin.py"]["full_import_location"] == "pkg.thing.plugin"


def test_init_edit_reported_changed(tmp_path: Path) -> None:
    info = _make_info(tmp_path)
    info.runtime_info.is_loaded = True
    info.runtime_info.imported_time = datetime.datetime.now(datetime.UTC) + datetime.timedelta(
        hours=1
    )
    assert info.get_changed_files() == []
    init = tmp_path / "__init__.py"
    future = (datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=2)).timestamp()
    os.utime(init, (future, future))
    changed = info.get_changed_files()
    assert [c["full_path"] for c in changed] == [init]
    # still reported on an unchanged rescan (cache hit refreshes the flag)
    assert [c["full_path"] for c in info.get_changed_files()] == [init]


def test_invalid_files_and_find_by_name(tmp_path: Path) -> None:
    info = _make_info(tmp_path)
    (tmp_path / "sub" / "bad.py").write_text("def (:\n", encoding="utf-8")
    invalid = info.get_invalid_python_files()
    assert [i["full_path"] for i in invalid] == [tmp_path / "sub" / "bad.py"]
    # cached invalid entry still reported, without reparse
    with patch.object(PluginInfo, "check_file_is_valid_python_code") as mocked:
        assert len(info.get_invalid_python_files()) == 1
        mocked.assert_not_called()
    found = info.find_file_by_name("plugin.py")
    assert len(found) == 1
    assert found[0]["full_import_location"] == "pkg.thing.plugin"

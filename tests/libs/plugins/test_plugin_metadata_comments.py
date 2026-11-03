# Project: bastproxy
# Filename: tests/libs/plugins/test_plugin_metadata_comments.py
#
# File Description: Tests for comment and bad-value handling in plugin metadata
#
# By: Bast
"""Tests that plugin metadata parses with trailing comments and survives bad values (#125)."""

from __future__ import annotations

from pathlib import Path

import pytest

from bastproxy.libs.exceptions import PluginValidationError
from bastproxy.libs.plugins.plugininfo import PluginInfo


def _parse(tmp_path: Path, content: str, plugin_id: str = "plugins.other.thing") -> PluginInfo:
    init = tmp_path / "__init__.py"
    init.write_text(content, encoding="utf-8")
    info = PluginInfo(plugin_id)
    info.package_import_location = f"pkg.{plugin_id}"
    info.package_init_file_path = init
    info.update_from_init()
    return info


_GOOD = (
    'PLUGIN_NAME = "Thing"\n'
    "PLUGIN_PURPOSE = 'Does things'\n"
    'PLUGIN_AUTHOR = "Bast"\n'
    "PLUGIN_VERSION = 3\n"
    "PLUGIN_REQUIRED = True\n"
)


def test_trailing_comments_on_every_line(tmp_path: Path) -> None:
    content = "".join(f"{line.rstrip()}  # a comment\n" for line in _GOOD.splitlines())
    info = _parse(tmp_path, content)
    assert info.is_plugin is True
    assert info.name == "Thing"
    assert info.purpose == "Does things"
    assert info.author == "Bast"
    assert info.version == 3
    assert info.is_required is True
    assert info.import_errors == []


def test_required_false_with_comment(tmp_path: Path) -> None:
    info = _parse(tmp_path, _GOOD.replace("True", "False  # not required"))
    assert info.is_required is False


def test_hash_inside_string_is_kept(tmp_path: Path) -> None:
    info = _parse(tmp_path, 'PLUGIN_NAME = "Thing # 1"  # c\n')
    assert info.name == "Thing # 1"


def test_last_assignment_wins(tmp_path: Path) -> None:
    info = _parse(tmp_path, "PLUGIN_VERSION = 1\nPLUGIN_VERSION = 2\n")
    assert info.version == 2


@pytest.mark.parametrize("bad", ['"x"', "True", "1.5", "int('3')", "SOME_NAME"])
def test_bad_version_records_error_and_keeps_others(tmp_path: Path, bad: str) -> None:
    info = _parse(tmp_path, _GOOD.replace("PLUGIN_VERSION = 3", f"PLUGIN_VERSION = {bad}"))
    assert info.version == -1
    assert info.name == "Thing"
    assert info.author == "Bast"
    assert info.is_plugin is True
    assert len(info.import_errors) == 1
    location, exc = info.import_errors[0]
    assert location == info.package_import_location
    assert isinstance(exc, PluginValidationError)


def test_non_literal_name_records_error(tmp_path: Path) -> None:
    info = _parse(tmp_path, 'PLUGIN_NAME = "a" + "b"\nPLUGIN_AUTHOR = "Bast"\n')
    assert info.name == ""
    assert info.is_plugin is False
    assert info.author == "Bast"
    assert len(info.import_errors) == 1


def test_wrong_type_required_records_error(tmp_path: Path) -> None:
    info = _parse(tmp_path, "PLUGIN_REQUIRED = 1\n")
    assert info.is_required is False
    assert len(info.import_errors) == 1


def test_rerun_does_not_accumulate_errors(tmp_path: Path) -> None:
    info = _parse(tmp_path, 'PLUGIN_VERSION = "x"\n')
    info.update_from_init()
    info.update_from_init()
    assert len(info.import_errors) == 1


def test_syntax_error_parses_nothing(tmp_path: Path) -> None:
    info = _parse(tmp_path, 'PLUGIN_NAME = "Thing"\nPLUGIN_VERSION = (\n')
    assert info.name == ""
    assert info.is_plugin is False
    assert info.import_errors == []


def test_one_bad_plugin_does_not_stop_others(tmp_path: Path) -> None:
    contents = {
        "a": _GOOD,
        "b": _GOOD.replace("PLUGIN_VERSION = 3", "PLUGIN_VERSION = 1  # first"),
        "c": _GOOD.replace("PLUGIN_VERSION = 3", 'PLUGIN_VERSION = "x"'),
        "d": _GOOD,
    }
    infos = {}
    for key, content in contents.items():
        sub = tmp_path / key
        sub.mkdir()
        infos[key] = _parse(sub, content, f"plugins.other.{key}")
    assert [infos[k].version for k in "abcd"] == [3, 1, -1, 3]
    assert [bool(infos[k].import_errors) for k in "abcd"] == [False, False, True, False]
    assert all(infos[k].name == "Thing" for k in "abcd")

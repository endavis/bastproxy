# Project: bastproxy
# Filename: tests/libs/plugins/test_plugin_required.py
#
# File Description: Tests for PLUGIN_REQUIRED parsing
#
# By: Bast
"""Tests for parsing ``PLUGIN_REQUIRED`` from a plugin's ``__init__.py`` (issue #117)."""

from __future__ import annotations

from pathlib import Path

import pytest

from bastproxy.libs.plugins.plugininfo import PluginInfo

_META = """\
PLUGIN_NAME = 'Thing'
PLUGIN_PURPOSE = 'Does things'
PLUGIN_AUTHOR = 'Bast'
PLUGIN_VERSION = 3
"""


def _parse(tmp_path: Path, content: str, plugin_id: str = "plugins.other.thing") -> PluginInfo:
    init = tmp_path / "__init__.py"
    init.write_text(content, encoding="utf-8")
    info = PluginInfo(plugin_id)
    info.package_init_file_path = init
    info.update_from_init()
    return info


def test_required_true_in_non_core_package(tmp_path: Path) -> None:
    info = _parse(tmp_path, _META + "PLUGIN_REQUIRED = True\n")
    assert info.is_required is True


@pytest.mark.parametrize("line", ["PLUGIN_REQUIRED = False\n", ""])
def test_required_false_or_absent(tmp_path: Path, line: str) -> None:
    info = _parse(tmp_path, _META + line)
    assert info.is_required is False


def test_bare_required_name_is_not_recognised(tmp_path: Path) -> None:
    info = _parse(tmp_path, _META + "REQUIRED = True\n")
    assert info.is_required is False


def test_required_first_still_parses_all_metadata(tmp_path: Path) -> None:
    content = (
        "PLUGIN_REQUIRED = True\n" + _META + "\nPLUGIN_DEPENDENCIES = ['plugins.core.events']\n"
    )
    info = _parse(tmp_path, content)
    assert info.is_required is True
    assert info.is_plugin is True
    assert info.name == "Thing"
    assert info.purpose == "Does things"
    assert info.author == "Bast"
    assert info.version == 3
    assert info.dependencies == ["plugins.core.events"]


def test_real_mudcmds_init_parses_as_required() -> None:
    import bastproxy.plugins.core.mudcmds as mudcmds_pkg

    assert mudcmds_pkg.__file__ is not None
    info = PluginInfo("plugins.core.mudcmds")
    info.package_init_file_path = Path(mudcmds_pkg.__file__)
    info.update_from_init()
    assert info.is_required is True

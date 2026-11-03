# Project: bastproxy
# Filename: tests/libs/plugins/test_plugin_metadata_quotes.py
#
# File Description: Tests for quote handling in plugin metadata parsing
#
# By: Bast
"""Tests that PLUGIN_NAME/AUTHOR/PURPOSE parse with either quote style (issue #119)."""

from __future__ import annotations

from pathlib import Path

import pytest

from bastproxy.libs.plugins.plugininfo import PluginInfo

_PLUGINS_ROOT = Path(__file__).resolve().parents[3] / "src" / "bastproxy" / "plugins"


def _parse_file(init: Path, plugin_id: str = "plugins.other.thing") -> PluginInfo:
    info = PluginInfo(plugin_id)
    info.package_init_file_path = init
    info.update_from_init()
    return info


def _parse(tmp_path: Path, content: str) -> PluginInfo:
    init = tmp_path / "__init__.py"
    init.write_text(content, encoding="utf-8")
    return _parse_file(init)


@pytest.mark.parametrize("quote", ["'", '"'])
def test_quoted_metadata_parses(tmp_path: Path, quote: str) -> None:
    q = quote
    content = (
        f"PLUGIN_NAME = {q}Thing{q}\n"
        f"PLUGIN_PURPOSE = {q}Does things{q}\n"
        f"PLUGIN_AUTHOR = {q}Bast{q}\n"
        "PLUGIN_VERSION = 1\n"
    )
    info = _parse(tmp_path, content)
    assert info.is_plugin is True
    assert info.name == "Thing"
    assert info.purpose == "Does things"
    assert info.author == "Bast"


@pytest.mark.parametrize("field", ["NAME", "AUTHOR", "PURPOSE"])
def test_mismatched_quotes_do_not_match(tmp_path: Path, field: str) -> None:
    info = _parse(tmp_path, f"PLUGIN_{field} = 'x\"\n")
    assert info.name == ""
    assert info.author == ""
    assert info.purpose == ""
    assert info.is_plugin is False


def test_real_cmdq_init_parses() -> None:
    info = _parse_file(_PLUGINS_ROOT / "core" / "cmdq" / "__init__.py", "plugins.core.cmdq")
    assert info.name == "Command Queue"
    assert info.author == "Bast"
    assert info.purpose == "Queue commands to the mud"
    assert info.is_plugin is True


def test_every_bundled_plugin_has_metadata() -> None:
    checked = 0
    for init in sorted(_PLUGINS_ROOT.rglob("__init__.py")):
        if "PLUGIN_NAME" not in init.read_text(encoding="utf-8"):
            continue
        info = _parse_file(init)
        assert info.is_plugin, init
        assert info.name, init
        assert info.author, init
        assert info.purpose, init
        checked += 1
    assert checked > 0

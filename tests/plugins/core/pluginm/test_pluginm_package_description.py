"""Tests for the package description constant and ``_package_description`` (issue #666)."""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from bastproxy.plugins.core.pluginm.plugin._pluginm import _package_description

PLUGINS_DIR = Path(__file__).resolve().parents[4] / "src" / "bastproxy" / "plugins"


def test_package_inits_use_package_description_name() -> None:
    """Every package __init__ that defines a description names it PACKAGE_DESCRIPTION."""
    checked = 0
    for init in PLUGINS_DIR.rglob("__init__.py"):
        tree = ast.parse(init.read_text(encoding="utf-8"))
        names = {
            target.id
            for node in tree.body
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        descriptions = {n for n in names if "DESCRIPTION" in n}
        assert descriptions <= {"PACKAGE_DESCRIPTION"}, f"{init}: {descriptions}"
        checked += "PACKAGE_DESCRIPTION" in descriptions
    assert checked >= 2


def _info(location: str) -> Any:
    return cast("Any", SimpleNamespace(package_import_location=location))


def test_test_package_description_is_read() -> None:
    """The test package's description is returned for a plugin inside it."""
    info = _info("bastproxy.plugins.test.cmddec")
    assert _package_description(info) == "Plugins to test things"


def test_missing_package_returns_empty() -> None:
    """A package that cannot be imported yields an empty description."""
    assert _package_description(_info("bastproxy.plugins.nonexistent.x")) == ""

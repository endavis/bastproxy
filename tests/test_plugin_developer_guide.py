"""The plugin developer guide names only API names and imports that exist (#387).

``tests/plugins/test_api_names_exist.py`` scans ``src`` only, so it does not see the docs. This
test applies the same registration check to the guide, and imports every name the guide's Python
excerpts import, so a renamed decorator or record fails here instead of misleading a reader.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

from tests.plugins.test_api_names_exist import Site, _collect, _missing

GUIDE = Path(__file__).resolve().parents[1] / "docs" / "plugin-developer-guide.md"

API_NAME = re.compile(r"\b((?:plugins|libs)\.[\w.]+:[\w.{}]+)")
FENCE = re.compile(r"```python\n(.*?)```", re.DOTALL)
IMPORT_LINE = re.compile(r"^from (bastproxy[\w.]*) import ([\w, ]+)$", re.MULTILINE)


def _guide_api_names() -> dict[str, list[Site]]:
    names: dict[str, list[Site]] = {}
    for number, line in enumerate(GUIDE.read_text(encoding="utf-8").splitlines(), start=1):
        for match in API_NAME.finditer(line):
            name = match.group(1).rstrip(".")
            names.setdefault(name, []).append((GUIDE.name, number))
    return names


def _guide_imports() -> list[tuple[str, str]]:
    imports: list[tuple[str, str]] = []
    for fence in FENCE.findall(GUIDE.read_text(encoding="utf-8")):
        for module, names in IMPORT_LINE.findall(fence):
            imports.extend((module, name.strip()) for name in names.split(","))
    return imports


def test_every_api_name_in_the_guide_is_registered() -> None:
    names = _guide_api_names()
    assert len(names) >= 6
    _, registered, patterns, _ = _collect()
    missing = _missing(names, registered, patterns)
    assert not missing, f"API names in the guide that are not registered: {sorted(missing)}"


def test_every_name_the_guide_imports_exists() -> None:
    imports = _guide_imports()
    assert len(imports) >= 8
    for module, name in imports:
        assert hasattr(importlib.import_module(module), name), f"{module} has no {name}"


def test_a_name_that_does_not_exist_is_reported() -> None:
    _, registered, patterns, _ = _collect()
    fake: dict[str, list[Site]] = {"plugins.core.events:no.such": [(GUIDE.name, 1)]}
    assert set(_missing(fake, registered, patterns)) == set(fake)


def test_the_import_check_notices_a_missing_name() -> None:
    assert not hasattr(importlib.import_module("bastproxy.libs.records"), "NoSuchRecord")


@pytest.mark.parametrize("line", ["from bastproxy.libs.records import A, B"])
def test_import_pattern_matches_a_plain_import(line: str) -> None:
    assert IMPORT_LINE.findall(line) == [("bastproxy.libs.records", "A, B")]

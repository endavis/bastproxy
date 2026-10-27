"""Tests for ``[tool.mutmut]`` in ``pyproject.toml`` (#839, #873).

mutmut 3 renamed two of the keys the template used and reads no ``runner`` at
all. ``paths_to_mutate`` became ``source_paths`` and ``tests_dir`` became
``pytest_add_cli_args_test_selection``; the old names print a deprecation
warning on every mutmut command. ``runner`` fails silently: its pytest flags
never reached pytest, and the ones still wanted now live in
``pytest_add_cli_args``.

The test selection fails in its own way (#873). mutmut runs the selected tests
inside ``mutants/``, a copy that holds the source paths and ``tests/`` but not
``tools/`` or anything else at the repository root. A selected test that
imports ``tools`` cannot be collected there. Since mutmut passes ``-x`` to
pytest, selecting all of ``tests/`` stopped every weekly run before a single
mutant was checked. The selection is now an explicit list, and these tests keep
it complete and runnable.

These are structural asserts on the parsed TOML and on the test files' imports.
They do not run mutmut.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"
TESTS = REPO_ROOT / "tests"

# Keys mutmut 3 deprecates, mapped to the keys that replace them.
REPLACED = {
    "paths_to_mutate": "source_paths",
    "tests_dir": "pytest_add_cli_args_test_selection",
}
# Keys mutmut 3 does not read at all, so nothing warns about them.
UNREAD = {"runner"}

# Tests that import the package but are left out of the selection on purpose.
NOT_SELECTED = {
    "tests/benchmarks": "they time the package and assert nothing, so they cannot kill a mutant",
}


def _mutmut_config() -> dict[str, Any]:
    """Return the ``[tool.mutmut]`` table."""
    with PYPROJECT.open("rb") as f:
        config: dict[str, Any] = tomllib.load(f)["tool"]["mutmut"]
    return config


def _selected_paths(config: dict[str, Any]) -> list[Path]:
    """Return the paths in the test selection, dropping options and node ids."""
    return [
        REPO_ROOT / entry.split("::")[0]
        for entry in config["pytest_add_cli_args_test_selection"]
        if not entry.startswith("-")
    ]


def _is_selected(path: Path, selected: list[Path]) -> bool:
    """Return True if *path* is a selected file or lies under a selected directory."""
    return any(path == s or s in path.parents for s in selected)


def _copied_roots(config: dict[str, Any]) -> set[str]:
    """Return the names at the repository root that mutmut copies into ``mutants/``.

    mutmut 3.8 copies the source paths, ``tests/``, ``test/``, root-level
    ``test*.py`` files and whatever ``also_copy`` lists, plus the lock files and
    project files, which nothing imports (``mutmut/configuration.py``).
    """
    entries = [*config["source_paths"], *config.get("also_copy", []), "tests", "test"]
    return {Path(e).parts[0] for e in entries} | {p.stem for p in REPO_ROOT.glob("test*.py")}


def _left_behind(names: set[str], copied: set[str]) -> set[str]:
    """Return the *names* that live at the repository root but are not copied."""
    return {
        name
        for name in names - copied
        if (REPO_ROOT / name).is_dir() or (REPO_ROOT / f"{name}.py").is_file()
    }


def _imported_names(source: str) -> set[str]:
    """Return the top-level names *source* imports absolutely, at any depth."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def _package_names(config: dict[str, Any]) -> set[str]:
    """Return the import names of the code mutmut mutates."""
    names: set[str] = set()
    for source in config["source_paths"]:
        root = REPO_ROOT / source
        if (root / "__init__.py").is_file():
            names.add(root.name)
            continue
        names |= {p.name for p in root.iterdir() if (p / "__init__.py").is_file()}
        names |= {p.stem for p in root.glob("*.py")}
    return names


def _modules_pytest_loads(selected: list[Path]) -> list[Path]:
    """Return the selected test modules plus the ``conftest.py`` files above them."""
    modules: set[Path] = set()
    for path in selected:
        modules |= set(path.rglob("*.py")) if path.is_dir() else {path}
        start = path if path.is_dir() else path.parent
        for directory in (start, *start.parents):
            if (directory == TESTS or TESTS in directory.parents) and (
                directory / "conftest.py"
            ).is_file():
                modules.add(directory / "conftest.py")
    return sorted(modules)


def test_no_deprecated_or_unread_keys() -> None:
    stale = sorted(set(_mutmut_config()) & (set(REPLACED) | UNREAD))

    assert not stale, f"mutmut 3 deprecates or ignores {stale}"


def test_uses_the_replacement_keys() -> None:
    """Without them mutmut guesses what to mutate and which tests to run."""
    missing = sorted(set(REPLACED.values()) - set(_mutmut_config()))

    assert not missing


def test_every_selected_path_exists() -> None:
    """pytest stops on a path it cannot find, and mutmut then checks no mutant."""
    missing = [
        p.relative_to(REPO_ROOT).as_posix()
        for p in _selected_paths(_mutmut_config())
        if not p.exists()
    ]

    assert not missing, f"pytest_add_cli_args_test_selection names missing paths: {missing}"


def test_selected_tests_import_nothing_mutmut_leaves_behind() -> None:
    """A selected test, or a conftest it loads, must import only what ``mutants/`` holds."""
    config = _mutmut_config()
    copied = _copied_roots(config)
    offenders = {
        path.relative_to(REPO_ROOT).as_posix(): sorted(left)
        for path in _modules_pytest_loads(_selected_paths(config))
        if (left := _left_behind(_imported_names(path.read_text(encoding="utf-8")), copied))
    }

    assert not offenders, (
        "these selected tests import modules that mutmut does not copy into mutants/, "
        f"so its stats run stops before any mutant is checked (#873): {offenders}"
    )


def test_every_test_of_the_package_is_selected() -> None:
    """A test that imports the package but is not selected never runs against a mutant.

    A test that also imports something ``mutants/`` lacks cannot be selected, so
    it is not required here; the previous test would reject it.
    """
    config = _mutmut_config()
    packages = _package_names(config)
    copied = _copied_roots(config)
    selected = _selected_paths(config)
    unselected = []
    for path in sorted(TESTS.rglob("test_*.py")):
        rel = path.relative_to(REPO_ROOT)
        if any(rel.is_relative_to(skipped) for skipped in NOT_SELECTED):
            continue
        names = _imported_names(path.read_text(encoding="utf-8"))
        if (
            names & packages
            and not _left_behind(names, copied)
            and not _is_selected(path, selected)
        ):
            unselected.append(rel.as_posix())

    assert not unselected, (
        f"these tests import {sorted(packages)} but mutmut never runs them: {unselected}. "
        "Add them to pytest_add_cli_args_test_selection in pyproject.toml."
    )


def test_the_import_scanner_sees_every_absolute_import() -> None:
    """Imports inside functions count; relative imports stay inside ``tests/``."""
    source = (
        "import os.path\n"
        "from tools.doit import github\n"
        "from . import sibling\n"
        "def test_x():\n"
        "    import package_name.core\n"
    )

    assert _imported_names(source) == {"os", "tools", "package_name"}


def test_tools_is_left_behind_and_the_tests_are_not() -> None:
    """The import that stopped every weekly run (#873) is the one this check catches."""
    copied = _copied_roots(_mutmut_config())

    assert _left_behind({"tools", "tests", "os"}, copied) == {"tools"}

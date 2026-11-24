"""Tests for ``[tool.mutmut]`` in ``pyproject.toml`` (#839, #873, #1272).

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

A selected test that reads a repository file mutmut does not copy fails the same
way (#1272), so a static scan of the paths the tests build catches that too. The
scan is a heuristic, not a proof; ``_repo_paths_read`` lists what it does not see.

These are structural asserts on the parsed TOML and on the test files' imports
and paths. They do not run mutmut.
"""

from __future__ import annotations

import ast
import functools
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import pytest

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


def _copied_paths(config: dict[str, Any]) -> set[tuple[str, ...]]:
    """Return the repository-relative path prefixes that mutmut copies into ``mutants/``.

    mutmut 3.8.1 copies the source paths, whatever ``also_copy`` lists, ``tests``,
    ``test``, ``setup.cfg``, ``pyproject.toml``, the lock files and root-level
    ``test*.py`` files (``Config.also_copy`` in ``mutmut/configuration.py``). Each
    entry keeps its full prefix, so a narrow ``also_copy`` entry such as
    ``tools/x/generated/`` does not mark all of ``tools`` as copied (#1272). A root
    ``test*.py`` is listed by file name and by stem, for imports.
    """
    entries = [
        *config["source_paths"],
        *config.get("also_copy", []),
        "tests",
        "test",
        "setup.cfg",
        "pyproject.toml",
        "uv.lock",
        "poetry.lock",
        "Pipfile.lock",
        "pdm.lock",
    ]
    copied = {Path(e).parts for e in entries}
    for p in REPO_ROOT.glob("test*.py"):
        copied |= {(p.name,), (p.stem,)}
    return copied


def _file_entries_in_subdirectories(config: dict[str, Any], root: Path) -> dict[str, str]:
    """Map each ``also_copy`` file entry under a subdirectory to the directory to list instead.

    mutmut 3.8.1 copies a file entry with ``shutil.copy2`` into ``mutants/`` without
    creating its parent directory, so it raises ``FileNotFoundError`` (#1275). A
    top-level file and a directory entry (copied with ``copytree``) work.
    """
    return {
        entry: Path(entry).parent.as_posix() + "/"
        for entry in config.get("also_copy", [])
        if len(Path(entry).parts) > 1 and (root / entry).is_file()
    }


def _is_copied(parts: tuple[str, ...], copied: set[tuple[str, ...]]) -> bool:
    """Return True if some copied prefix is a prefix of *parts*."""
    return any(parts[: len(prefix)] == prefix for prefix in copied)


def _left_behind(names: set[str], copied: set[tuple[str, ...]]) -> set[str]:
    """Return the *names* that live at the repository root but are not copied.

    Imports are compared by their first part only: ``tools/__init__.py`` is not
    copied, so ``tools.x.generated`` cannot be imported even if that directory is.
    """
    return {
        name
        for name in names
        if not _is_copied((name,), copied)
        and ((REPO_ROOT / name).is_dir() or (REPO_ROOT / f"{name}.py").is_file())
    }


@functools.cache
def _tracked_paths() -> frozenset[tuple[str, ...]]:
    """Return the git-tracked files as path parts, so ignored directories never count."""
    out = subprocess.run(
        ["git", "ls-files"],
        check=True,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    ).stdout
    return frozenset(Path(line).parts for line in out.splitlines() if line)


def _is_tracked(parts: tuple[str, ...]) -> bool:
    """Return True if *parts* is a tracked file or a directory holding one."""
    return bool(parts) and any(t[: len(parts)] == parts for t in _tracked_paths())


def _is_path_call(node: ast.Call) -> bool:
    """Return True for ``Path(...)`` and ``pathlib.Path(...)`` with one argument."""
    func = node.func
    named = (isinstance(func, ast.Name) and func.id == "Path") or (
        isinstance(func, ast.Attribute) and func.attr == "Path"
    )
    return named and len(node.args) == 1 and not node.keywords


def _str_constants(nodes: list[ast.expr]) -> list[str] | None:
    """Return the string values of *nodes*, or None if any is not a string constant."""
    values = [n.value for n in nodes if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    return values if len(values) == len(nodes) else None


def _resolve(node: ast.expr, module: Path, names: dict[str, Path]) -> Path | None:
    """Evaluate *node* to a real path when it is built from ``__file__``, else None."""
    resolved: Path | None = None
    if isinstance(node, ast.Name):
        resolved = module if node.id == "__file__" else names.get(node.id)
    elif isinstance(node, ast.Call) and _is_path_call(node):
        resolved = _resolve(node.args[0], module, names)
    elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        base = _resolve(node.func.value, module, names)
        if base is not None and node.func.attr in {"resolve", "absolute"} and not node.args:
            resolved = base
        elif base is not None and node.func.attr == "joinpath" and not node.keywords:
            parts = _str_constants(node.args)
            resolved = base.joinpath(*parts) if parts else None
    elif isinstance(node, ast.Attribute) and node.attr == "parent":
        base = _resolve(node.value, module, names)
        resolved = base.parent if base is not None else None
    elif (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "parents"
        and isinstance(node.slice, ast.Constant)
        and isinstance(node.slice.value, int)
    ):
        base = _resolve(node.value.value, module, names)
        try:
            resolved = base.parents[node.slice.value] if base is not None else None
        except IndexError:
            resolved = None
    elif (
        isinstance(node, ast.BinOp)
        and isinstance(node.op, ast.Div)
        and isinstance(node.right, ast.Constant)
        and isinstance(node.right.value, str)
    ):
        base = _resolve(node.left, module, names)
        resolved = base / node.right.value if base is not None else None
    return resolved


def _repo_paths_read(source: str, module: Path) -> set[tuple[str, ...]]:
    """Return the repository paths *source* builds, as parts relative to ``REPO_ROOT``.

    A static heuristic, not a proof. Anchors resolve to real paths when they trace
    back to ``__file__`` through ``Path(...)``, ``.parent``, ``.parents[n]``,
    ``.resolve()``, ``.absolute()``, ``/ "str"``, ``.joinpath("str", ...)`` and
    names bound to those, in any scope (no control-flow tracking). A relative
    ``Path("str")`` or ``open("str")`` resolves against the working directory, which
    is ``mutants/`` under mutmut. Either kind counts only when git tracks it, so a
    path a test creates at run time (a data or output directory) is not reported.
    Paths outside the repository, the repository root and the module itself are
    dropped.

    It does not see ``with_name``, ``with_suffix``, f-strings, ``os.path.join``,
    ``anchor / variable``, or a bare ``Path(__file__).read_text()`` (no joined
    constant).
    """
    tree = ast.parse(source)
    names: dict[str, Path] = {}
    assigns = [
        n
        for n in ast.walk(tree)
        if (
            isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
        )
        or (isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.value)
    ]
    for assign in sorted(assigns, key=lambda n: n.lineno):
        target = assign.targets[0] if isinstance(assign, ast.Assign) else assign.target
        if isinstance(target, ast.Name) and assign.value is not None:
            value = _resolve(assign.value, module, names)
            if value is not None:
                names[target.id] = value

    found: set[tuple[str, ...]] = set()

    def visit(node: ast.AST) -> None:
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node in assigns:
            # An anchor binding is not a read; its uses are.
            value = node.value
            if value is not None and _resolve(value, module, names) is not None:
                return
        if isinstance(node, ast.expr):
            path = _resolve(node, module, names)
            if path is not None:
                if path.is_relative_to(REPO_ROOT) and path not in {REPO_ROOT, module}:
                    parts = path.relative_to(REPO_ROOT).parts
                    if _is_tracked(parts):
                        found.add(parts)
                return
            if isinstance(node, ast.Call) and (
                _is_path_call(node) or (isinstance(node.func, ast.Name) and node.func.id == "open")
            ):
                arg = node.args[0] if node.args else None
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    parts = Path(arg.value).parts
                    if not Path(arg.value).is_absolute() and _is_tracked(parts):
                        found.add(parts)
                    return
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(tree)
    return found


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
    copied = _copied_paths(config)
    offenders = {
        path.relative_to(REPO_ROOT).as_posix(): sorted(left)
        for path in _modules_pytest_loads(_selected_paths(config))
        if (left := _left_behind(_imported_names(path.read_text(encoding="utf-8")), copied))
    }

    assert not offenders, (
        "these selected tests import modules that mutmut does not copy into mutants/, "
        f"so its stats run stops before any mutant is checked (#873): {offenders}"
    )


def test_selected_tests_read_no_file_mutmut_leaves_behind() -> None:
    """A selected test, or a conftest it loads, must read only files ``mutants/`` holds (#1272)."""
    config = _mutmut_config()
    copied = _copied_paths(config)
    offenders = {
        path.relative_to(REPO_ROOT).as_posix(): sorted("/".join(p) for p in left)
        for path in _modules_pytest_loads(_selected_paths(config))
        if (
            left := {
                p
                for p in _repo_paths_read(path.read_text(encoding="utf-8"), path)
                if not _is_copied(p, copied)
            }
        )
    }

    assert not offenders, (
        "these selected tests read files that mutmut does not copy into mutants/, so they "
        "fail there and its stats run stops before any mutant is checked (#1272). Add the "
        "narrowest directory that holds the file to also_copy in pyproject.toml; a file "
        "entry under a subdirectory crashes mutmut 3.8, which does not create its parent "
        f"directory (#1275): {offenders}"
    )


def test_also_copy_has_no_file_entry_under_a_subdirectory() -> None:
    """mutmut 3.8 cannot copy a file whose parent directory it does not create (#1275)."""
    offenders = _file_entries_in_subdirectories(_mutmut_config(), REPO_ROOT)

    assert not offenders, (
        "these also_copy entries are files under a subdirectory, which makes mutmut 3.8 "
        "raise FileNotFoundError before any test runs (#1275). List the directory "
        f"instead: {offenders}"
    )


def test_the_also_copy_guard_rejects_a_file_under_a_subdirectory(tmp_path: Path) -> None:
    (tmp_path / "docs" / "usage").mkdir(parents=True)
    (tmp_path / "docs" / "usage" / "page.md").write_text("x", encoding="utf-8")
    config = {"also_copy": ["docs/usage/page.md"]}

    assert _file_entries_in_subdirectories(config, tmp_path) == {
        "docs/usage/page.md": "docs/usage/"
    }


def test_the_also_copy_guard_accepts_a_directory_and_a_top_level_file(tmp_path: Path) -> None:
    (tmp_path / "docs" / "usage").mkdir(parents=True)
    (tmp_path / "data.json").write_text("{}", encoding="utf-8")
    config = {"also_copy": ["docs/usage/", "docs/usage", "data.json"]}

    assert _file_entries_in_subdirectories(config, tmp_path) == {}


def test_every_test_of_the_package_is_selected() -> None:
    """A test that imports the package but is not selected never runs against a mutant.

    A test that also imports something ``mutants/`` lacks cannot be selected, so
    it is not required here; the previous test would reject it.
    """
    config = _mutmut_config()
    packages = _package_names(config)
    copied = _copied_paths(config)
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
    copied = _copied_paths(_mutmut_config())

    assert _left_behind({"tools", "tests", "os"}, copied) == {"tools"}


def test_a_narrow_also_copy_does_not_copy_its_whole_root() -> None:
    """``tools/x/generated/`` copies that directory, not ``tools`` (#1272)."""
    config = {"source_paths": ["src/"], "also_copy": ["tools/x/generated/"]}
    copied = _copied_paths(config)

    assert _left_behind({"tools"}, copied) == {"tools"}
    assert _is_copied(("tools", "x", "generated", "spec.yaml"), copied)
    assert not _is_copied(("tools", "other"), copied)


def test_a_broad_also_copy_copies_its_root() -> None:
    copied = _copied_paths({"source_paths": ["src/"], "also_copy": ["tools/"]})

    assert _left_behind({"tools"}, copied) == set()


def _pretend_tracked(monkeypatch: pytest.MonkeyPatch, *paths: tuple[str, ...]) -> None:
    """Make ``_tracked_paths`` report *paths*, so a test does not depend on the checkout (#1302)."""
    monkeypatch.setattr(f"{__name__}._tracked_paths", lambda: frozenset(paths))


def test_the_path_scanner_resolves_anchors_to_repository_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _pretend_tracked(monkeypatch, ("docs", "usage", "basics.md"))
    module = TESTS / "unit" / "deep" / "test_x.py"
    source = 'Path(__file__).resolve().parents[3] / "docs" / "usage" / "basics.md"\n'

    assert _repo_paths_read(source, module) == {("docs", "usage", "basics.md")}


def test_the_path_scanner_does_not_flag_reads_under_tests() -> None:
    module = TESTS / "test_x.py"

    assert _repo_paths_read('Path(__file__).parent / "template"\n', module) == {
        ("tests", "template")
    }
    reported = _repo_paths_read('Path(__file__).parent.parent / "tools" / "doit"\n', module)
    assert reported == {("tools", "doit")}
    assert _is_copied(("tests", "template"), {("tests",)})
    assert not _is_copied(("tools", "doit"), {("tests",)})


def test_the_path_scanner_follows_names_in_any_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    _pretend_tracked(
        monkeypatch,
        ("docs", "index.md"),
        ("completions", "doit.bash"),
        ("examples", "a.py"),
    )
    module = TESTS / "test_x.py"
    source = (
        "REPO_ROOT = Path(__file__).parent.parent\n"
        'DOCS = REPO_ROOT / "docs"\n'
        "def test_a():\n"
        '    (DOCS / "index.md").read_text()\n'
        "def test_b():\n"
        "    root = Path(__file__).parent.parent\n"
        '    (root / "completions" / "doit.bash").read_text()\n'
        '    REPO_ROOT.joinpath("examples")\n'
    )

    assert _repo_paths_read(source, module) == {
        ("docs", "index.md"),
        ("completions", "doit.bash"),
        ("examples",),
    }


def test_the_path_scanner_drops_paths_outside_the_repository_and_the_root() -> None:
    module = TESTS / "test_x.py"

    assert _repo_paths_read('Path(__file__).parents[50] / "x"\n', module) == set()
    assert _repo_paths_read('Path(__file__).parents[10] / "x"\n', module) == set()
    assert _repo_paths_read("Path(__file__).parent.parent\n", module) == set()


def test_the_path_scanner_ignores_what_it_cannot_resolve() -> None:
    module = TESTS / "test_x.py"
    source = 'tmp_path / "docs"\nPath(__file__).read_text()\n'

    assert _repo_paths_read(source, module) == set()


def test_the_path_scanner_reports_an_anchored_path_only_when_git_tracks_it() -> None:
    module = TESTS / "test_x.py"
    untracked = 'Path(__file__).parent.parent / "data" / "isolation-check"\n'
    tracked = 'Path(__file__).parent.parent / "docs" / "index.md"\n'

    assert _repo_paths_read(untracked, module) == set()
    assert _repo_paths_read(tracked, module) == {("docs", "index.md")}


def test_the_path_scanner_counts_a_relative_constant_only_when_git_tracks_it() -> None:
    module = TESTS / "test_x.py"
    source = 'Path("docs/index.md")\nPath("tmp/x")\nopen("out.txt")\n'

    assert _repo_paths_read(source, module) == {("docs", "index.md")}

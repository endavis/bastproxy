"""Tests-only helper that loads a hook script once per test module (#1323).

The hook scripts have hyphens in their filenames, so tests load them with ``importlib``.
Re-executing the 4500-line ``block-dangerous-commands.py`` once per test is several times
slower under coverage on Python 3.14 (the ``sysmon`` core): 84s for one test file against
11s without coverage. A module-scoped fixture loads it once and a function-scoped fixture
hands the shared instance to each test after resetting what the previous test could have
changed.

Isolation rule: every module global the hook rebinds at runtime is found from its source
(each name in a ``global`` statement, through ``ast``) and restored before each test with
``monkeypatch``. A global added later is therefore reset without anyone listing it.

Limit: a function that mutates a module-level container in place (``.add``, ``.append``,
``.update`` and so on) is NOT reset. Hooks must not do that; none does today.

Follows the ``tests/doc_scan.py`` precedent: a helper module, not a test module. pytest does
not collect it (the filename does not match ``test_*.py``). It depends only on the standard
library and pytest, so it ships with the hook tests.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import types

    import pytest

DANGEROUS_HOOK_PATH = (
    Path(__file__).resolve().parents[1] / "tools" / "hooks" / "ai" / "block-dangerous-commands.py"
)

_ABSENT = object()


def load_hook(path: Path, name: str) -> types.ModuleType:
    """Load the script at *path* as a fresh module instance named *name*."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError(f"could not load hook from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rebound_globals(path: Path) -> frozenset[str]:
    """Return every name declared in a ``global`` statement in the source at *path*."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return frozenset(
        name for node in ast.walk(tree) if isinstance(node, ast.Global) for name in node.names
    )


def snapshot_rebound(module: types.ModuleType, names: frozenset[str]) -> dict[str, object]:
    """Record each of *names* as the freshly loaded *module* holds it."""
    return {name: getattr(module, name, _ABSENT) for name in names}


def reset_rebound(
    module: types.ModuleType,
    snapshot: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Restore *snapshot* on *module*; *monkeypatch* undoes it at teardown."""
    for name, value in snapshot.items():
        if value is _ABSENT:
            monkeypatch.delattr(module, name, raising=False)
        else:
            monkeypatch.setattr(module, name, value, raising=False)

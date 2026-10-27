"""Tests for tools/doit/docs.py ``task_spell_check`` wiring around ``bootstrap.py``.

Verifies that the spell-check task (codespell) includes ``bootstrap.py`` when
it exists at the cwd (template repo) and excludes it when it has been removed
(spawned consumer project). Addresses issue #469.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.doit.docs import task_spell_check


def _touch(tmp_path: Path, rel: str) -> Path:
    """Create ``rel`` under ``tmp_path`` and return the absolute path."""
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("", encoding="utf-8")
    return target


class TestTaskSpellCheck:
    """``task_spell_check`` includes bootstrap.py iff it exists at cwd."""

    def test_includes_bootstrap_py_when_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        _touch(tmp_path, "bootstrap.py")

        task = task_spell_check()
        action = task["actions"][0]
        assert isinstance(action, str)
        assert " bootstrap.py" in action
        # README.md remains in the invocation regardless of bootstrap.py.
        assert "README.md" in action

    def test_excludes_bootstrap_py_when_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        task = task_spell_check()
        action = task["actions"][0]
        assert isinstance(action, str)
        assert "bootstrap.py" not in action
        # README.md is still present.
        assert "README.md" in action
        # No stray double-space where bootstrap.py used to sit.
        assert "  " not in action

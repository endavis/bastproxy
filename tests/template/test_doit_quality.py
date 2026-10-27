"""Tests for tools/doit/quality.py task wiring around ``bootstrap.py``.

These tests verify that the code-quality tasks include ``bootstrap.py`` when
it exists at the cwd (template repo) and exclude it when it has been removed
(spawned consumer project). Addresses issue #469.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.doit.quality import (
    task_check,
    task_format,
    task_format_check,
    task_lint,
    task_type_check,
)


def _touch(tmp_path: Path, rel: str) -> Path:
    """Create ``rel`` under ``tmp_path`` and return the absolute path."""
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("", encoding="utf-8")
    return target


class TestTaskLint:
    """``task_lint`` includes bootstrap.py iff it exists at cwd."""

    def test_includes_bootstrap_py_when_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        _touch(tmp_path, "bootstrap.py")

        task = task_lint()
        action = task["actions"][0]
        assert isinstance(action, str)
        assert " bootstrap.py" in action

    def test_excludes_bootstrap_py_when_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        task = task_lint()
        action = task["actions"][0]
        assert isinstance(action, str)
        assert "bootstrap.py" not in action
        # Sanity check: the ruff invocation is still present.
        assert "ruff check" in action

    def test_includes_examples_when_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "examples").mkdir()

        task = task_lint()
        action = task["actions"][0]
        assert isinstance(action, str)
        assert " examples/" in action

    def test_excludes_examples_when_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        task = task_lint()
        action = task["actions"][0]
        assert isinstance(action, str)
        assert "examples" not in action


class TestTaskFormat:
    """``task_format`` has two actions (format + check --fix); both must behave the same."""

    def test_both_actions_include_bootstrap_py_when_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        _touch(tmp_path, "bootstrap.py")

        task = task_format()
        for action in task["actions"]:
            assert isinstance(action, str)
            assert " bootstrap.py" in action

    def test_both_actions_exclude_bootstrap_py_when_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        task = task_format()
        for action in task["actions"]:
            assert isinstance(action, str)
            assert "bootstrap.py" not in action

    def test_both_actions_include_examples_when_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "examples").mkdir()

        task = task_format()
        for action in task["actions"]:
            assert isinstance(action, str)
            assert " examples/" in action

    def test_both_actions_exclude_examples_when_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        task = task_format()
        for action in task["actions"]:
            assert isinstance(action, str)
            assert "examples" not in action


class TestTaskFormatCheck:
    """``task_format_check`` runs ``ruff format --check``."""

    def test_includes_bootstrap_py_when_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        _touch(tmp_path, "bootstrap.py")

        task = task_format_check()
        action = task["actions"][0]
        assert isinstance(action, str)
        assert " bootstrap.py" in action

    def test_excludes_bootstrap_py_when_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        task = task_format_check()
        action = task["actions"][0]
        assert isinstance(action, str)
        assert "bootstrap.py" not in action
        assert "ruff format --check" in action

    def test_includes_examples_when_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "examples").mkdir()

        task = task_format_check()
        action = task["actions"][0]
        assert isinstance(action, str)
        assert " examples/" in action

    def test_excludes_examples_when_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        task = task_format_check()
        action = task["actions"][0]
        assert isinstance(action, str)
        assert "examples" not in action


class TestTaskCheck:
    """``task_check`` aggregates the pre-PR check tasks via ``task_dep``."""

    def test_task_dep_includes_audit(self) -> None:
        """``audit`` must run as part of ``doit check`` so dep CVEs fail locally."""
        task = task_check()
        assert "audit" in task["task_dep"]

    def test_task_dep_covers_full_check_set(self) -> None:
        """``task_check`` must depend on every pre-PR quality/security task.

        ``deadcode`` joined the set in #700: it was defined as a task but never
        gated, so unused imports in ``tools/`` accumulated unnoticed. ``wheel_check``
        joined in #837 so a packaging regression fails locally, not on PyPI.
        ``docs_build`` joined in #974 so a strict-mode docs build failure (e.g. a
        page missing from mkdocs ``nav``) fails locally, not only in CI.
        """
        task = task_check()
        assert set(task["task_dep"]) == {
            "format_check",
            "lint",
            "type_check",
            "deadcode",
            "security",
            "audit",
            "spell_check",
            "wheel_check",
            "docs_build",
            "test",
        }

    def test_check_gates_on_docs_build(self) -> None:
        """``docs_build`` must run as part of ``doit check``, not just on demand.

        Before #974, ``doit check`` could pass locally while the strict mkdocs
        build failed in CI (e.g. a new ADR missing from the ``nav`` config).
        """
        assert "docs_build" in task_check()["task_dep"]


class TestTaskTypeCheck:
    """``task_type_check`` runs ``mypy``."""

    def test_includes_bootstrap_py_when_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        _touch(tmp_path, "bootstrap.py")

        task = task_type_check()
        action = task["actions"][0]
        assert isinstance(action, str)
        assert " bootstrap.py" in action

    def test_excludes_bootstrap_py_when_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        task = task_type_check()
        action = task["actions"][0]
        assert isinstance(action, str)
        assert "bootstrap.py" not in action
        assert "mypy" in action


class TestQualityGateScope:
    """The quality gate must cover the directories it claims to.

    Before #700, ``type_check`` targeted only ``src/ tools/doit/`` and vulture's
    configured paths omitted ``tools/`` entirely — so real errors in
    ``tools/hooks/`` and ``tests/`` passed a green ``doit check``. Two escaped
    that way in PR #699. These tests pin the scope so it cannot silently narrow
    again.
    """

    def test_type_check_covers_tools_and_tests(self) -> None:
        """``type_check`` must check all of ``src/``, ``tools/`` and ``tests/``."""
        action = task_type_check()["actions"][0]
        assert isinstance(action, str)
        for root in ("src/", "tools/", "tests/"):
            assert root in action, f"type_check no longer covers {root}"

    def test_type_check_does_not_narrow_to_tools_subdir(self) -> None:
        """Guard the specific regression: narrowing ``tools/`` to one subdirectory."""
        action = task_type_check()["actions"][0]
        assert isinstance(action, str)
        assert "tools/doit/" not in action, (
            "type_check narrowed back to tools/doit/; this hides tools/hooks/"
        )

    def test_check_gates_on_deadcode(self) -> None:
        """``deadcode`` must run as part of ``doit check``, not just on demand."""
        assert "deadcode" in task_check()["task_dep"]

    def test_vulture_paths_include_tools(self) -> None:
        """Vulture's configured paths must include ``tools/``."""
        import tomllib

        pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
        with pyproject.open("rb") as handle:
            config = tomllib.load(handle)
        paths = config["tool"]["vulture"]["paths"]
        assert "tools" in paths, f"vulture paths missing 'tools': {paths}"

    def test_mypy_does_not_exclude_pyproject_template(self) -> None:
        """The tooling package must not be excluded from type checking wholesale.

        Its bare ``sys.path`` imports are suppressed by module-name overrides
        instead, so the other ~5,300 lines stay checked.
        """
        import tomllib

        pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
        with pyproject.open("rb") as handle:
            config = tomllib.load(handle)
        excludes = config["tool"]["mypy"].get("exclude", [])
        assert not any("pyproject_template" in entry for entry in excludes), (
            f"tools/pyproject_template/ is excluded from mypy again: {excludes}"
        )

"""Tests for tools/doit/security.py task wiring.

Covers two concerns:

1. ``task_security`` includes ``bootstrap.py`` iff it exists at cwd (template
   repo) and excludes it when removed (spawned consumer project). Addresses
   issue #469.
2. All four security tasks gate their underlying tool on ``uv pip show
   <package>`` (via ``install_check_or_skip``) so real failures (bandit
   findings, pip-audit CVEs, etc.) propagate instead of being swallowed by
   the legacy ``|| echo 'not installed'`` pattern. Addresses issue #527.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.doit.security import task_audit, task_licenses, task_sbom, task_security


def _touch(tmp_path: Path, rel: str) -> Path:
    """Create ``rel`` under ``tmp_path`` and return the absolute path."""
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("", encoding="utf-8")
    return target


class TestTaskSecurity:
    """``task_security`` includes bootstrap.py iff it exists at cwd."""

    def test_includes_bootstrap_py_when_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        _touch(tmp_path, "bootstrap.py")

        task = task_security()
        action = task["actions"][0]
        assert isinstance(action, str)
        assert " bootstrap.py" in action
        # The shell-level fallback messaging is still in place.
        assert "bandit not installed" in action

    def test_excludes_bootstrap_py_when_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        task = task_security()
        action = task["actions"][0]
        assert isinstance(action, str)
        assert "bootstrap.py" not in action
        # The bandit invocation is still present.
        assert "bandit" in action
        assert "src/" in action
        assert "tools/" in action


class TestSecurityTaskGates:
    """Each security task gates its tool via ``uv pip show <package>``.

    The gate replaces the swallow-prone ``cmd || echo 'not installed'``
    pattern. We assert: (a) the gate is present, (b) the install hint is
    preserved, (c) the original tool invocation is still part of the action,
    and (d) the broken-swallow pattern is gone.
    """

    def test_audit_gates_on_pip_audit_package(self) -> None:
        action = task_audit()["actions"][0]
        assert isinstance(action, str)
        assert "uv pip show pip-audit" in action
        assert "pip-audit not installed. Run: doit install_dev" in action
        assert "uv run pip-audit --skip-editable" in action
        # Bug-fix invariant: the bare-swallow pattern must be gone.
        assert "|| echo 'pip-audit not installed" not in action

    def test_security_gates_on_bandit_package(self) -> None:
        action = task_security()["actions"][0]
        assert isinstance(action, str)
        assert "uv pip show bandit" in action
        assert "bandit not installed. Run: doit install_dev" in action
        assert "uv run bandit -c pyproject.toml -r src/ tools/" in action
        assert "|| echo 'bandit not installed" not in action

    def test_licenses_gates_on_pip_licenses_package(self) -> None:
        action = task_licenses()["actions"][0]
        assert isinstance(action, str)
        assert "uv pip show pip-licenses" in action
        assert "pip-licenses not installed. Run: doit install_dev" in action
        assert "uv run pip-licenses --format=markdown --order=license" in action
        assert "|| echo 'pip-licenses not installed" not in action

    def test_sbom_gates_on_cyclonedx_bom_package(self) -> None:
        # task_sbom has TWO actions: ``mkdir -p tmp`` (untouched) and the
        # cyclonedx invocation (gated). Inspect the second.
        actions = task_sbom()["actions"]
        assert len(actions) == 2
        assert actions[0] == "mkdir -p tmp"
        action = actions[1]
        assert isinstance(action, str)
        # CLI is ``cyclonedx-py`` but the package name is ``cyclonedx-bom``.
        assert "uv pip show cyclonedx-bom" in action
        assert "cyclonedx-py not installed. Run: doit install_dev" in action
        assert "uv run cyclonedx-py environment --of JSON -o tmp/sbom.json" in action
        assert "uv run cyclonedx-py environment --of XML -o tmp/sbom.xml" in action
        assert "|| echo 'cyclonedx-py not installed" not in action

"""Tests for tools/doit/security.py task wiring.

Covers three concerns:

1. ``task_security`` includes ``bootstrap.py`` iff it exists at cwd (template
   repo) and excludes it when removed (spawned consumer project). Addresses
   issue #469.
2. All four security tasks gate their underlying tool on an import probe in the
   project venv (via ``install_check_or_skip``) so real failures (bandit
   findings, pip-audit CVEs, etc.) propagate instead of being swallowed by
   the legacy ``|| echo 'not installed'`` pattern. Addresses issue #527.
3. No action needs a POSIX shell, so the tasks run under cmd.exe: no
   ``/dev/null``, ``||``, brace group, ``mkdir -p`` or single quote. Addresses
   issue #1291.
"""

from __future__ import annotations

import shlex
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tools.doit.base import _GuardedCmdAction
from tools.doit.security import (
    _make_tmp_dir,
    task_audit,
    task_licenses,
    task_sbom,
    task_security,
)

_POSIX_ONLY = ("/dev/null", "||", "{ ", "mkdir -p", "'")


def _touch(tmp_path: Path, rel: str) -> Path:
    """Create ``rel`` under ``tmp_path`` and return the absolute path."""
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("", encoding="utf-8")
    return target


def _guard(action: object) -> tuple[str, str, str]:
    """Return the guarded action's (module, hint, command), failing if it is not one."""
    assert isinstance(action, _GuardedCmdAction)
    return action._module, action._hint, action._action


class TestTaskSecurity:
    """``task_security`` includes bootstrap.py iff it exists at cwd."""

    def test_includes_bootstrap_py_when_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        _touch(tmp_path, "bootstrap.py")

        _, hint, command = _guard(task_security()["actions"][0])
        assert " bootstrap.py" in command
        assert "bandit not installed" in hint

    def test_excludes_bootstrap_py_when_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        _, _, command = _guard(task_security()["actions"][0])
        assert "bootstrap.py" not in command
        assert "bandit" in command
        assert "src/" in command
        assert "tools/" in command


class TestSecurityTaskGates:
    """Each security task gates its tool by importing its module in the project venv."""

    def test_audit_gates_on_pip_audit_package(self) -> None:
        module, hint, command = _guard(task_audit()["actions"][0])
        assert module == "pip_audit"
        assert hint == "pip-audit not installed. Run: doit install_dev"
        assert command == "uv run pip-audit --skip-editable"

    def test_security_gates_on_bandit_package(self) -> None:
        module, hint, command = _guard(task_security()["actions"][0])
        assert module == "bandit"
        assert hint == "bandit not installed. Run: doit install_dev"
        assert command.startswith("uv run bandit -c pyproject.toml -r src/ tools/")

    def test_security_output_is_terse(self) -> None:
        """#1075: quiet, one line per finding."""
        _, _, command = _guard(task_security()["actions"][0])
        tokens = shlex.split(command.split("uv run bandit", 1)[1])
        assert "-q" in tokens
        assert tokens[tokens.index("-f") + 1] == "custom"
        assert "--msg-template" in tokens

    def test_security_msg_template_is_double_quoted(self) -> None:
        """cmd.exe does not treat single quotes as quotes (#1291)."""
        _, _, command = _guard(task_security()["actions"][0])
        assert '--msg-template "{relpath}:{line}:{col}: {test_id}' in command

    def test_licenses_gates_on_pip_licenses_package(self) -> None:
        module, hint, command = _guard(task_licenses()["actions"][0])
        assert module == "piplicenses"
        assert hint == "pip-licenses not installed. Run: doit install_dev"
        assert command == "uv run pip-licenses --format=markdown --order=license"

    def test_sbom_gates_on_cyclonedx_bom_package(self) -> None:
        # CLI is ``cyclonedx-py`` but the package name is ``cyclonedx-bom``.
        actions = task_sbom()["actions"]
        assert len(actions) == 2
        assert actions[0] is _make_tmp_dir
        module, hint, command = _guard(actions[1])
        assert module == "cyclonedx"
        assert hint == "cyclonedx-py not installed. Run: doit install_dev"
        assert "uv run cyclonedx-py environment --of JSON -o tmp/sbom.json" in command
        assert "uv run cyclonedx-py environment --of XML -o tmp/sbom.xml" in command

    def test_make_tmp_dir_is_idempotent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        _make_tmp_dir()
        _make_tmp_dir()
        assert (tmp_path / "tmp").is_dir()


class TestNoPosixShellSyntax:
    """No security action needs a POSIX shell, so each runs under cmd.exe (#1291)."""

    @pytest.mark.parametrize("task", [task_audit, task_security, task_licenses, task_sbom])
    def test_commands_have_no_posix_only_syntax(self, task: Callable[[], dict[str, Any]]) -> None:
        for action in task()["actions"]:
            if callable(action):
                continue
            _, hint, command = _guard(action)
            for token in _POSIX_ONLY:
                assert token not in command, f"{token!r} in {command!r}"
            assert "/dev/null" not in hint

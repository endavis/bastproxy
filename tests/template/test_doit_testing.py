"""Tests for tools/doit/testing.py task wiring."""

from __future__ import annotations

from tools.doit.testing import task_test


class TestTaskTest:
    """``task_test`` depends on ``env_check`` first (#1033).

    ``env_check`` warns, without failing, when the environment has drifted
    from ``uv.lock`` — the replacement for the ``post-merge``/``post-checkout``
    pre-commit hooks that used to auto-sync on checkout.
    """

    def test_depends_on_env_check(self) -> None:
        assert "env_check" in task_test()["task_dep"]

    def test_still_runs_pytest(self) -> None:
        assert "uv run pytest -n auto -v" in task_test()["actions"]

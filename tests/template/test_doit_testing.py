"""Tests for tools/doit/testing.py task wiring."""

from __future__ import annotations

import shlex

from tools.doit.testing import task_test


class TestTaskTest:
    """``task_test`` depends on ``env_check`` first (#1033).

    ``env_check`` warns, without failing, when the environment has drifted
    from ``uv.lock`` — the replacement for the ``post-merge``/``post-checkout``
    pre-commit hooks that used to auto-sync on checkout.
    """

    def test_depends_on_env_check(self) -> None:
        assert "env_check" in task_test()["task_dep"]

    @staticmethod
    def _tokens() -> list[str]:
        action = task_test()["actions"][0]
        assert isinstance(action, str)
        return shlex.split(action)

    def test_still_runs_pytest_in_parallel(self) -> None:
        tokens = self._tokens()
        assert tokens[:3] == ["uv", "run", "pytest"]
        assert "-n" in tokens
        assert tokens[tokens.index("-n") + 1] == "auto"

    def test_failure_output_is_terse(self) -> None:
        """#1075: quiet, failure summary and short tracebacks."""
        tokens = self._tokens()
        assert "-q" in tokens
        assert "-rfE" in tokens
        assert "--tb=short" in tokens

    def test_has_no_verbose_flag(self) -> None:
        """#1075: ``-v`` prints one PASSED line per test into the failure dump."""
        tokens = self._tokens()
        assert not {"-v", "-vv", "--verbose"} & set(tokens)

    def test_verbosity_is_zero(self) -> None:
        assert task_test()["verbosity"] == 0

"""Tests for helpers in tools.doit.base and tools.doit.release.

``run_streamed`` / ``run_teed`` back the live-streaming output changes for
the release tasks (issue #631). ``_extract_version_from_release_pr`` is the
version-parsing helper factored out of ``task_release_tag`` to support
PEP440 and semver-style pre-release suffixes (issue #632 Phase A).
``_build_cz_get_next_cmd`` is the command-list builder factored out of
``task_release`` so ``--prerelease`` can be threaded through to
``cz bump --get-next`` (issue #632 Phase B). The task functions themselves
(``task_release``, etc.) have no existing test coverage and are out of scope
per the plan.
"""

from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
from datetime import date
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from tools.doit.base import run_streamed, run_teed
from tools.doit.release import (
    ChangelogFormatError,
    _build_cz_get_next_cmd,
    _bump_handwritten_changelog,
    _changelog_is_handwritten_enabled,
    _extract_next_version_from_cz_output,
    _extract_version_from_release_pr,
    _get_pypi_name_from_pyproject,
    _major_version,
    _major_version_zero_enabled,
    _repo_has_version_tags,
    _version_files_from_pyproject,
    _version_provider_is_scm,
    task_release,
    task_release_tag,
    validate_issue_links,
    validate_merge_commits,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from _pytest.monkeypatch import MonkeyPatch


class TestVersionProviderIsScm:
    """Reads ``[tool.commitizen].version_provider`` from the cwd's ``pyproject.toml`` (#971)."""

    @pytest.mark.parametrize(
        ("pyproject", "expected"),
        [
            ('[tool.commitizen]\nversion_provider = "scm"\n', True),
            ('[tool.commitizen]\nversion_provider = "pep621"\n', False),
            ('[tool.commitizen]\nname = "cz_conventional_commits"\n', True),
            ('[project]\nname = "my-pkg"\n', True),
        ],
    )
    def test_reads_the_setting(
        self, tmp_path: Path, monkeypatch: MonkeyPatch, pyproject: str, expected: bool
    ) -> None:
        (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        assert _version_provider_is_scm() is expected

    def test_a_missing_pyproject_counts_as_scm(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        assert _version_provider_is_scm() is True


class TestChangelogIsHandwrittenEnabled:
    """Reads ``[tool.commitizen].update_changelog_on_bump`` from ``pyproject.toml`` (#971)."""

    @pytest.mark.parametrize(
        ("pyproject", "expected"),
        [
            ("[tool.commitizen]\nupdate_changelog_on_bump = false\n", True),
            ("[tool.commitizen]\nupdate_changelog_on_bump = true\n", False),
            # A missing key is commitizen's default, False, so it counts as hand-written.
            ('[tool.commitizen]\nname = "cz_conventional_commits"\n', True),
            ('[project]\nname = "my-pkg"\n', True),
        ],
    )
    def test_reads_the_setting(
        self, tmp_path: Path, monkeypatch: MonkeyPatch, pyproject: str, expected: bool
    ) -> None:
        (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        assert _changelog_is_handwritten_enabled() is expected

    def test_a_missing_pyproject_counts_as_generated(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        assert _changelog_is_handwritten_enabled() is False


class TestVersionFilesFromPyproject:
    """Reads ``[tool.commitizen].version_files`` from ``pyproject.toml``, paths only (#971)."""

    def test_strips_the_pattern_suffix(self, tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
        pyproject = (
            "[tool.commitizen]\n"
            'version_files = ["src/mypkg/__init__.py:__version__", "Makefile:VERSION"]\n'
        )
        (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        assert _version_files_from_pyproject() == ["src/mypkg/__init__.py", "Makefile"]

    def test_missing_key_returns_empty_list(self, tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[tool.commitizen]\nname = "cz_conventional_commits"\n', encoding="utf-8"
        )
        monkeypatch.chdir(tmp_path)
        assert _version_files_from_pyproject() == []

    def test_missing_pyproject_returns_empty_list(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        assert _version_files_from_pyproject() == []

    def test_non_list_value_returns_empty_list(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[tool.commitizen]\nversion_files = "not-a-list"\n', encoding="utf-8"
        )
        monkeypatch.chdir(tmp_path)
        assert _version_files_from_pyproject() == []


class TestBumpHandwrittenChangelog:
    """Unit tests for ``_bump_handwritten_changelog`` (#971)."""

    _CHANGELOG_WITH_ENTRIES = (
        "# Changelog\n\n"
        "## [Unreleased]\n\n"
        "### Added\n"
        "- A hand-written entry\n\n"
        "## [0.1.0] - 2026-01-01\n\n"
        "### Added\n"
        "- First release\n"
    )

    def test_renames_unreleased_and_inserts_new_empty_section(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        (tmp_path / "CHANGELOG.md").write_text(self._CHANGELOG_WITH_ENTRIES, encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        _bump_handwritten_changelog("0.2.0")

        result = (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8")
        today = date.today().isoformat()
        assert f"## [Unreleased]\n\n## [0.2.0] - {today}" in result
        assert "- A hand-written entry" in result
        assert "## [0.1.0] - 2026-01-01" in result
        assert "- First release" in result

    def test_raises_when_unreleased_heading_missing(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\nNothing here.\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        with pytest.raises(ChangelogFormatError, match=r"no '## \[Unreleased\]' heading"):
            _bump_handwritten_changelog("0.2.0")

    def test_raises_when_unreleased_section_is_empty(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        changelog = "# Changelog\n\n## [Unreleased]\n\n## [0.1.0] - 2026-01-01\n\n- x\n"
        (tmp_path / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        with pytest.raises(ChangelogFormatError, match="section is empty"):
            _bump_handwritten_changelog("0.2.0")


class TestRunStreamed:
    """Tests for ``run_streamed``."""

    def test_success_returns_none(self) -> None:
        """A zero-exit command returns ``None`` and does not raise."""
        # run_streamed is annotated `-> None`, so mypy calls the binding below
        # pointless. The assertion is kept deliberately: it documents the
        # contract at runtime and would catch the signature being widened to
        # return something. Suppressing beats deleting a real check.
        result = run_streamed([sys.executable, "-c", "print('hi')"])  # type: ignore[func-returns-value]
        assert result is None

    def test_failure_with_check_true_raises(self) -> None:
        """Non-zero exit with ``check=True`` raises ``CalledProcessError``."""
        with pytest.raises(subprocess.CalledProcessError) as excinfo:
            run_streamed([sys.executable, "-c", "import sys; sys.exit(2)"])
        assert excinfo.value.returncode == 2

    def test_failure_with_check_false_does_not_raise(self) -> None:
        """Non-zero exit with ``check=False`` returns without raising."""
        # Must not raise.
        # See the note in test_success_returns_none for why this is suppressed
        # rather than the assertion removed.
        result = run_streamed(  # type: ignore[func-returns-value]
            [sys.executable, "-c", "import sys; sys.exit(3)"],
            check=False,
        )
        assert result is None

    def test_env_is_threaded_through(self, capfd: pytest.CaptureFixture[str]) -> None:
        """The ``env`` mapping is forwarded to the child process."""
        # Use a sentinel env var the child will echo to stdout.
        run_streamed(
            [
                sys.executable,
                "-c",
                "import os; print(os.environ.get('RUN_STREAMED_TEST', ''))",
            ],
            env={"RUN_STREAMED_TEST": "threaded-value"},
        )
        out = capfd.readouterr().out
        assert "threaded-value" in out

    def test_empty_env_isolates_child(self, capfd: pytest.CaptureFixture[str]) -> None:
        """Passing a tightly-scoped env actually replaces (not extends) the parent env."""
        # A var the parent likely has — confirm the child doesn't see it when
        # we pass a minimal env. We still need PATH for the interpreter lookup
        # on some platforms; use the interpreter's absolute path to avoid that.
        run_streamed(
            [
                sys.executable,
                "-c",
                "import os; print(os.environ.get('PATH', 'NO_PATH'))",
            ],
            env={"OTHER": "x"},
        )
        out = capfd.readouterr().out
        assert "NO_PATH" in out

    def test_pythonunbuffered_is_set_by_default(self, capfd: pytest.CaptureFixture[str]) -> None:
        """``PYTHONUNBUFFERED=1`` is injected into the child env so Python
        descendants flush stdout line-by-line to pipes, not on process exit."""
        run_streamed(
            [
                sys.executable,
                "-c",
                "import os; print(os.environ.get('PYTHONUNBUFFERED', 'unset'))",
            ]
        )
        assert capfd.readouterr().out.strip() == "1"


class TestRunTeed:
    """Tests for ``run_teed``."""

    def test_streams_and_captures_stdout(self, monkeypatch: MonkeyPatch) -> None:
        """Each line of stdout is both written live and captured in the buffer.

        The child deliberately does NOT call ``sys.stdout.flush()`` — real
        tools (cz, pytest, mypy) don't, and an earlier version of this test
        did which masked a PYTHONUNBUFFERED bug. We rely on the helper's
        ``PYTHONUNBUFFERED=1`` env override for the child to line-buffer.
        """
        fake_stdout = io.StringIO()
        monkeypatch.setattr(sys, "stdout", fake_stdout)

        result = run_teed(
            [
                sys.executable,
                "-c",
                "for i in (1, 2, 3):\n    print(i)\n",
            ]
        )

        streamed = fake_stdout.getvalue()
        # All three lines must appear in the live-streamed output.
        assert "1\n" in streamed
        assert "2\n" in streamed
        assert "3\n" in streamed
        # And also in the returned captured stdout.
        assert result.stdout == "1\n2\n3\n"
        assert result.stderr == ""
        assert result.returncode == 0

    def test_stderr_merges_into_stdout(self, monkeypatch: MonkeyPatch) -> None:
        """Content written to stderr is captured in ``.stdout`` (merged stream)."""
        fake_stdout = io.StringIO()
        monkeypatch.setattr(sys, "stdout", fake_stdout)

        result = run_teed(
            [
                sys.executable,
                "-c",
                "import sys; sys.stderr.write('err-line\\n'); sys.stderr.flush()",
            ]
        )

        assert "err-line" in result.stdout
        assert "err-line" in fake_stdout.getvalue()
        assert result.stderr == ""
        assert result.returncode == 0

    def test_returncode_reflects_success(self, monkeypatch: MonkeyPatch) -> None:
        """A zero-exit command returns a ``CompletedProcess`` with ``returncode=0``."""
        monkeypatch.setattr(sys, "stdout", io.StringIO())
        result = run_teed([sys.executable, "-c", "print('ok')"])
        assert result.returncode == 0
        assert "ok" in result.stdout

    def test_failure_with_check_true_raises_with_stdout(self, monkeypatch: MonkeyPatch) -> None:
        """Non-zero exit under ``check=True`` raises with captured ``stdout``.

        This preserves the old error-path semantics — callers that logged
        ``e.stdout`` still see output even though live streaming already
        showed it to the user.
        """
        monkeypatch.setattr(sys, "stdout", io.StringIO())

        with pytest.raises(subprocess.CalledProcessError) as excinfo:
            run_teed(
                [
                    sys.executable,
                    "-c",
                    "import sys; print('partial output'); sys.exit(5)",
                ]
            )

        err = excinfo.value
        assert err.returncode == 5
        assert err.stdout is not None
        assert "partial output" in err.stdout

    def test_failure_with_check_false_returns_completedprocess(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        """Non-zero exit under ``check=False`` returns a ``CompletedProcess``."""
        monkeypatch.setattr(sys, "stdout", io.StringIO())

        result = run_teed(
            [
                sys.executable,
                "-c",
                "import sys; print('still captured'); sys.exit(7)",
            ],
            check=False,
        )

        assert result.returncode == 7
        assert "still captured" in result.stdout
        assert result.stderr == ""

    def test_env_is_threaded_through(self, monkeypatch: MonkeyPatch) -> None:
        """The ``env`` mapping is forwarded to the child process."""
        monkeypatch.setattr(sys, "stdout", io.StringIO())

        result = run_teed(
            [
                sys.executable,
                "-c",
                "import os; print(os.environ.get('RUN_TEED_TEST', ''))",
            ],
            env={"RUN_TEED_TEST": "teed-value"},
        )

        assert "teed-value" in result.stdout

    def test_cwd_is_threaded_through(self, monkeypatch: MonkeyPatch, tmp_path: object) -> None:
        """The ``cwd`` parameter is forwarded to the child process."""
        monkeypatch.setattr(sys, "stdout", io.StringIO())

        # tmp_path is a pathlib.Path fixture; reify to str for the child.
        from pathlib import Path

        assert isinstance(tmp_path, Path)
        result = run_teed(
            [sys.executable, "-c", "import os; print(os.getcwd())"],
            cwd=str(tmp_path),
        )

        # getcwd() in the child should resolve to tmp_path.
        captured = result.stdout.strip()
        assert Path(captured).resolve() == tmp_path.resolve()

    def test_pythonunbuffered_is_set_by_default(self, monkeypatch: MonkeyPatch) -> None:
        """``PYTHONUNBUFFERED=1`` is injected into the child env so Python
        descendants flush stdout line-by-line to pipes, not on process exit."""
        monkeypatch.setattr(sys, "stdout", io.StringIO())
        result = run_teed(
            [
                sys.executable,
                "-c",
                "import os; print(os.environ.get('PYTHONUNBUFFERED', 'unset'))",
            ]
        )
        assert result.stdout.strip() == "1"

    def test_pythonunbuffered_caller_override_respected(self, monkeypatch: MonkeyPatch) -> None:
        """A caller-supplied ``PYTHONUNBUFFERED`` wins; the helper only
        provides it as a default."""
        monkeypatch.setattr(sys, "stdout", io.StringIO())
        result = run_teed(
            [
                sys.executable,
                "-c",
                "import os; print(os.environ.get('PYTHONUNBUFFERED', 'unset'))",
            ],
            env={**os.environ, "PYTHONUNBUFFERED": "0"},
        )
        assert result.stdout.strip() == "0"

    def test_streams_line_by_line_without_child_flush(self, monkeypatch: MonkeyPatch) -> None:
        """Regression test for PR #633 review Issue 2: a Python child that
        does NOT call ``sys.stdout.flush()`` after each print (which is what
        real tools do) still delivers lines to the parent as they are
        printed — not batched at process exit — thanks to
        ``PYTHONUNBUFFERED=1``. Without that env override, all three writes
        would arrive together at ~0.45s when the child terminates.
        """
        import time

        received: list[tuple[float, str]] = []
        start = time.monotonic()

        class TimestampingStdout:
            def write(self, s: str) -> int:
                received.append((time.monotonic() - start, s))
                return len(s)

            def flush(self) -> None:
                pass

        monkeypatch.setattr(sys, "stdout", TimestampingStdout())

        # Child prints 3 lines with 150ms gaps. Total runtime ~0.45s. No flush.
        run_teed(
            [
                sys.executable,
                "-c",
                "import time\nfor i in (1, 2, 3):\n    print(i)\n    time.sleep(0.15)\n",
            ]
        )

        content_writes = [(t, s) for t, s in received if s.strip()]
        assert len(content_writes) >= 3, f"expected >=3 content writes, got {content_writes}"

        first_write_time = content_writes[0][0]
        # Generous threshold: first line should arrive by ~0.15s under live
        # streaming; child's full runtime is ~0.45s. 0.3s gives margin for
        # slow CI without masking a regression where everything arrives at
        # process exit.
        assert first_write_time < 0.3, (
            f"first content write at {first_write_time:.3f}s "
            f"(child runs ~0.45s). Output appears buffered — "
            f"regression of PR #633 review Issue 2 fix (PYTHONUNBUFFERED)."
        )

    def test_raising_write_triggers_child_cleanup(self, monkeypatch: MonkeyPatch) -> None:
        """Regression test for PR #633 review Issue 1: if the stdout-write
        loop raises, the helper still calls ``process.kill()`` and
        ``wait()`` so the child is reaped and the pipe is closed — no
        lingering child, no deadlock on a full pipe."""

        class FailingStdout:
            def write(self, s: str) -> int:
                raise OSError(f"broken stdout (refused {len(s)} chars)")

            def flush(self) -> None:
                pass

        monkeypatch.setattr(sys, "stdout", FailingStdout())

        # The child prints a line; our write will raise on the first line.
        # Primary assertion: the exception propagates out (rather than the
        # helper swallowing it and hanging on wait()).
        with pytest.raises(OSError, match="broken stdout"):
            run_teed([sys.executable, "-c", "print('hi')"])


class TestExtractVersionFromReleasePR:
    """Tests for ``_extract_version_from_release_pr``.

    Covers the PR-title / branch-name shapes produced by ``task_release``
    (and the shapes a maintainer might hand-write), including PEP440 and
    semver-style pre-release suffixes that the previous regex in
    ``task_release_tag`` rejected (issue #632).
    """

    @pytest.mark.parametrize(
        ("pr_title", "expected"),
        [
            # Production release (what was already supported before #632).
            ("release: v1.0.0", "1.0.0"),
            # PEP440 pre-release shapes (cz bump --prerelease output).
            ("release: v0.1.0a0", "0.1.0a0"),
            ("release: v0.2.0b1", "0.2.0b1"),
            ("release: v1.5.0rc0", "1.5.0rc0"),
            ("release: v0.1.0.dev2", "0.1.0.dev2"),
            # Semver-style pre-release shapes (hand-written / alternate tooling).
            ("release: v0.1.0-alpha.0", "0.1.0-alpha.0"),
            ("release: v0.1.0-beta.1", "0.1.0-beta.1"),
            ("release: v0.1.0-rc.0", "0.1.0-rc.0"),
        ],
    )
    def test_extracts_from_pr_title(self, pr_title: str, expected: str) -> None:
        """The PR title is the primary source; the captured group is the bare version."""
        # Branch name is deliberately unrelated so the title match is the only
        # thing that can succeed.
        assert _extract_version_from_release_pr(pr_title, "unrelated/branch") == expected

    def test_falls_back_to_branch_name(self) -> None:
        """When the PR title doesn't match, the branch name is consulted."""
        assert _extract_version_from_release_pr("unrelated: fix", "release/v0.1.0a0") == "0.1.0a0"

    def test_returns_none_when_neither_matches(self) -> None:
        """Neither input matches -> ``None`` (caller handles the error path)."""
        assert _extract_version_from_release_pr("fix: bug", "fix/123-thing") is None

    def test_returns_none_for_non_numeric_version(self) -> None:
        """``release: vX.Y.Z`` with literal letters must not match — the regex
        requires digits."""
        assert _extract_version_from_release_pr("release: vX.Y.Z", "release/vX.Y.Z") is None


class TestBuildCzGetNextCmd:
    """Tests for ``_build_cz_get_next_cmd``.

    The helper is a pure command-list builder: no validation, no I/O. These
    tests pin the flag ordering, the uppercasing of ``--increment``, and the
    verbatim pass-through of ``--prerelease`` (issue #632 Phase B).
    """

    @pytest.mark.parametrize(
        ("increment", "prerelease", "expected"),
        [
            # No flags: base command only.
            ("", "", ["uv", "run", "cz", "bump", "--get-next", "--yes"]),
            # Increment alone (lowercase input is uppercased).
            (
                "minor",
                "",
                ["uv", "run", "cz", "bump", "--get-next", "--yes", "--increment", "MINOR"],
            ),
            # Increment alone (already uppercase stays uppercase).
            (
                "PATCH",
                "",
                ["uv", "run", "cz", "bump", "--get-next", "--yes", "--increment", "PATCH"],
            ),
            # Prerelease alone: alpha.
            (
                "",
                "alpha",
                ["uv", "run", "cz", "bump", "--get-next", "--yes", "--prerelease", "alpha"],
            ),
            # Prerelease alone: beta.
            (
                "",
                "beta",
                ["uv", "run", "cz", "bump", "--get-next", "--yes", "--prerelease", "beta"],
            ),
            # Prerelease alone: rc.
            (
                "",
                "rc",
                ["uv", "run", "cz", "bump", "--get-next", "--yes", "--prerelease", "rc"],
            ),
            # Both set: helper emits both flags in increment-then-prerelease
            # order; the task accepts this combination (see #475).
            (
                "minor",
                "alpha",
                [
                    "uv",
                    "run",
                    "cz",
                    "bump",
                    "--get-next",
                    "--yes",
                    "--increment",
                    "MINOR",
                    "--prerelease",
                    "alpha",
                ],
            ),
        ],
    )
    def test_builds_expected_command(
        self, increment: str, prerelease: str, expected: list[str]
    ) -> None:
        """The emitted list matches the expected base + flags in order."""
        assert _build_cz_get_next_cmd(increment, prerelease) == expected


class TestValidateMergeCommits:
    """Tests for ``validate_merge_commits`` (issue #639).

    The helper shells out to ``git describe`` and ``git log --merges``; the
    tests monkeypatch ``subprocess.run`` inside ``tools.doit.release`` so the
    git calls return canned results and the ``range_spec`` argument to the
    second call can be asserted on.
    """

    @staticmethod
    def _silent_console() -> Console:
        return Console(file=io.StringIO(), force_terminal=False)

    @staticmethod
    def _fake_run(
        describe_returncode: int,
        describe_stdout: str,
        log_stdout: str,
    ) -> tuple[list[list[str]], object]:
        """Build a fake ``subprocess.run`` that captures calls.

        Returns ``(captured_calls, fake_run)``. The first git-describe call
        yields a ``CompletedProcess`` with the given ``describe_returncode``
        and ``describe_stdout``; the second git-log call yields ``log_stdout``
        with returncode 0. ``captured_calls`` is appended to on each call.
        """
        calls: list[list[str]] = []

        def fake(
            cmd: list[str],
            *_args: object,
            **_kwargs: object,
        ) -> subprocess.CompletedProcess[str]:
            calls.append(cmd)
            if "describe" in cmd:
                return subprocess.CompletedProcess(
                    args=cmd, returncode=describe_returncode, stdout=describe_stdout, stderr=""
                )
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=log_stdout, stderr="")

        return calls, fake

    def test_no_tags_falls_back_to_last_10_commits(self, monkeypatch: MonkeyPatch) -> None:
        """When ``git describe`` fails (no tags), range_spec is ``HEAD~10..HEAD``.

        Regression test for #639: the previous fallback was ``HEAD``, which
        walked full history and surfaced merges from unrelated pre-project
        ancestors on any fresh repo.
        """
        calls, fake = self._fake_run(describe_returncode=128, describe_stdout="", log_stdout="")
        monkeypatch.setattr("tools.doit.release.subprocess.run", fake)

        assert validate_merge_commits(self._silent_console()) is True

        log_cmds = [c for c in calls if "log" in c]
        assert len(log_cmds) == 1
        assert log_cmds[0][-1] == "HEAD~10..HEAD"

    def test_with_tag_uses_tag_range(self, monkeypatch: MonkeyPatch) -> None:
        """When a tag exists, range_spec is ``<last_tag>..HEAD``."""
        calls, fake = self._fake_run(
            describe_returncode=0, describe_stdout="v0.1.0\n", log_stdout=""
        )
        monkeypatch.setattr("tools.doit.release.subprocess.run", fake)

        assert validate_merge_commits(self._silent_console()) is True

        log_cmds = [c for c in calls if "log" in c]
        assert len(log_cmds) == 1
        assert log_cmds[0][-1] == "v0.1.0..HEAD"

    def test_valid_merge_commit_passes(self, monkeypatch: MonkeyPatch) -> None:
        """A merge commit matching the convention returns True."""
        _, fake = self._fake_run(
            describe_returncode=0,
            describe_stdout="v0.1.0\n",
            log_stdout="abc1234 fix: handle null (merges PR #42, addresses #41)",
        )
        monkeypatch.setattr("tools.doit.release.subprocess.run", fake)

        assert validate_merge_commits(self._silent_console()) is True

    def test_invalid_merge_commit_fails(self, monkeypatch: MonkeyPatch) -> None:
        """A merge commit not matching the convention returns False."""
        _, fake = self._fake_run(
            describe_returncode=0,
            describe_stdout="v0.1.0\n",
            log_stdout="abc1234 Merge branch 'master' of https://example.com/repo",
        )
        monkeypatch.setattr("tools.doit.release.subprocess.run", fake)

        assert validate_merge_commits(self._silent_console()) is False

    def test_prints_a_bracketed_subject_verbatim(self, monkeypatch: MonkeyPatch) -> None:
        """A subject is text, not markup: `[/tmp]` crashed `doit release` here (#900).

        Escaped, it still lost the backslash before `[1]` and turned `:sparkles:` into an emoji
        (#914).
        """
        windows = r"def5678 :sparkles: read C:\notes\[1].md"
        _, fake = self._fake_run(
            describe_returncode=0,
            describe_stdout="v0.1.0\n",
            log_stdout=f"abc1234 Merge [tool.x] from [/tmp] into main\n{windows}",
        )
        monkeypatch.setattr("tools.doit.release.subprocess.run", fake)
        console = self._silent_console()

        assert validate_merge_commits(console) is False
        output = console.file.getvalue()  # type: ignore[attr-defined]
        assert "abc1234 Merge [tool.x] from [/tmp] into main" in output
        assert windows in output


class TestExtractNextVersionFromCzOutput:
    """Tests for ``_extract_next_version_from_cz_output`` (issue #641).

    Scans the captured stdout of ``cz bump --get-next --yes`` and returns
    the last line that matches a semver-ish version pattern. Must tolerate
    leading diagnostic noise (on a tagless repo, cz prints a multi-line
    "No tag matching configuration could be found" block before emitting
    the version) and reject strings that merely contain a version substring.
    """

    @pytest.mark.parametrize(
        ("stdout", "expected"),
        [
            # Clean production-release output.
            ("1.2.3\n", "1.2.3"),
            # Clean pre-release output (PEP440).
            ("0.1.0a0\n", "0.1.0a0"),
            ("0.1.0b1\n", "0.1.0b1"),
            ("0.1.0rc0\n", "0.1.0rc0"),
            # Clean pre-release output (semver style).
            ("0.1.0-alpha.0\n", "0.1.0-alpha.0"),
            # Leading 'v' accepted and stripped.
            ("v0.2.0\n", "0.2.0"),
            # Tagless-repo case: diagnostic noise precedes the version.
            # Regression case that this helper exists to fix.
            (
                "No tag matching configuration could be found.\n"
                "Possible causes:\n"
                "- version in configuration is not the current version\n"
                "- tag_format or legacy_tag_formats is missing\n"
                "\n"
                "0.1.0a0\n",
                "0.1.0a0",
            ),
            # Trailing blank lines are ignored; the version is still found.
            ("0.1.0\n\n\n", "0.1.0"),
        ],
    )
    def test_returns_trailing_version_line(self, stdout: str, expected: str) -> None:
        assert _extract_next_version_from_cz_output(stdout) == expected

    def test_returns_none_when_no_version_line(self) -> None:
        """Output with zero version-shaped lines returns ``None``."""
        assert _extract_next_version_from_cz_output("totally unrelated output\n") is None

    def test_rejects_line_that_only_contains_a_version_substring(self) -> None:
        """The pattern is anchored to the whole line.

        A diagnostic line like ``"error at 1.2.3 somewhere"`` must not
        be mistaken for the version output.
        """
        stdout = "something broke near 1.2.3 in the build\n"
        assert _extract_next_version_from_cz_output(stdout) is None

    def test_returns_last_version_when_multiple(self) -> None:
        """When multiple version-shaped lines are present, take the last.

        cz may print intermediate version hints in diagnostic output; the
        trailing line is the authoritative one.
        """
        stdout = "0.0.1\n0.0.2\n0.0.3\n"
        assert _extract_next_version_from_cz_output(stdout) == "0.0.3"


class TestRepoHasVersionTags:
    """Tests for ``_repo_has_version_tags`` (issue #448).

    The helper shells out to ``git tag --list v*``. These tests monkeypatch
    ``subprocess.run`` inside ``tools.doit.release`` so the git call returns
    canned stdout.
    """

    @staticmethod
    def _fake_tag_list(
        stdout: str, returncode: int = 0
    ) -> Callable[..., subprocess.CompletedProcess[str]]:
        def fake(
            cmd: list[str],
            *_args: object,
            **_kwargs: object,
        ) -> subprocess.CompletedProcess[str]:
            assert cmd[:3] == ["git", "tag", "--list"]
            return subprocess.CompletedProcess(
                args=cmd, returncode=returncode, stdout=stdout, stderr=""
            )

        return fake

    def test_no_tags_returns_false(self, monkeypatch: MonkeyPatch) -> None:
        """Empty ``git tag --list v*`` output → no tags → ``False``."""
        monkeypatch.setattr("tools.doit.release.subprocess.run", self._fake_tag_list(""))
        assert _repo_has_version_tags() is False

    def test_whitespace_only_returns_false(self, monkeypatch: MonkeyPatch) -> None:
        """Whitespace-only output counts as no tags."""
        monkeypatch.setattr("tools.doit.release.subprocess.run", self._fake_tag_list("\n\n  \n"))
        assert _repo_has_version_tags() is False

    def test_one_tag_returns_true(self, monkeypatch: MonkeyPatch) -> None:
        """A single ``v*`` tag present → ``True``."""
        monkeypatch.setattr("tools.doit.release.subprocess.run", self._fake_tag_list("v0.0.0\n"))
        assert _repo_has_version_tags() is True

    def test_multiple_tags_returns_true(self, monkeypatch: MonkeyPatch) -> None:
        """Multiple ``v*`` tags present → ``True``."""
        monkeypatch.setattr(
            "tools.doit.release.subprocess.run",
            self._fake_tag_list("v0.0.0\nv0.1.0a0\nv0.1.0\n"),
        )
        assert _repo_has_version_tags() is True


class TestTaskReleaseActionSignature:
    """Regression tests for ``task_release`` CLI-param wiring (issue #650).

    doit's ``params`` parsing populates values for the **action function**,
    not the outer task-creator function. If the action doesn't accept the
    param names as kwargs, doit silently drops the CLI values and the action
    runs with closure-captured defaults. These tests pin the action signature
    so a future refactor can't re-introduce the silent drop.
    """

    def test_action_accepts_params(self) -> None:
        """The first action must accept ``increment`` and ``prerelease`` kwargs."""
        import inspect

        from tools.doit.release import task_release

        result = task_release()
        actions = result["actions"]
        assert actions, "task_release must return at least one action"
        action = actions[0]
        sig = inspect.signature(action)
        assert "increment" in sig.parameters, (
            "create_release_pr must accept 'increment' for --increment CLI flag to reach it"
        )
        assert "prerelease" in sig.parameters, (
            "create_release_pr must accept 'prerelease' for --prerelease CLI flag to reach it"
        )

    def test_params_names_match_action_signature(self) -> None:
        """Every ``params[n]['name']`` must be a parameter of the action function.

        Without this match, doit's parsed CLI values can't reach the action.
        """
        import inspect

        from tools.doit.release import task_release

        result = task_release()
        action = result["actions"][0]
        sig_params = set(inspect.signature(action).parameters)
        cli_param_names = {p["name"] for p in result["params"]}
        missing = cli_param_names - sig_params
        assert not missing, (
            f"params names {missing} have no matching kwarg in the action signature; "
            "doit will silently drop their CLI values"
        )


class TestReleaseTagGhSearch:
    """Regression test for ``task_release_tag``'s gh pr list search (issue #657).

    GitHub's search parses ``release: v in:title`` with the colon as a
    qualifier separator (like ``head:``, ``author:``), returning zero results
    for literal title substrings containing colons. ``head:release/`` is
    GitHub's intended syntax and matches the head-branch naming convention
    ``doit release`` uses for release branches.
    """

    def test_gh_search_uses_head_prefix_not_title_colon_substring(self) -> None:
        """Source must use head:release/ and not the broken title-colon search."""
        import pathlib

        # Windows read_text() defaults to cp1252 which can't decode non-ASCII
        # characters like ❌ in release.py's error banners — always specify utf-8.
        src = pathlib.Path("tools/doit/release.py").read_text(encoding="utf-8")
        assert "release: v in:title" not in src, (
            "The broken colon-in-search pattern returns zero results from gh "
            "pr list and must not recur"
        )
        assert '"head:release/"' in src, (
            "task_release_tag must use head:release/ to find merged release PRs"
        )


class _ReachedCzBuild(Exception):  # noqa: N818 - sentinel, not a runtime error
    """Sentinel raised from ``_build_cz_get_next_cmd`` to halt the task flow.

    Used by ``TestCreateReleasePrValidation`` to prove that control reached
    the cz step without exercising the real release pipeline. Suffixing
    ``Error`` would be misleading — this signals success, not failure.
    """


class TestCreateReleasePrValidation:
    """Tests for the ``--prerelease`` / ``--increment`` validation in
    ``task_release``'s action (issue #475).

    The mutex that rejected ``--prerelease`` + ``--increment`` has been
    removed; cz itself accepts both flags (increment forces the base bump,
    prerelease appends the suffix). These tests mock the pre-cz subprocess
    calls and the ``_build_cz_get_next_cmd`` helper so the action runs far
    enough to prove the combination is accepted, then stops via a sentinel
    exception before any real release work happens.

    The separate invalid-prerelease test guards against the allowed-values
    check accidentally being deleted alongside the mutex.
    """

    @staticmethod
    def _patch_precz_subprocess_calls(monkeypatch: MonkeyPatch) -> None:
        """Patch everything needed to walk from the action entry to the cz call.

        Mocks in ``tools.doit.release``:

        - ``subprocess.run``: branch=main, status clean, all other calls no-op.
        - ``run_streamed``: return ``None`` (used for ``git pull`` and
          ``doit check``).
        - ``validate_merge_commits`` / ``validate_issue_links``: return ``True``.
        - ``_build_cz_get_next_cmd``: raise ``_ReachedCzBuild`` so the flow
          stops before subprocess ever runs cz.
        """

        def fake_run(
            cmd: list[str],
            *_args: object,
            **_kwargs: object,
        ) -> subprocess.CompletedProcess[str]:
            if cmd[:3] == ["git", "branch", "--show-current"]:
                stdout = "main\n"
            elif cmd[:3] == ["git", "status", "-s"]:
                stdout = ""
            else:
                stdout = ""
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=stdout, stderr="")

        monkeypatch.setattr("tools.doit.release.subprocess.run", fake_run)
        monkeypatch.setattr("tools.doit.release.run_streamed", lambda *a, **kw: None)
        # Pretend the repo has a version tag so the tagless-repo guard at
        # release.py (still enforced for bare --prerelease) doesn't fire
        # and abort the flow before it reaches _build_cz_get_next_cmd.
        monkeypatch.setattr("tools.doit.release._repo_has_version_tags", lambda: True)
        monkeypatch.setattr(
            "tools.doit.release.validate_merge_commits",
            lambda _console: True,
        )
        monkeypatch.setattr(
            "tools.doit.release.validate_issue_links",
            lambda _console: True,
        )

        def raise_sentinel(_increment: str, _prerelease: str) -> list[str]:
            raise _ReachedCzBuild

        monkeypatch.setattr("tools.doit.release._build_cz_get_next_cmd", raise_sentinel)

    def test_prerelease_with_increment_is_accepted(self, monkeypatch: MonkeyPatch) -> None:
        """``--prerelease=alpha --increment=minor`` no longer aborts with SystemExit.

        The mutex at ``release.py`` was removed in #475. This test proves the
        combination is accepted by walking the action up to the
        ``_build_cz_get_next_cmd`` call, which the monkeypatch replaces with a
        sentinel-raising stub. If the mutex had still been in place, the action
        would have called ``sys.exit(1)`` before reaching that call.
        """
        from tools.doit.release import task_release

        self._patch_precz_subprocess_calls(monkeypatch)
        action = task_release()["actions"][0]

        # The sentinel proves the flow reached cz; SystemExit would mean the
        # mutex (or some earlier validation) rejected the combination.
        with pytest.raises(_ReachedCzBuild):
            action(increment="minor", prerelease="alpha")

    def test_invalid_prerelease_still_rejected(self, monkeypatch: MonkeyPatch) -> None:
        """An invalid ``--prerelease`` value still raises ``SystemExit``.

        Regression guard: the allowed-values check (``alpha``/``beta``/``rc``)
        sits immediately above the removed mutex block. This test ensures it
        was not dropped along with the mutex.
        """
        from tools.doit.release import task_release

        self._patch_precz_subprocess_calls(monkeypatch)
        action = task_release()["actions"][0]

        with pytest.raises(SystemExit):
            action(prerelease="gamma")

    @pytest.mark.parametrize("increment", ["major", "Minor", "PATCH"])
    def test_accepts_an_increment_in_any_case(
        self, monkeypatch: MonkeyPatch, capsys: pytest.CaptureFixture[str], increment: str
    ) -> None:
        """The task upper-cases ``--increment`` for cz, so any case passes the check (#917).

        A rejected value is printed by the check itself; see
        ``TestCreateReleasePrGuards.test_prints_a_rejected_increment_verbatim``.

        Here the helper returns a marker command instead of raising, so the flow
        passes the print and stops at the cz call.
        """
        from tools.doit.release import task_release

        self._patch_precz_subprocess_calls(monkeypatch)
        monkeypatch.setattr("tools.doit.release._build_cz_get_next_cmd", lambda *_: ["cz-next"])

        def run(
            cmd: list[str], *_args: object, **_kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            if cmd == ["cz-next"]:
                raise _ReachedCzBuild
            stdout = "main\n" if cmd[:3] == ["git", "branch", "--show-current"] else ""
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=stdout, stderr="")

        monkeypatch.setattr("tools.doit.release.subprocess.run", run)
        action = task_release()["actions"][0]

        with pytest.raises(_ReachedCzBuild):
            action(increment=increment)

        out = _ANSI.sub("", capsys.readouterr().out)
        assert f"Forcing {increment.upper()} version bump" in out


class TestGetPypiNameFromPyproject:
    """Tests for ``_get_pypi_name_from_pyproject`` (issue #478).

    The helper reads ``[project].name`` from ``pyproject.toml`` in the current
    working directory at runtime. ``task_release_tag`` calls it to substitute
    the project's PyPI name into the "Next steps" URL printout instead of
    relying on the template's spawn-time placeholder substitution (which never
    visited ``tools/doit/`` and therefore left the literal ``package-name``
    string in URLs of every spawned project).

    Each test uses ``monkeypatch.chdir(tmp_path)`` so the helper reads a
    synthetic ``pyproject.toml`` instead of the repo's real one.
    """

    def test_returns_project_name(self, tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
        """Happy path: ``[project].name = "my-pkg"`` → ``"my-pkg"``."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "my-pkg"\nversion = "0.1.0"\n',
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        assert _get_pypi_name_from_pyproject() == "my-pkg"

    def test_returns_none_when_pyproject_missing(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        """No ``pyproject.toml`` in the cwd → ``None`` (caller falls back)."""
        monkeypatch.chdir(tmp_path)
        assert _get_pypi_name_from_pyproject() is None

    def test_returns_none_when_project_table_missing(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        """Valid TOML without a ``[project]`` table → ``None``."""
        (tmp_path / "pyproject.toml").write_text(
            '[tool.poetry]\nname = "irrelevant"\n',
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        assert _get_pypi_name_from_pyproject() is None

    def test_returns_none_when_name_key_missing(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        """``[project]`` table present but no ``name`` key → ``None``."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nversion = "0.1.0"\n',
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        assert _get_pypi_name_from_pyproject() is None

    def test_returns_none_for_malformed_toml(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        """Malformed TOML → ``None`` (the ``TOMLDecodeError`` is swallowed)."""
        (tmp_path / "pyproject.toml").write_text(
            "this is = = not valid toml [[",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        assert _get_pypi_name_from_pyproject() is None


# ---------------------------------------------------------------------------
# Coverage paydown for the release paths (#708)
#
# The failure mode here is a bad or partial release: a tag pushed for the wrong
# version, or a release PR opened off the wrong branch. Both are expensive to
# undo once they reach the remote.
# ---------------------------------------------------------------------------


def _fake_git(commits: str, last_tag: str = "v1.0.0") -> object:
    """Return a subprocess.run stand-in answering `git describe` and `git log`."""

    def run(cmd: list[str], *_a: object, **_kw: object) -> MagicMock:
        if cmd[:2] == ["git", "describe"]:
            return MagicMock(stdout=f"{last_tag}\n", returncode=0 if last_tag else 128)
        if cmd[:2] == ["git", "log"]:
            return MagicMock(stdout=commits, returncode=0)
        return MagicMock(stdout="", returncode=0)

    return run


class TestValidateIssueLinks:
    """`validate_issue_links` warns but never blocks — that is deliberate."""

    def test_all_commits_referencing_issues_passes_quietly(self) -> None:
        console = Console(file=io.StringIO())

        with patch(
            "tools.doit.release.subprocess.run", side_effect=_fake_git("abc1234 feat: x (#12)")
        ):
            assert validate_issue_links(console) is True

        assert "All non-docs commits reference issues" in console.file.getvalue()  # type: ignore[attr-defined]

    def test_unlinked_commit_warns_without_blocking(self) -> None:
        """A release must not be stopped by a traceability nicety."""
        console = Console(file=io.StringIO())

        with patch(
            "tools.doit.release.subprocess.run", side_effect=_fake_git("abc1234 feat: no link")
        ):
            assert validate_issue_links(console) is True

        output = console.file.getvalue()  # type: ignore[attr-defined]
        assert "don't reference issues" in output
        assert "warning only" in output.lower()

    def test_docs_commits_are_exempt(self) -> None:
        console = Console(file=io.StringIO())

        with patch(
            "tools.doit.release.subprocess.run", side_effect=_fake_git("abc1234 docs: tidy")
        ):
            assert validate_issue_links(console) is True

        assert "All non-docs commits reference issues" in console.file.getvalue()  # type: ignore[attr-defined]

    def test_merge_commits_are_skipped(self) -> None:
        """They are validated separately by `validate_merge_commits`."""
        console = Console(file=io.StringIO())

        with patch(
            "tools.doit.release.subprocess.run",
            side_effect=_fake_git("abc1234 Merge branch 'x' into main"),
        ):
            assert validate_issue_links(console) is True

        assert "All non-docs commits reference issues" in console.file.getvalue()  # type: ignore[attr-defined]

    def test_no_commits_passes(self) -> None:
        console = Console(file=io.StringIO())

        with patch("tools.doit.release.subprocess.run", side_effect=_fake_git("")):
            assert validate_issue_links(console) is True

        assert "No commits to validate" in console.file.getvalue()  # type: ignore[attr-defined]

    def test_only_the_first_five_offenders_are_listed(self) -> None:
        """Long lists are truncated, with a count of the remainder."""
        console = Console(file=io.StringIO())
        commits = "\n".join(f"abc123{n} feat: unlinked {n}" for n in range(8))

        with patch("tools.doit.release.subprocess.run", side_effect=_fake_git(commits)):
            assert validate_issue_links(console) is True

        assert "and 3 more" in console.file.getvalue()  # type: ignore[attr-defined]

    def test_git_failure_does_not_block_the_release(self) -> None:
        """A check that cannot run must not stop a release it only advises on."""
        console = Console(file=io.StringIO())

        with patch("tools.doit.release.subprocess.run", side_effect=OSError("no git")):
            assert validate_issue_links(console) is True

        assert "Could not check issue links" in console.file.getvalue()  # type: ignore[attr-defined]


def _release_action() -> Callable[..., None]:
    """Return the `create_release_pr` action that `doit release` runs."""
    action: Callable[..., None] = task_release()["actions"][0]
    return action


def _tag_action() -> Callable[..., None]:
    """Return the `create_release_tag` action that `doit release_tag` runs."""
    action: Callable[..., None] = task_release_tag()["actions"][0]
    return action


class TestCreateReleasePrGuards:
    """`doit release` refuses before it mutates anything (#708).

    AGENTS.md says never to run this without an explicit instruction, so the
    guards that stop it early are the part worth pinning.
    """

    def test_refuses_when_not_on_main(self, capsys: pytest.CaptureFixture[str]) -> None:
        with (
            patch(
                "tools.doit.release.subprocess.run",
                return_value=MagicMock(stdout="feat/1-x\n", returncode=0),
            ),
            pytest.raises(SystemExit) as exc,
        ):
            _release_action()()

        assert exc.value.code == 1
        assert "Must be on main branch" in capsys.readouterr().out

    @pytest.mark.parametrize("value", ["gamma", "RC", "1.0", "pre"])
    def test_rejects_an_unknown_prerelease_value(self, value: str) -> None:
        """Only alpha/beta/rc are meaningful to commitizen."""
        with (
            patch(
                "tools.doit.release.subprocess.run",
                return_value=MagicMock(stdout="main\n", returncode=0),
            ),
            pytest.raises(SystemExit) as exc,
        ):
            _release_action()(prerelease=value)

        assert exc.value.code == 1

    @pytest.mark.parametrize("value", ["[x]", "[/x]", r"rc\[1]", ":memo:"])
    def test_prints_a_rejected_prerelease_verbatim(
        self, capsys: pytest.CaptureFixture[str], value: str
    ) -> None:
        """The value is text, not markup: Rich would drop `[x]` and crash on `[/x]` (#907).

        Escaped, it still lost the backslash before `[1]` and turned `:memo:` into an emoji (#914).
        """
        with (
            patch(
                "tools.doit.release.subprocess.run",
                return_value=MagicMock(stdout="main\n", returncode=0),
            ),
            pytest.raises(SystemExit) as exc,
        ):
            _release_action()(prerelease=value)

        assert exc.value.code == 1
        assert f"Invalid prerelease value '{value}'" in _ANSI.sub("", capsys.readouterr().out)

    @pytest.mark.parametrize("value", ["minr", "micro", "1", "major minor"])
    def test_rejects_an_unknown_increment_value(self, value: str) -> None:
        """cz takes only MAJOR, MINOR or PATCH, so the task stops before it pulls (#917).

        It used to pull and run `doit check` first, and only cz's own parser caught the value.
        """
        with (
            patch(
                "tools.doit.release.subprocess.run",
                return_value=MagicMock(stdout="main\n", returncode=0),
            ) as mock_run,
            patch("tools.doit.release.run_streamed") as mock_streamed,
            pytest.raises(SystemExit) as exc,
        ):
            _release_action()(increment=value)

        assert exc.value.code == 1
        assert [c.args[0] for c in mock_run.call_args_list] == [["git", "branch", "--show-current"]]
        mock_streamed.assert_not_called()

    @pytest.mark.parametrize("value", ["[x]", "[/x]", r"x\[1]", ":memo:"])
    def test_prints_a_rejected_increment_verbatim(
        self, capsys: pytest.CaptureFixture[str], value: str
    ) -> None:
        """The value is text, not markup (#907), and keeps its backslash and `:memo:` (#914).

        The check prints it as typed. Before #917 it reached the `Forcing ... version bump`
        line instead, upper-cased.
        """
        with (
            patch(
                "tools.doit.release.subprocess.run",
                return_value=MagicMock(stdout="main\n", returncode=0),
            ),
            pytest.raises(SystemExit) as exc,
        ):
            _release_action()(increment=value)

        assert exc.value.code == 1
        assert f"Invalid increment value '{value}'" in _ANSI.sub("", capsys.readouterr().out)

    @pytest.mark.parametrize("value", ["alpha", "beta", "rc"])
    def test_accepts_the_documented_prerelease_values(self, value: str) -> None:
        """These must get past validation — a guard that rejects everything is useless.

        The run stops at the governance gate, after the clean-tree check and the pull. It used
        to stop at the clean-tree check, which exits 1 just as a rejected value does, so the
        test passed even when the prerelease check rejected all three values (#919).
        """

        def fake_run(cmd: list[str], *_args: object, **_kwargs: object) -> MagicMock:
            stdout = "" if cmd[:3] == ["git", "status", "-s"] else "main\n"
            return MagicMock(stdout=stdout, returncode=0)

        with (
            patch("tools.doit.release.subprocess.run", side_effect=fake_run),
            patch("tools.doit.release._repo_has_version_tags", return_value=True),
            patch("tools.doit.release.run_streamed"),
            patch("tools.doit.release.validate_merge_commits", return_value=False) as governance,
            pytest.raises(SystemExit) as exc,
        ):
            _release_action()(prerelease=value)

        assert exc.value.code == 1
        governance.assert_called_once()

    def test_prints_uncommitted_paths_verbatim(self, capsys: pytest.CaptureFixture[str]) -> None:
        """`git status -s` output is text, not markup: a `[/x]` path crashed this guard (#900).

        Escaped, it still lost a backslash before `[1]` and turned `:memo:` into an emoji (#914).
        git quotes a path holding a backslash, and doubles the backslash.
        """
        quoted = r'?? "notes\\[1].md"'
        status = f"?? docs/[draft].md\n?? [/x]\n{quoted}\n?? :memo:.md"

        def fake_run(cmd: list[str], *_args: object, **_kwargs: object) -> MagicMock:
            stdout = status if cmd[:3] == ["git", "status", "-s"] else "main\n"
            return MagicMock(stdout=stdout, returncode=0)

        with (
            patch("tools.doit.release.subprocess.run", side_effect=fake_run),
            pytest.raises(SystemExit) as exc,
        ):
            _release_action()()

        assert exc.value.code == 1
        out = _ANSI.sub("", capsys.readouterr().out)
        assert "Uncommitted changes detected" in out
        assert "?? docs/[draft].md" in out
        assert "?? [/x]" in out
        assert quoted in out
        assert "?? :memo:.md" in out


class TestCreateReleaseTag:
    """`doit release_tag` pushes a tag — the most expensive thing to undo (#708)."""

    def test_refuses_when_not_on_main(self, capsys: pytest.CaptureFixture[str]) -> None:
        with (
            patch(
                "tools.doit.release.subprocess.run",
                return_value=MagicMock(stdout="feat/1-x\n", returncode=0),
            ),
            pytest.raises(SystemExit) as exc,
        ):
            _tag_action()()

        assert exc.value.code == 1
        assert "Must be on main branch" in capsys.readouterr().out

    def test_aborts_when_git_pull_fails(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Tagging a stale checkout would tag the wrong commit."""
        with (
            patch(
                "tools.doit.release.subprocess.run",
                return_value=MagicMock(stdout="main\n", returncode=0),
            ),
            patch(
                "tools.doit.release.run_streamed",
                side_effect=subprocess.CalledProcessError(1, ["git", "pull"]),
            ),
            pytest.raises(SystemExit) as exc,
        ):
            _tag_action()()

        assert exc.value.code == 1
        assert "Error pulling latest changes" in capsys.readouterr().out

    @staticmethod
    def _patch_happy_path(monkeypatch: MonkeyPatch) -> None:
        """Walk the action from entry to the final "Next steps" printout.

        Mocks ``subprocess.run`` for every call `create_release_tag` makes
        after the main-branch check: finding the merged release PR via
        ``gh pr list``, the existing-tag check, and ``git tag``. ``run_streamed``
        (``git pull``, ``git push``) is a no-op.
        """

        def fake_run(
            cmd: list[str], *_args: object, **_kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            if cmd[:3] == ["git", "branch", "--show-current"]:
                stdout = "main\n"
            elif cmd[:2] == ["gh", "pr"]:
                stdout = json.dumps(
                    [
                        {
                            "title": "release: v1.2.3",
                            "mergedAt": "2024-01-01T00:00:00Z",
                            "headRefName": "release/v1.2.3",
                        }
                    ]
                )
            else:
                # Covers ``git tag -l <tag>`` (no existing tag) and
                # ``git tag <tag>`` (create).
                stdout = ""
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=stdout, stderr="")

        monkeypatch.setattr("tools.doit.release.subprocess.run", fake_run)
        monkeypatch.setattr("tools.doit.release.run_streamed", lambda *a, **kw: None)

    def test_next_steps_mention_pypi_and_actions_with_release_workflow(
        self, tmp_path: Path, monkeypatch: MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """With ``.github/workflows/release.yml``, the three original steps print."""
        workflows_dir = tmp_path / ".github" / "workflows"
        workflows_dir.mkdir(parents=True)
        (workflows_dir / "release.yml").write_text("name: release\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        self._patch_happy_path(monkeypatch)

        _tag_action()()

        out = capsys.readouterr().out
        assert "Monitor GitHub Actions" in out
        assert "Check TestPyPI" in out
        assert "Check PyPI" in out

    def test_next_steps_say_tag_is_the_release_without_release_workflow(
        self, tmp_path: Path, monkeypatch: MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Without ``.github/workflows/release.yml``, no step names PyPI or Actions (#993)."""
        monkeypatch.chdir(tmp_path)
        self._patch_happy_path(monkeypatch)

        _tag_action()()

        out = capsys.readouterr().out
        assert "PyPI" not in out
        assert "GitHub Actions" not in out
        assert "tag is the release" in out


class TestMajorVersionZeroEnabled:
    """Reads ``[tool.commitizen].major_version_zero`` from the cwd's ``pyproject.toml`` (#881)."""

    @pytest.mark.parametrize(
        ("pyproject", "expected"),
        [
            ("[tool.commitizen]\nmajor_version_zero = true\n", True),
            ("[tool.commitizen]\nmajor_version_zero = false\n", False),
            ('[tool.commitizen]\nname = "cz_conventional_commits"\n', False),
            ('[project]\nname = "my-pkg"\n', False),
        ],
    )
    def test_reads_the_setting(
        self, tmp_path: Path, monkeypatch: MonkeyPatch, pyproject: str, expected: bool
    ) -> None:
        (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        assert _major_version_zero_enabled() is expected

    def test_a_missing_pyproject_counts_as_off(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        assert _major_version_zero_enabled() is False


class TestMajorVersion:
    @pytest.mark.parametrize(
        ("version", "major"),
        [("0.4.0", 0), ("1.0.0", 1), ("1.0.0a0", 1), ("2.0.0rc1", 2), ("10.1.0", 10)],
    )
    def test_reads_the_leading_number(self, version: str, major: int) -> None:
        assert _major_version(version) == major


class _ReachedBranchCreation(Exception):  # noqa: N818 - sentinel, not a runtime error
    """Sentinel raised at ``git checkout -b`` to prove the flow got past the version checks."""


_ANSI = re.compile(r"\x1b\[[0-9;]*m")


class TestReleaseRefusesMajorVersionZeroFromOne:
    """`doit release` stops at 1.0 or later while major_version_zero is on (#881).

    commitizen applies the setting at every version, so from 1.0 on every breaking
    change would bump MINOR. The check runs once the next version is known, before
    the release branch exists.
    """

    @staticmethod
    def _walk_to_branch_creation(monkeypatch: MonkeyPatch, next_version: str) -> list[list[str]]:
        """Fake every step up to ``git checkout -b``, with cz answering *next_version*."""
        calls: list[list[str]] = []

        def fake_run(
            cmd: list[str], *_args: object, **_kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            calls.append(cmd)
            if cmd[:3] == ["git", "checkout", "-b"]:
                raise _ReachedBranchCreation
            if cmd[:3] == ["git", "branch", "--show-current"]:
                stdout = "main\n"
            elif "--get-next" in cmd:
                stdout = f"{next_version}\n"
            else:
                stdout = ""
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=stdout, stderr="")

        monkeypatch.setattr("tools.doit.release.subprocess.run", fake_run)
        monkeypatch.setattr("tools.doit.release.run_streamed", lambda *a, **kw: None)
        monkeypatch.setattr("tools.doit.release.validate_merge_commits", lambda _console: True)
        monkeypatch.setattr("tools.doit.release.validate_issue_links", lambda _console: True)
        return calls

    def test_refuses_1_0_while_the_setting_is_on(
        self, monkeypatch: MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        calls = self._walk_to_branch_creation(monkeypatch, "1.0.0")
        monkeypatch.setattr("tools.doit.release._major_version_zero_enabled", lambda: True)

        with pytest.raises(SystemExit) as exc:
            _release_action()(increment="major")

        assert exc.value.code == 1
        assert not any(cmd[:3] == ["git", "checkout", "-b"] for cmd in calls)
        out = _ANSI.sub("", capsys.readouterr().out)
        assert "major_version_zero = true in [tool.commitizen]" in out

    @pytest.mark.parametrize(
        ("next_version", "enabled"),
        [("0.4.0", True), ("1.3.0", False), ("2.0.0", False)],
    )
    def test_releases_below_1_0_or_with_the_setting_off(
        self, monkeypatch: MonkeyPatch, next_version: str, enabled: bool
    ) -> None:
        self._walk_to_branch_creation(monkeypatch, next_version)
        monkeypatch.setattr("tools.doit.release._major_version_zero_enabled", lambda: enabled)

        with pytest.raises(_ReachedBranchCreation):
            _release_action()()


class TestCreateReleasePrStaticVersionAndChangelogOptIns:
    """Integration tests for the two opt-in branches `create_release_pr` gained for #971:
    bumping a static version (`version_provider` != "scm") and renaming a hand-written
    changelog (`update_changelog_on_bump = false`). Each walks the full action, in a
    `tmp_path` cwd carrying a real `pyproject.toml`/`CHANGELOG.md`, so the config-reading
    helpers and `_bump_handwritten_changelog` exercise real file I/O; only `subprocess.run`,
    `run_streamed`, and the two governance validators are faked.
    """

    _NEXT_VERSION = "1.2.0"

    _DEFAULT_CHANGELOG = (
        "# Changelog\n\n"
        "## [Unreleased]\n\n"
        "### Added\n"
        "- A hand-written entry\n\n"
        "## [0.1.0] - 2026-01-01\n\n"
        "### Added\n"
        "- First release\n"
    )

    def _patch(
        self,
        monkeypatch: MonkeyPatch,
        tmp_path: Path,
        pyproject: str,
        changelog: str | None = None,
        fail_on: list[str] | None = None,
    ) -> tuple[list[list[str]], list[list[str]]]:
        """Write real config/changelog files into ``tmp_path`` and fake the subprocess layer.

        Returns ``(subprocess_calls, streamed_calls)`` — every command list passed to
        ``subprocess.run`` and ``run_streamed`` respectively, in call order.
        """
        (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")
        (tmp_path / "CHANGELOG.md").write_text(
            changelog if changelog is not None else self._DEFAULT_CHANGELOG, encoding="utf-8"
        )
        monkeypatch.chdir(tmp_path)

        subprocess_calls: list[list[str]] = []
        streamed_calls: list[list[str]] = []

        def fake_run(
            cmd: list[str], *_args: object, **_kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            subprocess_calls.append(cmd)
            if fail_on is not None and cmd[: len(fail_on)] == fail_on:
                raise subprocess.CalledProcessError(1, cmd)
            if cmd[:3] == ["git", "branch", "--show-current"]:
                stdout = "main\n"
            elif cmd[:3] == ["git", "status", "-s"]:
                stdout = ""
            elif "--get-next" in cmd:
                stdout = f"{self._NEXT_VERSION}\n"
            else:
                stdout = ""
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=stdout, stderr="")

        def fake_streamed(cmd: list[str], **_kwargs: object) -> None:
            streamed_calls.append(cmd)
            return None

        monkeypatch.setattr("tools.doit.release.subprocess.run", fake_run)
        monkeypatch.setattr("tools.doit.release.run_streamed", fake_streamed)
        monkeypatch.setattr("tools.doit.release.validate_merge_commits", lambda _console: True)
        monkeypatch.setattr("tools.doit.release.validate_issue_links", lambda _console: True)
        return subprocess_calls, streamed_calls

    def test_template_default_is_unchanged(self, tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
        """Criterion 3: ``scm`` provider + generated changelog -> no bump, cz changelog runs.

        Regression guard: this is the template's own configuration.
        """
        pyproject = '[tool.commitizen]\nversion_provider = "scm"\nupdate_changelog_on_bump = true\n'
        subprocess_calls, streamed_calls = self._patch(monkeypatch, tmp_path, pyproject)

        _release_action()()

        assert not any("--files-only" in cmd for cmd in streamed_calls)
        assert ["uv", "run", "cz", "changelog", "--incremental"] in streamed_calls
        git_add_calls = [c for c in subprocess_calls if c[:2] == ["git", "add"]]
        assert git_add_calls == [["git", "add", "CHANGELOG.md"]]

    def test_static_version_bumps_files_and_lock(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        """Criterion 1: every version file and ``uv.lock`` are bumped and committed."""
        pyproject = (
            "[tool.commitizen]\n"
            'version_provider = "pep621"\n'
            'version_files = ["src/mypkg/__init__.py:__version__", "Makefile:VERSION"]\n'
        )
        subprocess_calls, streamed_calls = self._patch(monkeypatch, tmp_path, pyproject)

        _release_action()()

        assert [
            "uv",
            "run",
            "cz",
            "bump",
            "--files-only",
            "--yes",
            self._NEXT_VERSION,
        ] in streamed_calls
        assert ["uv", "lock"] in streamed_calls
        git_add_calls = [c for c in subprocess_calls if c[:2] == ["git", "add"]]
        assert len(git_add_calls) == 1
        assert set(git_add_calls[0][2:]) == {
            "CHANGELOG.md",
            "pyproject.toml",
            "src/mypkg/__init__.py",
            "Makefile",
            "uv.lock",
        }

    def test_handwritten_changelog_is_renamed_not_generated(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        """Criterion 2: every existing Unreleased entry survives under the new heading."""
        pyproject = "[tool.commitizen]\nupdate_changelog_on_bump = false\n"
        subprocess_calls, streamed_calls = self._patch(monkeypatch, tmp_path, pyproject)

        _release_action()()

        assert not any(cmd[-3:] == ["cz", "changelog", "--incremental"] for cmd in streamed_calls)
        result = (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8")
        today = date.today().isoformat()
        assert f"## [Unreleased]\n\n## [{self._NEXT_VERSION}] - {today}" in result
        assert "- A hand-written entry" in result
        git_add_calls = [c for c in subprocess_calls if c[:2] == ["git", "add"]]
        assert git_add_calls == [["git", "add", "CHANGELOG.md"]]

    def test_handwritten_changelog_check_aborts_before_the_branch_exists(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        """A missing/empty Unreleased section aborts before any branch or bump is made."""
        pyproject = (
            '[tool.commitizen]\nversion_provider = "pep621"\nupdate_changelog_on_bump = false\n'
        )
        empty_changelog = "# Changelog\n\n## [Unreleased]\n\n## [0.1.0] - 2026-01-01\n\n- x\n"
        subprocess_calls, streamed_calls = self._patch(
            monkeypatch, tmp_path, pyproject, changelog=empty_changelog
        )

        with pytest.raises(SystemExit) as exc:
            _release_action()()

        assert exc.value.code == 1
        assert not any(cmd[:3] == ["git", "checkout", "-b"] for cmd in subprocess_calls)
        assert not any("--files-only" in cmd for cmd in streamed_calls)
        assert (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8") == empty_changelog

    def test_a_missing_key_is_treated_as_handwritten(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        """Commitizen's default for the key is False, so no key means hand-written."""
        _subprocess_calls, streamed_calls = self._patch(
            monkeypatch, tmp_path, '[tool.commitizen]\nname = "cz_conventional_commits"\n'
        )

        _release_action()()

        assert not any(cmd[-3:] == ["cz", "changelog", "--incremental"] for cmd in streamed_calls)
        result = (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8")
        assert f"## [{self._NEXT_VERSION}] - {date.today().isoformat()}" in result

    def test_static_version_with_generated_changelog_skips_cz_changelog(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        """The bump already wrote the changelog; ``cz changelog --incremental`` would exit 16."""
        pyproject = (
            '[tool.commitizen]\nversion_provider = "pep621"\nupdate_changelog_on_bump = true\n'
        )
        _subprocess_calls, streamed_calls = self._patch(monkeypatch, tmp_path, pyproject)

        _release_action()()

        assert any("--files-only" in cmd for cmd in streamed_calls)
        assert not any(cmd[-3:] == ["cz", "changelog", "--incremental"] for cmd in streamed_calls)

    def test_abort_after_a_version_bump_discards_it_before_leaving_the_branch(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        """A failure after the bump must not carry the bumped files onto ``main``."""
        pyproject = (
            '[tool.commitizen]\nversion_provider = "pep621"\nupdate_changelog_on_bump = false\n'
        )
        subprocess_calls, streamed_calls = self._patch(
            monkeypatch, tmp_path, pyproject, fail_on=["git", "add"]
        )

        with pytest.raises(SystemExit):
            _release_action()()

        assert any("--files-only" in cmd for cmd in streamed_calls)
        restore = subprocess_calls.index(["git", "checkout", "--", "."])
        assert subprocess_calls.index(["git", "reset", "--quiet", "HEAD"]) < restore
        assert restore < subprocess_calls.index(["git", "checkout", "main"])
        branch_name = f"release/v{self._NEXT_VERSION}"
        assert ["git", "branch", "-D", branch_name] in subprocess_calls

    @staticmethod
    def _pr_body(streamed_calls: list[list[str]]) -> str:
        create = next(cmd for cmd in streamed_calls if cmd[:3] == ["gh", "pr", "create"])
        return create[create.index("--body") + 1]

    def test_issue_param_writes_addresses_line(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        """``--issue`` puts the line ``doit pr_merge`` and the issue-link check look for."""
        pyproject = '[tool.commitizen]\nversion_provider = "scm"\nupdate_changelog_on_bump = true\n'
        _subprocess_calls, streamed_calls = self._patch(monkeypatch, tmp_path, pyproject)

        _release_action()(issue="#304")

        assert re.search(r"^Addresses #304$", self._pr_body(streamed_calls), re.MULTILINE)

    def test_no_issue_param_writes_no_addresses_line(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        pyproject = '[tool.commitizen]\nversion_provider = "scm"\nupdate_changelog_on_bump = true\n'
        _subprocess_calls, streamed_calls = self._patch(monkeypatch, tmp_path, pyproject)

        _release_action()()

        assert "Addresses" not in self._pr_body(streamed_calls)

    def test_invalid_issue_param_aborts_before_anything_runs(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        pyproject = '[tool.commitizen]\nversion_provider = "scm"\nupdate_changelog_on_bump = true\n'
        subprocess_calls, _streamed_calls = self._patch(monkeypatch, tmp_path, pyproject)

        with pytest.raises(SystemExit) as exc:
            _release_action()(issue="abc")

        assert exc.value.code == 1
        assert not any(cmd[:2] == ["git", "pull"] for cmd in subprocess_calls)

    def test_static_version_body_lists_every_bumped_file(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        pyproject = (
            "[tool.commitizen]\n"
            'version_provider = "pep621"\n'
            'version_files = ["src/mypkg/__init__.py:__version__"]\n'
        )
        _subprocess_calls, streamed_calls = self._patch(monkeypatch, tmp_path, pyproject)

        _release_action()()

        body = self._pr_body(streamed_calls)
        assert "in pyproject.toml" in body
        assert "in src/mypkg/__init__.py" in body
        assert "uv.lock" in body

    @pytest.mark.parametrize(("has_workflow", "mentions_workflow"), [(True, True), (False, False)])
    def test_body_mentions_the_release_workflow_only_when_it_exists(
        self, tmp_path: Path, monkeypatch: MonkeyPatch, has_workflow: bool, mentions_workflow: bool
    ) -> None:
        pyproject = '[tool.commitizen]\nversion_provider = "scm"\nupdate_changelog_on_bump = true\n'
        if has_workflow:
            (tmp_path / ".github" / "workflows").mkdir(parents=True)
            (tmp_path / ".github" / "workflows" / "release.yml").write_text("", encoding="utf-8")
        _subprocess_calls, streamed_calls = self._patch(monkeypatch, tmp_path, pyproject)

        _release_action()()

        assert ("release workflow" in self._pr_body(streamed_calls)) is mentions_workflow

"""Tests for github.py doit tasks."""

import io
import json
import os
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

import tools.doit.github as github_mod
from tools.doit.github import (
    _PR_TITLE_PATTERN,
    _check_branch_up_to_date,
    _close_linked_issues,
    _current_branch,
    _delete_remote_branch,
    _ensure_branch_pushed,
    _extract_linked_issues,
    _fast_forward_base,
    _fetch_github_labels,
    _fetch_issue_context,
    _fetch_pr_context,
    _finish_branch_in_worktree,
    _format_merge_subject,
    _get_default_branch,
    _get_pr_info,
    _gh_env_create,
    _gh_env_exists,
    _gh_env_list,
    _gh_repo_slug,
    _is_transient_gh_error,
    _load_labels_file,
    _merged_head,
    _open_editor_with_template,
    _parse_markdown_sections,
    _read_body_file,
    _reconcile_labels,
    _run_gh_with_retry,
    _run_label_cmd,
    _validate_issue_content,
    _worktree_holding,
    task_delegation_context,
    task_env_create,
    task_env_list,
    task_issue,
    task_labels_sync,
    task_pr,
    task_pr_merge,
    task_publish_setup,
)
from tools.doit.templates import get_required_sections


class TestExtractLinkedIssues:
    """Tests for _extract_linked_issues function."""

    def test_addresses_issue(self) -> None:
        """Test extraction of 'Addresses #XX' pattern."""
        body = "Addresses #123"
        result = _extract_linked_issues(body)
        assert result == ["123"]

    def test_addresses_lowercase_ignored(self) -> None:
        """Test that lowercase 'addresses #XX' is ignored."""
        body = "addresses #456"
        result = _extract_linked_issues(body)
        assert result == []

    def test_addresses_uppercase_ignored(self) -> None:
        """Test that uppercase 'ADDRESSES #XX' is ignored."""
        body = "ADDRESSES #789"
        result = _extract_linked_issues(body)
        assert result == []

    def test_mid_sentence_ignored(self) -> None:
        """Test that mid-sentence 'Addresses #XX' is ignored."""
        body = "This PR Addresses #123"
        result = _extract_linked_issues(body)
        assert result == []

    def test_multiple_addresses(self) -> None:
        """Test extraction of multiple addresses patterns at line starts."""
        body = "Addresses #123\nAddresses #456"
        result = _extract_linked_issues(body)
        assert result == ["123", "456"]

    def test_duplicate_issues(self) -> None:
        """Test that duplicate issues are removed."""
        body = "Addresses #123\nAddresses #123"
        result = _extract_linked_issues(body)
        assert result == ["123"]

    def test_no_issues(self) -> None:
        """Test handling of body with no issues."""
        body = "This PR adds a new feature"
        result = _extract_linked_issues(body)
        assert result == []

    def test_issue_in_code_block_still_matched(self) -> None:
        """Test that issues in code blocks are still matched (by design)."""
        body = "```\nAddresses #123\n```"
        result = _extract_linked_issues(body)
        assert result == ["123"]

    def test_old_closes_keyword_not_matched(self) -> None:
        """Test that old 'Closes' keyword is not matched."""
        body = "Closes #123"
        result = _extract_linked_issues(body)
        assert result == []

    def test_old_fixes_keyword_not_matched(self) -> None:
        """Test that old 'Fixes' keyword is not matched."""
        body = "Fixes #456"
        result = _extract_linked_issues(body)
        assert result == []

    def test_old_part_of_keyword_not_matched(self) -> None:
        """Test that old 'Part of' keyword is not matched."""
        body = "Part of #101"
        result = _extract_linked_issues(body)
        assert result == []


class TestFormatMergeSubject:
    """Tests for _format_merge_subject function."""

    def test_with_single_issue(self) -> None:
        """Test formatting with a single addressed issue."""
        result = _format_merge_subject("feat: add feature", 18, ["42"])
        assert result == "feat: add feature (merges PR #18, addresses #42)"

    def test_with_multiple_issues(self) -> None:
        """Test formatting with multiple addressed issues."""
        result = _format_merge_subject("fix: bug fix", 23, ["19", "20"])
        assert result == "fix: bug fix (merges PR #23, addresses #19, #20)"

    def test_without_issues(self) -> None:
        """Test formatting without linked issues."""
        result = _format_merge_subject("docs: update readme", 29, [])
        assert result == "docs: update readme (merges PR #29)"

    def test_with_scope(self) -> None:
        """Test formatting with scoped title."""
        result = _format_merge_subject("feat(api): add endpoint", 50, ["100"])
        assert result == "feat(api): add endpoint (merges PR #50, addresses #100)"

    def test_preserves_title_exactly(self) -> None:
        """Test that PR title is preserved exactly."""
        title = "refactor: simplify complex logic"
        result = _format_merge_subject(title, 99, ["55"])
        assert result.startswith(title)


class TestCloseLinkedIssues:
    """Tests for _close_linked_issues helper."""

    def test_closes_single_linked_issue(self, mock_subprocess: MagicMock) -> None:
        """Single issue results in one gh issue close invocation."""
        console = Console()
        mock_subprocess.register({("gh", "issue", "close"): {}})
        _close_linked_issues(["123"], 45, console)

        assert mock_subprocess.call_count == 1
        args, kwargs = mock_subprocess.call_args
        assert args[0] == [
            "gh",
            "issue",
            "close",
            "123",
            "--comment",
            "Addressed in PR #45",
        ]
        assert kwargs["check"] is True
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True

    def test_closes_multiple_linked_issues(self, mock_subprocess: MagicMock) -> None:
        """Multiple issues result in multiple calls in order."""
        console = Console()
        mock_subprocess.register({("gh", "issue", "close"): {}})
        _close_linked_issues(["10", "20", "30"], 7, console)

        assert mock_subprocess.call_count == 3
        called_issues = [call.args[0][3] for call in mock_subprocess.call_args_list]
        assert called_issues == ["10", "20", "30"]

    def test_no_issues_is_noop(self, mock_subprocess: MagicMock) -> None:
        """Empty issue list results in no subprocess calls."""
        console = Console()
        _close_linked_issues([], 99, console)

        mock_subprocess.assert_not_called()

    def test_partial_failure_continues(self, mock_subprocess: MagicMock) -> None:
        """A failure on one issue does not stop subsequent closes."""
        console = Console()

        def spec(cmd: list[str]) -> MagicMock | BaseException:
            if cmd[3] == "20":
                return subprocess.CalledProcessError(returncode=1, cmd=cmd, stderr="boom")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_subprocess.register({("gh", "issue", "close"): spec})
        # Should not raise.
        _close_linked_issues(["10", "20", "30"], 7, console)

        assert mock_subprocess.call_count == 3
        called_issues = [call.args[0][3] for call in mock_subprocess.call_args_list]
        assert called_issues == ["10", "20", "30"]

    def test_close_comment_format(self, mock_subprocess: MagicMock) -> None:
        """The close comment must be exactly 'Addressed in PR #<n>'."""
        console = Console()
        mock_subprocess.register({("gh", "issue", "close"): {}})
        _close_linked_issues(["5"], 123, console)

        cmd = mock_subprocess.call_args.args[0]
        assert cmd[4] == "--comment"
        assert cmd[5] == "Addressed in PR #123"


class TestCheckBranchUpToDate:
    """Tests for _check_branch_up_to_date helper."""

    @staticmethod
    def _make_console() -> Console:
        return Console(file=io.StringIO(), width=200)

    def test_up_to_date_branch_passes(self, mock_subprocess: MagicMock) -> None:
        """rev-list --count == 0 → helper returns cleanly."""
        console = self._make_console()
        mock_subprocess.register(
            {
                ("git", "rev-list", "--count"): {"stdout": "0\n"},
                ("git", "fetch"): {},
            }
        )
        _check_branch_up_to_date("feat/x", console)

        output = console.file.getvalue()  # type: ignore[attr-defined]
        assert "up to date" in output.lower()

    def test_behind_branch_aborts(self, mock_subprocess: MagicMock) -> None:
        """rev-list --count > 0 → SystemExit(1) with remediation message."""
        console = self._make_console()
        mock_subprocess.register(
            {
                ("git", "rev-list", "--count"): {"stdout": "3\n"},
                ("git", "fetch"): {},
                ("git", "log"): {"stdout": "abc1 one\n"},
            }
        )

        with pytest.raises(SystemExit) as excinfo:
            _check_branch_up_to_date("feat/x", console)

        assert excinfo.value.code == 1
        output = console.file.getvalue()  # type: ignore[attr-defined]
        assert "3 commit" in output
        assert "git rebase origin/main" in output
        assert "feat/x" in output

    def test_fetch_failure_warns_and_proceeds(self, mock_subprocess: MagicMock) -> None:
        """git fetch failure → warning printed, helper returns."""
        console = self._make_console()
        mock_subprocess.register(
            {
                ("git", "fetch"): subprocess.CalledProcessError(
                    returncode=128, cmd=["git", "fetch"], stderr="could not resolve host"
                ),
            }
        )
        _check_branch_up_to_date("feat/x", console)

        output = console.file.getvalue()  # type: ignore[attr-defined]
        assert "warning" in output.lower()
        assert "could not resolve host" in output

    def test_behind_branch_lists_missing_commits(self, mock_subprocess: MagicMock) -> None:
        """Missing commit SHAs from `git log` appear in the output."""
        console = self._make_console()
        log_out = "abc1234 feat: one\ndef5678 fix: two\n"
        mock_subprocess.register(
            {
                ("git", "rev-list", "--count"): {"stdout": "2\n"},
                ("git", "fetch"): {},
                ("git", "log"): {"stdout": log_out},
            }
        )

        with pytest.raises(SystemExit):
            _check_branch_up_to_date("feat/x", console)

        output = console.file.getvalue()  # type: ignore[attr-defined]
        assert "abc1234" in output
        assert "def5678" in output

    def test_prints_bracketed_subjects_verbatim(self, mock_subprocess: MagicMock) -> None:
        """A subject is text, not markup: `[tool.x]` vanished and `[/tmp]` crashed (#900).

        Escaped, it still lost the backslash before `[1]` and turned `:bug:` into an emoji (#914).
        """
        console = self._make_console()
        windows = r"0f1e2d3 fix: :bug: in C:\notes\[1].md"
        log_out = (
            "56ad2af chore: move [tool.mutmut] to the keys\nabc1234 fix: strip [/tmp] prefix\n"
            f"{windows}\n"
        )
        mock_subprocess.register(
            {
                ("git", "rev-list", "--count"): {"stdout": "2\n"},
                ("git", "fetch"): {},
                ("git", "log"): {"stdout": log_out},
            }
        )

        with pytest.raises(SystemExit):
            _check_branch_up_to_date("feat/x", console)

        output = _plain(console.file.getvalue())  # type: ignore[attr-defined]
        assert "56ad2af chore: move [tool.mutmut] to the keys" in output
        assert "abc1234 fix: strip [/tmp] prefix" in output
        assert windows in output

    def test_default_base_is_main(self, mock_subprocess: MagicMock) -> None:
        mock_subprocess.register(
            {("git", "rev-list", "--count"): {"stdout": "0\n"}, ("git", "fetch"): {}}
        )
        _check_branch_up_to_date("feat/x", self._make_console())

        cmds = [c.args[0] for c in mock_subprocess.call_args_list]
        assert ["git", "fetch", "origin", "main"] in cmds
        assert ["git", "rev-list", "--count", "HEAD..origin/main"] in cmds

    def test_compares_against_the_given_base(self, mock_subprocess: MagicMock) -> None:
        """`doit pr --base` checks the branch the PR builds on, not main (#855)."""
        console = self._make_console()
        mock_subprocess.register(
            {("git", "rev-list", "--count"): {"stdout": "0\n"}, ("git", "fetch"): {}}
        )
        _check_branch_up_to_date("feat/2-upper", console, base="feat/1-lower")

        cmds = [c.args[0] for c in mock_subprocess.call_args_list]
        assert ["git", "fetch", "origin", "feat/1-lower"] in cmds
        assert ["git", "rev-list", "--count", "HEAD..origin/feat/1-lower"] in cmds
        output = console.file.getvalue()  # type: ignore[attr-defined]
        assert "up to date with origin/feat/1-lower" in output

    def test_behind_the_given_base_rebases_onto_it(self, mock_subprocess: MagicMock) -> None:
        """The layer must contain the tip of the branch it builds on (#855)."""
        console = self._make_console()
        mock_subprocess.register(
            {
                ("git", "rev-list", "--count"): {"stdout": "1\n"},
                ("git", "fetch"): {},
                ("git", "log"): {"stdout": "abc1234 feat: lower change\n"},
            }
        )

        with pytest.raises(SystemExit) as excinfo:
            _check_branch_up_to_date("feat/2-upper", console, base="feat/1-lower")

        assert excinfo.value.code == 1
        output = console.file.getvalue()  # type: ignore[attr-defined]
        assert "behind origin/feat/1-lower" in output
        assert "git rebase origin/feat/1-lower" in output


class TestEnsureBranchPushed:
    """Tests for _ensure_branch_pushed helper."""

    @staticmethod
    def _make_console() -> Console:
        return Console(file=io.StringIO(), width=200)

    def test_existing_upstream_is_noop(self, mock_subprocess: MagicMock) -> None:
        """rev-parse @{u} succeeds → no push, helper returns."""
        console = self._make_console()
        mock_subprocess.register(
            {
                ("git", "rev-parse"): {"stdout": "origin/feat/x\n"},
            }
        )
        _ensure_branch_pushed("feat/x", console, no_push=False)

        assert mock_subprocess.call_count == 1

    def test_no_upstream_pushes(self, mock_subprocess: MagicMock) -> None:
        """rev-parse @{u} fails → git push -u origin is called."""
        console = self._make_console()
        mock_subprocess.register(
            {
                ("git", "rev-parse"): subprocess.CalledProcessError(
                    returncode=128, cmd=["git", "rev-parse"], stderr="no upstream configured"
                ),
                ("git", "push", "-u"): {},
            }
        )
        _ensure_branch_pushed("feat/x", console, no_push=False)

        assert mock_subprocess.call_count == 2
        push_cmd = mock_subprocess.call_args_list[1].args[0]
        assert push_cmd == ["git", "push", "-u", "origin", "feat/x"]

    def test_push_failure_aborts(self, mock_subprocess: MagicMock) -> None:
        """rev-parse @{u} fails and git push fails → SystemExit(1)."""
        console = self._make_console()
        mock_subprocess.register(
            {
                ("git", "rev-parse"): subprocess.CalledProcessError(
                    returncode=128, cmd=["git", "rev-parse"], stderr="no upstream"
                ),
                ("git", "push", "-u"): subprocess.CalledProcessError(
                    returncode=1,
                    cmd=["git", "push", "-u"],
                    stderr="remote rejected: protected branch",
                ),
            }
        )

        with pytest.raises(SystemExit) as excinfo:
            _ensure_branch_pushed("feat/x", console, no_push=False)

        assert excinfo.value.code == 1
        output = console.file.getvalue()  # type: ignore[attr-defined]
        assert "Failed to push" in output
        assert "remote rejected" in output

    def test_prints_gits_rejection_verbatim(self, mock_subprocess: MagicMock) -> None:
        """git's `[rejected]` marker vanished from this error, and `[/x]` crashed it (#900).

        Escaped, it still lost the backslash before `[1]` and turned `:x:` into an emoji (#914).
        """
        console = self._make_console()
        hook = r"remote: hook C:\hooks\[1].ps1 failed :x:"
        stderr = (
            "To github.com:o/r.git\n"
            " ! [rejected]        feat/x -> feat/x (non-fast-forward)\n"
            "remote: see [/docs/push-rules] for details\n"
            f"{hook}\n"
        )
        mock_subprocess.register(
            {
                ("git", "rev-parse"): subprocess.CalledProcessError(
                    returncode=128, cmd=["git", "rev-parse"], stderr="no upstream"
                ),
                ("git", "push", "-u"): subprocess.CalledProcessError(
                    returncode=1, cmd=["git", "push", "-u"], stderr=stderr
                ),
            }
        )

        with pytest.raises(SystemExit):
            _ensure_branch_pushed("feat/x", console, no_push=False)

        output = _plain(console.file.getvalue())  # type: ignore[attr-defined]
        assert "! [rejected]        feat/x -> feat/x (non-fast-forward)" in output
        assert "remote: see [/docs/push-rules] for details" in output
        assert hook in output

    def test_no_push_flag_and_no_upstream_aborts(self, mock_subprocess: MagicMock) -> None:
        """no_push=True with missing upstream → SystemExit(1), no push."""
        console = self._make_console()
        mock_subprocess.register(
            {
                ("git", "rev-parse"): subprocess.CalledProcessError(
                    returncode=128, cmd=["git", "rev-parse"], stderr="no upstream"
                ),
            }
        )

        with pytest.raises(SystemExit) as excinfo:
            _ensure_branch_pushed("feat/x", console, no_push=True)

        assert excinfo.value.code == 1
        assert mock_subprocess.call_count == 1
        output = console.file.getvalue()  # type: ignore[attr-defined]
        assert "no upstream" in output.lower()
        assert "--no-push" in output

    def test_no_push_flag_with_upstream_passes(self, mock_subprocess: MagicMock) -> None:
        """no_push=True with an upstream → returns, no push."""
        console = self._make_console()
        mock_subprocess.register(
            {
                ("git", "rev-parse"): {"stdout": "origin/feat/x\n"},
            }
        )
        _ensure_branch_pushed("feat/x", console, no_push=True)

        assert mock_subprocess.call_count == 1


class TestLabelsSync:
    """Tests for the ``labels_sync`` doit task and its helpers."""

    @staticmethod
    def _make_console() -> Console:
        return Console(file=io.StringIO(), width=200)

    @staticmethod
    def _labels_file(tmp_path: Path, body: str) -> Path:
        path = tmp_path / "labels.yml"
        path.write_text(body, encoding="utf-8")
        return path

    @staticmethod
    def _register_list(mock_subprocess: MagicMock, current: list[dict[str, str]]) -> None:
        """Wire `gh label list` to return ``current`` as JSON."""
        mock_subprocess.register({("gh", "label", "list"): {"stdout": json.dumps(current)}})

    def _run_task(
        self,
        dry_run: bool = False,
        prune: bool = False,
        file: str = "",
    ) -> None:
        action = task_labels_sync()["actions"][0]
        action(dry_run=dry_run, prune=prune, file=file)

    def test_creates_missing_labels(self, tmp_path: Path, mock_subprocess: MagicMock) -> None:
        """File has 'foo', GH has none → one gh label create call."""
        labels_file = self._labels_file(
            tmp_path,
            "- name: foo\n  color: aaa111\n  description: Foo label\n",
        )
        self._register_list(mock_subprocess, [])
        mock_subprocess.register({("gh", "label", "create"): {}})

        self._run_task(file=str(labels_file))

        create_calls = [
            c for c in mock_subprocess.call_args_list if c.args[0][:3] == ["gh", "label", "create"]
        ]
        assert len(create_calls) == 1
        assert create_calls[0].args[0] == [
            "gh",
            "label",
            "create",
            "foo",
            "--color",
            "aaa111",
            "--description",
            "Foo label",
        ]

    def test_updates_mismatched_labels(self, tmp_path: Path, mock_subprocess: MagicMock) -> None:
        """File has 'foo' color aaa111, GH has color bbb222 → one gh label edit call."""
        labels_file = self._labels_file(
            tmp_path,
            "- name: foo\n  color: aaa111\n  description: Foo label\n",
        )
        self._register_list(
            mock_subprocess,
            [{"name": "foo", "color": "bbb222", "description": "Foo label"}],
        )
        mock_subprocess.register({("gh", "label", "edit"): {}})

        self._run_task(file=str(labels_file))

        edit_calls = [
            c for c in mock_subprocess.call_args_list if c.args[0][:3] == ["gh", "label", "edit"]
        ]
        assert len(edit_calls) == 1
        assert edit_calls[0].args[0] == [
            "gh",
            "label",
            "edit",
            "foo",
            "--color",
            "aaa111",
            "--description",
            "Foo label",
        ]

    def test_no_change_when_match(self, tmp_path: Path, mock_subprocess: MagicMock) -> None:
        """File and GH identical → no mutating calls."""
        labels_file = self._labels_file(
            tmp_path,
            "- name: foo\n  color: aaa111\n  description: Foo label\n",
        )
        self._register_list(
            mock_subprocess,
            [{"name": "foo", "color": "aaa111", "description": "Foo label"}],
        )

        self._run_task(file=str(labels_file))

        mutating = [
            c
            for c in mock_subprocess.call_args_list
            if c.args[0][:3]
            in (["gh", "label", "create"], ["gh", "label", "edit"], ["gh", "label", "delete"])
        ]
        assert mutating == []

    def test_prune_deletes_extras(self, tmp_path: Path, mock_subprocess: MagicMock) -> None:
        """With --prune, GH has a label not in file → gh label delete is called."""
        labels_file = self._labels_file(
            tmp_path,
            "- name: foo\n  color: aaa111\n  description: Foo label\n",
        )
        self._register_list(
            mock_subprocess,
            [
                {"name": "foo", "color": "aaa111", "description": "Foo label"},
                {"name": "old-label", "color": "cccccc", "description": "legacy"},
            ],
        )
        mock_subprocess.register({("gh", "label", "delete"): {}})

        self._run_task(file=str(labels_file), prune=True)

        delete_calls = [
            c for c in mock_subprocess.call_args_list if c.args[0][:3] == ["gh", "label", "delete"]
        ]
        assert len(delete_calls) == 1
        assert delete_calls[0].args[0] == ["gh", "label", "delete", "old-label", "--yes"]

    def test_no_prune_by_default(self, tmp_path: Path, mock_subprocess: MagicMock) -> None:
        """GH has extra label, no --prune → no delete call; extra is reported as skipped."""
        labels_file = self._labels_file(
            tmp_path,
            "- name: foo\n  color: aaa111\n  description: Foo label\n",
        )
        self._register_list(
            mock_subprocess,
            [
                {"name": "foo", "color": "aaa111", "description": "Foo label"},
                {"name": "old-label", "color": "cccccc", "description": "legacy"},
            ],
        )

        self._run_task(file=str(labels_file))

        delete_calls = [
            c for c in mock_subprocess.call_args_list if c.args[0][:3] == ["gh", "label", "delete"]
        ]
        assert delete_calls == []

    def test_dry_run_makes_no_mutations(self, tmp_path: Path, mock_subprocess: MagicMock) -> None:
        """With --dry-run, only gh label list is called; no create/edit/delete."""
        labels_file = self._labels_file(
            tmp_path,
            "- name: foo\n  color: aaa111\n  description: Foo label\n"
            "- name: bar\n  color: bbb222\n  description: Bar label\n",
        )
        self._register_list(
            mock_subprocess,
            [
                {"name": "bar", "color": "999999", "description": "Bar label"},
                {"name": "legacy", "color": "cccccc", "description": "to prune"},
            ],
        )

        self._run_task(file=str(labels_file), prune=True, dry_run=True)

        mutating = [
            c
            for c in mock_subprocess.call_args_list
            if c.args[0][:3]
            in (["gh", "label", "create"], ["gh", "label", "edit"], ["gh", "label", "delete"])
        ]
        assert mutating == []

    def test_malformed_yaml_raises_clear_error(
        self, tmp_path: Path, mock_subprocess: MagicMock
    ) -> None:
        """Entry without a 'name' field → SystemExit(1) naming the offending entry."""
        labels_file = self._labels_file(tmp_path, "- color: red\n")

        with pytest.raises(SystemExit) as excinfo:
            self._run_task(file=str(labels_file))

        assert excinfo.value.code == 1
        mock_subprocess.assert_not_called()

    def test_missing_file_raises(self, tmp_path: Path, mock_subprocess: MagicMock) -> None:
        """--file pointing at a nonexistent path → SystemExit(1)."""
        missing = tmp_path / "does-not-exist.yml"

        with pytest.raises(SystemExit) as excinfo:
            self._run_task(file=str(missing))

        assert excinfo.value.code == 1
        mock_subprocess.assert_not_called()

    @pytest.mark.parametrize("name", ["[x].yml", "[/x].yml", r"C:\notes\[1].yml", ":memo:.yml"])
    def test_missing_file_keeps_a_bracketed_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
    ) -> None:
        """The path is the user's `--file` value, text rather than markup (#907).

        Relative to tmp_path, so the only backslash before a `[` is the one a name spells out.
        A Windows path keeps it, and `:memo:` stays text (#914). The message shows `Path(name)`,
        which Windows spells `[/x].yml` with a backslash.
        """
        monkeypatch.chdir(tmp_path)
        console = Console(file=io.StringIO(), soft_wrap=True)

        with pytest.raises(SystemExit) as excinfo:
            _load_labels_file(Path(name), console)

        assert excinfo.value.code == 1
        output = _plain(console.file.getvalue())  # type: ignore[attr-defined]
        assert f"Labels file not found: {Path(name)}" in output

    @pytest.mark.parametrize(
        "name",
        [
            "[x].yml",
            "[/x].yml",
            r"x\[1].yml",
            pytest.param(
                ":memo:.yml",
                marks=pytest.mark.skipif(os.name == "nt", reason="Windows refuses : in a name"),
            ),
        ],
    )
    def test_prints_a_loaded_files_path_verbatim(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        mock_subprocess: MagicMock,
        name: str,
    ) -> None:
        """A `--file` the task has read is still the user's text, not markup (#920).

        #907 printed a missing one as text but left the path of one that loads as markup.
        """
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("COLUMNS", "1000")
        path = Path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        self._run_task(file=name)
        path.write_text("- name: foo\n  color: aaa111\n", encoding="utf-8")
        self._register_list(mock_subprocess, [])
        self._run_task(file=name, dry_run=True)

        out = _plain(capsys.readouterr().out)
        assert f"No labels defined in {name}; nothing to sync." in out
        assert f"Loaded 1 label(s) from {name}" in out

    @pytest.mark.parametrize("name", ["[x]", "[/x]", r"x\[1]", ":memo:"])
    def test_reconcile_prints_label_names_verbatim(self, name: str) -> None:
        """A label name from the file or from GitHub is text, not markup (#920).

        Rich dropped `[x]`, crashed on `[/x]`, dropped the backslash before `[1]` and turned
        `:memo:` into an emoji.
        """
        desired = [
            {"name": f"new {name}", "color": "aaa111", "description": ""},
            {"name": f"same {name}", "color": "bbb222", "description": ""},
            {"name": f"changed {name}", "color": "ccc333", "description": ""},
        ]
        current = {
            f"same {name}": {"name": f"same {name}", "color": "bbb222", "description": ""},
            f"changed {name}": {"name": f"changed {name}", "color": "999999", "description": ""},
            f"extra {name}": {"name": f"extra {name}", "color": "111111", "description": ""},
        }
        lines: list[str] = []
        for prune in (False, True):
            console = self._make_console()
            _reconcile_labels(desired, current, prune=prune, dry_run=True, console=console)
            lines += _plain(console.file.getvalue()).splitlines()  # type: ignore[attr-defined]

        assert f"+ would create new {name} (color=aaa111)" in lines
        assert f"= no change same {name}" in lines
        assert f"~ would update changed {name} (color=ccc333)" in lines
        assert f"? skipped extra {name} (not in file; use --prune to delete)" in lines
        assert f"- would delete extra {name}" in lines

    @pytest.mark.parametrize("name", ["[x]", "[/x]", r"x\[1]", ":memo:"])
    def test_labels_file_errors_print_the_entry_verbatim(self, tmp_path: Path, name: str) -> None:
        """Each error that quotes a labels-file entry prints it as text (#920)."""
        errors = {
            f"- color: '{name}'\n": f"(entry: {{'color': {name!r}}})",
            f"- name: '{name}'\n  color: 5\n": (
                f"Labels file entry '{name}' has a non-string 'color' (got int)."
            ),
            f"- name: '{name}'\n  description: 5\n": (
                f"Labels file entry '{name}' has a non-string 'description' (got int)."
            ),
        }
        for body, message in errors.items():
            console = self._make_console()
            with pytest.raises(SystemExit):
                _load_labels_file(self._labels_file(tmp_path, body), console)

            assert message in _plain(console.file.getvalue())  # type: ignore[attr-defined]

    @pytest.mark.parametrize("name", ["[x]", "[/x]", r"x\[1]", ":memo:"])
    def test_a_failed_label_command_is_printed_verbatim(self, name: str) -> None:
        """The command carries a label's name and description, which are text (#920)."""
        cmd = ["gh", "label", "create", name, "--color", "aaa111", "--description", name]
        console = self._make_console()
        error = subprocess.CalledProcessError(1, cmd, stderr="HTTP 422")
        with (
            patch("tools.doit.github._run_gh_with_retry", side_effect=error),
            pytest.raises(SystemExit),
        ):
            _run_label_cmd(cmd, console)

        lines = _plain(console.file.getvalue()).splitlines()  # type: ignore[attr-defined]
        assert f"Command failed: {' '.join(cmd)}" in lines

    def test_color_comparison_case_insensitive(
        self, tmp_path: Path, mock_subprocess: MagicMock
    ) -> None:
        """File 'FBCA04', GH 'fbca04' → no update."""
        labels_file = self._labels_file(
            tmp_path,
            "- name: needs-triage\n  color: FBCA04\n  description: triage\n",
        )
        self._register_list(
            mock_subprocess,
            [{"name": "needs-triage", "color": "fbca04", "description": "triage"}],
        )

        self._run_task(file=str(labels_file))

        mutating = [
            c
            for c in mock_subprocess.call_args_list
            if c.args[0][:3]
            in (["gh", "label", "create"], ["gh", "label", "edit"], ["gh", "label", "delete"])
        ]
        assert mutating == []

    def test_empty_description_handled(self, tmp_path: Path, mock_subprocess: MagicMock) -> None:
        """File entry with empty description → create call uses --description ''."""
        labels_file = self._labels_file(
            tmp_path,
            '- name: foo\n  color: aaa111\n  description: ""\n',
        )
        self._register_list(mock_subprocess, [])
        mock_subprocess.register({("gh", "label", "create"): {}})

        self._run_task(file=str(labels_file))

        create_calls = [
            c for c in mock_subprocess.call_args_list if c.args[0][:3] == ["gh", "label", "create"]
        ]
        assert len(create_calls) == 1
        cmd = create_calls[0].args[0]
        assert cmd[-2:] == ["--description", ""]

    def test_summary_counts_correct(self, tmp_path: Path, mock_subprocess: MagicMock) -> None:
        """Mixed scenario (create + update + no-change + skipped) → counters correct."""
        labels_file = self._labels_file(
            tmp_path,
            "\n".join(
                [
                    "- name: new-one",
                    "  color: aaa111",
                    "  description: new",
                    "- name: updated",
                    "  color: bbb222",
                    "  description: updated desc",
                    "- name: same",
                    "  color: cccccc",
                    "  description: same",
                    "",
                ]
            ),
        )
        self._register_list(
            mock_subprocess,
            [
                {"name": "updated", "color": "999999", "description": "old"},
                {"name": "same", "color": "cccccc", "description": "same"},
                {"name": "extra", "color": "111111", "description": "extra"},
            ],
        )
        mock_subprocess.register(
            {
                ("gh", "label", "create"): {},
                ("gh", "label", "edit"): {},
            }
        )

        counters = _reconcile_labels(
            _load_labels_file(labels_file, self._make_console()),
            _fetch_github_labels(self._make_console()),
            prune=False,
            dry_run=False,
            console=self._make_console(),
        )

        assert counters["created"] == 1
        assert counters["updated"] == 1
        assert counters["unchanged"] == 1
        assert counters["deleted"] == 0
        assert counters["skipped"] == 1

    def test_labels_file_parses(self) -> None:
        """The actual .github/labels.yml parses and has non-empty entries."""
        repo_labels = Path(__file__).resolve().parent.parent.parent / ".github" / "labels.yml"
        assert repo_labels.exists(), f"{repo_labels} is missing"

        entries = _load_labels_file(repo_labels, self._make_console())
        assert entries, "labels.yml should not be empty"

        names = {entry["name"] for entry in entries}
        # Two labels the issue highlighted as missing on the repo must be present.
        assert "automerge-blocked" in names
        assert "do-not-merge" in names
        # Every entry must have a 6-char hex color.
        for entry in entries:
            assert len(entry["color"]) == 6, f"bad color for {entry['name']}: {entry['color']!r}"


class TestPrTitlePattern:
    """Tests for ``_PR_TITLE_PATTERN`` (issue #655).

    The pattern gates whether ``doit pr_merge`` accepts a PR title. All eight
    standard conventional-commit types must pass; ``release`` must pass too
    (machine-generated by ``doit release``) so the release PR can be merged
    via the standard flow. Arbitrary titles must be rejected.
    """

    @pytest.mark.parametrize(
        "title",
        [
            "feat: add thing",
            "fix: bug fix",
            "refactor: restructure",
            "docs: update",
            "test: add case",
            "chore: bump dep",
            "ci: add workflow",
            "perf: speed it up",
            "release: v0.1.0a0",
            "release: v1.2.3",
            "release: v0.1.0-alpha.0",
            "fix(api): scope ok",
            "release(hotfix): v1.2.3",
        ],
    )
    def test_valid_titles_match(self, title: str) -> None:
        assert _PR_TITLE_PATTERN.match(title), f"should match: {title!r}"

    @pytest.mark.parametrize(
        "title",
        [
            "no type prefix",
            "Release: wrong case",
            "feat add colon",
            "bump: wrong type",
            "release v0.1.0a0",  # missing colon
            "",
        ],
    )
    def test_invalid_titles_reject(self, title: str) -> None:
        assert not _PR_TITLE_PATTERN.match(title), f"should not match: {title!r}"


class TestGhRepoSlug:
    """Tests for the ``_gh_repo_slug`` helper."""

    def test_returns_name_with_owner(self, mock_subprocess: MagicMock) -> None:
        """gh repo view output is stripped and returned verbatim."""
        mock_subprocess.register({("gh", "repo", "view"): {"stdout": "acme/widgets\n"}})
        assert _gh_repo_slug() == "acme/widgets"

    def test_uses_json_and_jq(self, mock_subprocess: MagicMock) -> None:
        """The command uses ``--json nameWithOwner`` and ``--jq .nameWithOwner``."""
        mock_subprocess.register({("gh", "repo", "view"): {"stdout": "o/r\n"}})
        _gh_repo_slug()

        cmd = mock_subprocess.call_args.args[0]
        assert cmd == [
            "gh",
            "repo",
            "view",
            "--json",
            "nameWithOwner",
            "--jq",
            ".nameWithOwner",
        ]


class TestGhEnvExists:
    """Tests for the ``_gh_env_exists`` helper."""

    def test_returns_true_on_200(self, mock_subprocess: MagicMock) -> None:
        """HTTP 200 (returncode 0) → True."""
        mock_subprocess.register(
            {("gh", "api", "repos/acme/widgets/environments/pypi"): {"returncode": 0}}
        )
        assert _gh_env_exists("acme/widgets", "pypi") is True

    def test_returns_false_on_404(self, mock_subprocess: MagicMock) -> None:
        """Non-zero exit (e.g., 404) → False."""
        mock_subprocess.register(
            {
                ("gh", "api", "repos/acme/widgets/environments/pypi"): {
                    "returncode": 1,
                    "stderr": "HTTP 404: Not Found",
                }
            }
        )
        assert _gh_env_exists("acme/widgets", "pypi") is False

    def test_uses_silent_flag(self, mock_subprocess: MagicMock) -> None:
        """The GET includes ``--silent`` so the response body is discarded."""
        mock_subprocess.register(
            {("gh", "api", "repos/acme/widgets/environments/pypi"): {"returncode": 0}}
        )
        _gh_env_exists("acme/widgets", "pypi")

        cmd = mock_subprocess.call_args.args[0]
        assert cmd == ["gh", "api", "repos/acme/widgets/environments/pypi", "--silent"]


class TestGhEnvCreate:
    """Tests for the ``_gh_env_create`` helper."""

    def test_sends_put(self, mock_subprocess: MagicMock) -> None:
        """The call is a ``PUT`` to the environments endpoint."""
        mock_subprocess.register({("gh", "api", "-X", "PUT"): {}})
        _gh_env_create("acme/widgets", "pypi")

        cmd = mock_subprocess.call_args.args[0]
        assert cmd == ["gh", "api", "-X", "PUT", "repos/acme/widgets/environments/pypi"]
        assert mock_subprocess.call_args.kwargs["check"] is True

    def test_propagates_failure(self, mock_subprocess: MagicMock) -> None:
        """A failed API call propagates as CalledProcessError."""
        mock_subprocess.register(
            {
                ("gh", "api", "-X", "PUT"): subprocess.CalledProcessError(
                    returncode=1, cmd=["gh"], stderr="boom"
                )
            }
        )
        with pytest.raises(subprocess.CalledProcessError):
            _gh_env_create("acme/widgets", "pypi")


class TestGhEnvList:
    """Tests for the ``_gh_env_list`` helper."""

    def test_parses_and_sorts(self, mock_subprocess: MagicMock) -> None:
        """Newline-separated names are parsed and sorted alphabetically."""
        mock_subprocess.register(
            {("gh", "api", "repos/acme/widgets/environments"): {"stdout": "testpypi\npypi\n"}}
        )
        result = _gh_env_list("acme/widgets")
        assert result == ["pypi", "testpypi"]

    def test_handles_empty(self, mock_subprocess: MagicMock) -> None:
        """Empty output yields an empty list."""
        mock_subprocess.register({("gh", "api", "repos/acme/widgets/environments"): {"stdout": ""}})
        assert _gh_env_list("acme/widgets") == []

    def test_ignores_blank_lines(self, mock_subprocess: MagicMock) -> None:
        """Blank lines and extra whitespace are ignored."""
        mock_subprocess.register(
            {
                ("gh", "api", "repos/acme/widgets/environments"): {
                    "stdout": "  pypi\n\n  testpypi  \n"
                }
            }
        )
        assert _gh_env_list("acme/widgets") == ["pypi", "testpypi"]


class TestTaskEnvCreate:
    """Tests for the ``env_create`` doit task."""

    @staticmethod
    def _action() -> "Callable[..., None]":
        action = task_env_create()["actions"][0]
        return action  # type: ignore[no-any-return]

    def test_empty_name_exits(self, mock_subprocess: MagicMock) -> None:
        """Empty ``--name`` aborts with exit 1 and no API calls."""
        with pytest.raises(SystemExit) as excinfo:
            self._action()(name="")

        assert excinfo.value.code == 1
        mock_subprocess.assert_not_called()

    def test_shortcircuits_on_existing(self, mock_subprocess: MagicMock) -> None:
        """Existing environment → no PUT is issued."""
        mock_subprocess.register(
            {
                ("gh", "repo", "view"): {"stdout": "acme/widgets\n"},
                ("gh", "api", "repos/acme/widgets/environments/pypi"): {"returncode": 0},
            }
        )

        self._action()(name="pypi")

        put_calls = [
            c for c in mock_subprocess.call_args_list if c.args[0][:4] == ["gh", "api", "-X", "PUT"]
        ]
        assert put_calls == []

    def test_creates_when_missing(self, mock_subprocess: MagicMock) -> None:
        """Missing environment → exactly one PUT is issued to the right path."""
        mock_subprocess.register(
            {
                ("gh", "repo", "view"): {"stdout": "acme/widgets\n"},
                ("gh", "api", "repos/acme/widgets/environments/pypi"): {
                    "returncode": 1,
                    "stderr": "HTTP 404",
                },
                ("gh", "api", "-X", "PUT"): {},
            }
        )

        self._action()(name="pypi")

        put_calls = [
            c for c in mock_subprocess.call_args_list if c.args[0][:4] == ["gh", "api", "-X", "PUT"]
        ]
        assert len(put_calls) == 1
        assert put_calls[0].args[0] == [
            "gh",
            "api",
            "-X",
            "PUT",
            "repos/acme/widgets/environments/pypi",
        ]

    @pytest.mark.parametrize("name", ["[x]", "[/x]", r"x\[1]", ":memo:"])
    def test_prints_the_name_verbatim(
        self, mock_subprocess: MagicMock, capsys: pytest.CaptureFixture[str], name: str
    ) -> None:
        """`--name` is the user's text, not markup, created or already there (#920)."""
        check = ("gh", "api", f"repos/acme/widgets/environments/{name}")
        mock_subprocess.register(
            {
                ("gh", "repo", "view"): {"stdout": "acme/widgets\n"},
                check: {"returncode": 1, "stderr": "HTTP 404"},
                ("gh", "api", "-X", "PUT"): {},
            }
        )
        self._action()(name=name)
        mock_subprocess.register({check: {"returncode": 0}})
        self._action()(name=name)

        lines = _plain(capsys.readouterr().out).splitlines()
        assert f"✓ Created environment '{name}' in acme/widgets" in lines
        assert f"Environment '{name}' already exists in acme/widgets — skipped" in lines


class TestTaskEnvList:
    """Tests for the ``env_list`` doit task."""

    @staticmethod
    def _action() -> "Callable[..., None]":
        action = task_env_list()["actions"][0]
        return action  # type: ignore[no-any-return]

    def test_lists_environments(self, mock_subprocess: MagicMock) -> None:
        """A populated repo prints a bulleted list and issues no writes."""
        mock_subprocess.register(
            {
                ("gh", "repo", "view"): {"stdout": "acme/widgets\n"},
                ("gh", "api", "repos/acme/widgets/environments"): {"stdout": "pypi\ntestpypi\n"},
            }
        )

        self._action()()

        put_calls = [
            c for c in mock_subprocess.call_args_list if c.args[0][:4] == ["gh", "api", "-X", "PUT"]
        ]
        assert put_calls == []
        assert mock_subprocess.call_count == 2

    def test_handles_empty_repo(self, mock_subprocess: MagicMock) -> None:
        """No environments → helper returns cleanly (no SystemExit, no writes)."""
        mock_subprocess.register(
            {
                ("gh", "repo", "view"): {"stdout": "acme/widgets\n"},
                ("gh", "api", "repos/acme/widgets/environments"): {"stdout": ""},
            }
        )

        # Must not raise.
        self._action()()

        put_calls = [
            c for c in mock_subprocess.call_args_list if c.args[0][:4] == ["gh", "api", "-X", "PUT"]
        ]
        assert put_calls == []

    def test_prints_the_names_verbatim(
        self, mock_subprocess: MagicMock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Environment names come from GitHub: text, not markup (#920)."""
        names = sorted(["[x]", "[/x]", r"x\[1]", ":memo:"])
        mock_subprocess.register(
            {
                ("gh", "repo", "view"): {"stdout": "acme/widgets\n"},
                ("gh", "api", "repos/acme/widgets/environments"): {"stdout": "\n".join(names)},
            }
        )

        self._action()()

        lines = _plain(capsys.readouterr().out).splitlines()
        assert [line for line in lines if line.startswith("  • ")] == [f"  • {n}" for n in names]


class TestTaskPublishSetup:
    """Tests for the ``publish_setup`` doit task."""

    @staticmethod
    def _action() -> "Callable[..., None]":
        action = task_publish_setup()["actions"][0]
        return action  # type: ignore[no-any-return]

    def test_creates_both_when_missing(self, mock_subprocess: MagicMock) -> None:
        """Both ``testpypi`` and ``pypi`` are PUT when neither exists."""

        def api_spec(cmd: list[str]) -> MagicMock:
            # PUT requests succeed with 200.
            if cmd[:4] == ["gh", "api", "-X", "PUT"]:
                return MagicMock(returncode=0, stdout="", stderr="")
            # GET environment-exists checks always 404 for this test.
            return MagicMock(returncode=1, stdout="", stderr="HTTP 404")

        mock_subprocess.register(
            {
                ("gh", "repo", "view"): {"stdout": "acme/widgets\n"},
                ("gh", "api"): api_spec,
            }
        )

        self._action()()

        put_calls = [
            c for c in mock_subprocess.call_args_list if c.args[0][:4] == ["gh", "api", "-X", "PUT"]
        ]
        assert len(put_calls) == 2
        put_paths = [c.args[0][4] for c in put_calls]
        assert put_paths == [
            "repos/acme/widgets/environments/testpypi",
            "repos/acme/widgets/environments/pypi",
        ]

    def test_idempotent_when_both_exist(self, mock_subprocess: MagicMock) -> None:
        """When both environments exist, no PUT is issued."""
        mock_subprocess.register(
            {
                ("gh", "repo", "view"): {"stdout": "acme/widgets\n"},
                ("gh", "api", "repos/acme/widgets/environments/testpypi"): {"returncode": 0},
                ("gh", "api", "repos/acme/widgets/environments/pypi"): {"returncode": 0},
            }
        )

        self._action()()

        put_calls = [
            c for c in mock_subprocess.call_args_list if c.args[0][:4] == ["gh", "api", "-X", "PUT"]
        ]
        assert put_calls == []

    def test_creates_only_missing(self, mock_subprocess: MagicMock) -> None:
        """Only the missing environment is PUT; existing one is skipped."""

        def api_spec(cmd: list[str]) -> MagicMock:
            if cmd[:4] == ["gh", "api", "-X", "PUT"]:
                return MagicMock(returncode=0, stdout="", stderr="")
            # testpypi exists, pypi does not.
            if cmd[2] == "repos/acme/widgets/environments/testpypi":
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=1, stdout="", stderr="HTTP 404")

        mock_subprocess.register(
            {
                ("gh", "repo", "view"): {"stdout": "acme/widgets\n"},
                ("gh", "api"): api_spec,
            }
        )

        self._action()()

        put_calls = [
            c for c in mock_subprocess.call_args_list if c.args[0][:4] == ["gh", "api", "-X", "PUT"]
        ]
        assert len(put_calls) == 1
        assert put_calls[0].args[0][4] == "repos/acme/widgets/environments/pypi"

    def test_output_lists_all_three_trusted_publishers(
        self, mock_subprocess: MagicMock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Panel output enumerates all three (workflow, env) registrations."""
        mock_subprocess.register(
            {
                ("gh", "repo", "view"): {"stdout": "acme/widgets\n"},
                ("gh", "api", "repos/acme/widgets/environments/testpypi"): {"returncode": 0},
                ("gh", "api", "repos/acme/widgets/environments/pypi"): {"returncode": 0},
            }
        )

        self._action()()

        # Collapse all whitespace so assertions are robust against any
        # rich-driven line wrapping inside the Panel.fit output.
        captured = capsys.readouterr().out
        collapsed = " ".join(captured.split())

        # All three (workflow, env) pairs must be mentioned.
        assert "workflow=testpypi.yml, env=testpypi" in collapsed
        assert "workflow=release.yml, env=testpypi" in collapsed
        assert "workflow=release.yml, env=pypi" in collapsed

        # Both publishing URLs must appear. The TestPyPI URL must appear
        # at least twice (once per TestPyPI registration).
        assert "https://pypi.org/manage/account/publishing/" in collapsed
        assert "https://test.pypi.org/manage/account/publishing/" in collapsed
        assert collapsed.count("https://test.pypi.org/manage/account/publishing/") >= 2

        # The owner/repo values from _gh_repo_slug must appear.
        assert "acme" in collapsed
        assert "widgets" in collapsed


class TestIsTransientGhError:
    """Tests for _is_transient_gh_error string classifier."""

    def test_5xx_gateway_timeout(self) -> None:
        """HTTP 504 Gateway Timeout is classified as transient."""
        result = _is_transient_gh_error("non-200 OK status code: 504 Gateway Timeout")
        assert result is not None

    def test_503_service_unavailable(self) -> None:
        """503 Service Unavailable substring is classified as transient."""
        result = _is_transient_gh_error("503 Service Unavailable")
        assert result is not None

    def test_unicorn_marker(self) -> None:
        """GitHub's 'Unicorn!' error page is classified as transient."""
        result = _is_transient_gh_error("Unicorn!")
        assert result is not None

    def test_connection_refused(self) -> None:
        """'connection refused' is classified as transient."""
        result = _is_transient_gh_error("connection refused")
        assert result is not None

    def test_io_timeout(self) -> None:
        """'i/o timeout' is classified as transient."""
        result = _is_transient_gh_error("i/o timeout")
        assert result is not None

    def test_http_404_not_transient(self) -> None:
        """HTTP 404 Not Found is NOT transient."""
        result = _is_transient_gh_error("HTTP 404 Not Found")
        assert result is None

    def test_validation_error_not_transient(self) -> None:
        """Validation errors are NOT transient."""
        result = _is_transient_gh_error("Validation Failed: title required")
        assert result is None

    def test_empty_string_not_transient(self) -> None:
        """Empty string returns None (not transient)."""
        result = _is_transient_gh_error("")
        assert result is None


class TestRunGhWithRetry:
    """Tests for _run_gh_with_retry retry logic."""

    def test_success_on_first_attempt(
        self, mock_subprocess: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Successful first attempt returns result without calling sleep."""
        sleep_mock = MagicMock()
        monkeypatch.setattr(github_mod.time, "sleep", sleep_mock)
        monkeypatch.setattr(github_mod.random, "uniform", lambda *_: 0.0)

        mock_subprocess.register({("gh", "issue"): {"returncode": 0, "stdout": "ok"}})
        result = _run_gh_with_retry(["gh", "issue", "list"], check=True)

        assert result.stdout == "ok"
        sleep_mock.assert_not_called()

    @pytest.mark.parametrize("name", ["[x]", "[/x]", r"x\[1]", ":memo:"])
    def test_prints_the_retried_command_verbatim(
        self,
        mock_subprocess: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        name: str,
    ) -> None:
        """The command can name an environment, which is the user's text, not markup (#920)."""
        monkeypatch.setattr(github_mod.time, "sleep", MagicMock())
        monkeypatch.setattr(github_mod.random, "uniform", lambda *_: 0.0)
        monkeypatch.setenv("DOIT_GH_RETRIES", "1")
        monkeypatch.setenv("COLUMNS", "1000")
        error = subprocess.CalledProcessError(1, ["gh"], stderr="HTTP 502 Bad Gateway")
        mock_subprocess.register({("gh", "api"): error})
        path = f"repos/acme/widgets/environments/{name}"

        with pytest.raises(subprocess.CalledProcessError):
            _run_gh_with_retry(["gh", "api", path, "--silent"], check=True)

        assert f"Retry 1/1: gh api {path} (transient:" in _plain(capsys.readouterr().out)

    def test_success_after_one_transient_retry(
        self, mock_subprocess: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """First attempt raises transient 504, second attempt succeeds."""
        sleep_mock = MagicMock()
        monkeypatch.setattr(github_mod.time, "sleep", sleep_mock)
        monkeypatch.setattr(github_mod.random, "uniform", lambda *_: 0.0)
        monkeypatch.setenv("DOIT_GH_RETRIES", "3")

        call_count = 0

        def spec(cmd: list[str]) -> MagicMock | BaseException:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return subprocess.CalledProcessError(
                    returncode=1,
                    cmd=cmd,
                    stderr="non-200 OK status code: 504 Gateway Timeout",
                )
            return MagicMock(returncode=0, stdout="merged", stderr="")

        mock_subprocess.register({("gh", "pr"): spec})
        result = _run_gh_with_retry(["gh", "pr", "merge", "42"], check=True)

        assert result.stdout == "merged"
        assert sleep_mock.call_count == 1

    def test_all_retries_exhausted_check_true(
        self, mock_subprocess: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """All retries exhausted with check=True raises CalledProcessError."""
        sleep_mock = MagicMock()
        monkeypatch.setattr(github_mod.time, "sleep", sleep_mock)
        monkeypatch.setattr(github_mod.random, "uniform", lambda *_: 0.0)
        monkeypatch.setenv("DOIT_GH_RETRIES", "2")

        mock_subprocess.register(
            {
                ("gh", "api"): subprocess.CalledProcessError(
                    returncode=1,
                    cmd=["gh", "api"],
                    stderr="503 Service Unavailable",
                )
            }
        )

        with pytest.raises(subprocess.CalledProcessError):
            _run_gh_with_retry(["gh", "api", "/repos"], check=True)

        # 2 retries means 3 total attempts → 2 sleeps
        assert sleep_mock.call_count == 2

    def test_non_retryable_4xx_raises_immediately(
        self, mock_subprocess: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non-transient (4xx) failure with check=True raises without sleeping."""
        sleep_mock = MagicMock()
        monkeypatch.setattr(github_mod.time, "sleep", sleep_mock)
        monkeypatch.setattr(github_mod.random, "uniform", lambda *_: 0.0)

        mock_subprocess.register(
            {
                ("gh", "issue"): subprocess.CalledProcessError(
                    returncode=1,
                    cmd=["gh", "issue"],
                    stderr="HTTP 422 Validation Failed: title required",
                )
            }
        )

        with pytest.raises(subprocess.CalledProcessError):
            _run_gh_with_retry(["gh", "issue", "create"], check=True)

        sleep_mock.assert_not_called()

    def test_check_false_transient_returns_after_exhaustion(
        self, mock_subprocess: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """check=False with transient errors retries then returns CompletedProcess."""
        sleep_mock = MagicMock()
        monkeypatch.setattr(github_mod.time, "sleep", sleep_mock)
        monkeypatch.setattr(github_mod.random, "uniform", lambda *_: 0.0)
        monkeypatch.setenv("DOIT_GH_RETRIES", "2")

        mock_subprocess.register(
            {
                ("gh", "api"): subprocess.CalledProcessError(
                    returncode=1,
                    cmd=["gh", "api"],
                    stderr="503 Service Unavailable",
                )
            }
        )

        result = _run_gh_with_retry(["gh", "api", "/test"], check=False)

        assert result.returncode == 1
        assert "503" in result.stderr
        assert sleep_mock.call_count == 2

    def test_check_false_non_transient_returns_immediately(
        self, mock_subprocess: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """check=False with non-transient error returns immediately without retry."""
        sleep_mock = MagicMock()
        monkeypatch.setattr(github_mod.time, "sleep", sleep_mock)
        monkeypatch.setattr(github_mod.random, "uniform", lambda *_: 0.0)

        mock_subprocess.register(
            {
                ("gh", "api"): subprocess.CalledProcessError(
                    returncode=1,
                    cmd=["gh", "api"],
                    stderr="HTTP 404 Not Found",
                )
            }
        )

        result = _run_gh_with_retry(["gh", "api", "/missing"], check=False)

        assert result.returncode == 1
        sleep_mock.assert_not_called()

    def test_doit_gh_retries_zero_no_sleep(
        self, mock_subprocess: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """DOIT_GH_RETRIES=0 means single attempt — failure raises, no sleep."""
        sleep_mock = MagicMock()
        monkeypatch.setattr(github_mod.time, "sleep", sleep_mock)
        monkeypatch.setattr(github_mod.random, "uniform", lambda *_: 0.0)
        monkeypatch.setenv("DOIT_GH_RETRIES", "0")

        mock_subprocess.register(
            {
                ("gh", "label"): subprocess.CalledProcessError(
                    returncode=1,
                    cmd=["gh", "label"],
                    stderr="503 Service Unavailable",
                )
            }
        )

        with pytest.raises(subprocess.CalledProcessError):
            _run_gh_with_retry(["gh", "label", "list"])

        sleep_mock.assert_not_called()

    def test_doit_gh_backoff_base_zero_sleep_near_zero(
        self, mock_subprocess: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """DOIT_GH_BACKOFF_BASE=0.0 results in sleep called with ~0.0 delay."""
        sleep_calls: list[float] = []
        monkeypatch.setattr(github_mod.time, "sleep", lambda s: sleep_calls.append(s))
        monkeypatch.setattr(github_mod.random, "uniform", lambda *_: 0.0)
        monkeypatch.setenv("DOIT_GH_RETRIES", "1")
        monkeypatch.setenv("DOIT_GH_BACKOFF_BASE", "0.0")

        call_count = 0

        def spec(cmd: list[str]) -> MagicMock | BaseException:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return subprocess.CalledProcessError(
                    returncode=1, cmd=cmd, stderr="503 Service Unavailable"
                )
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_subprocess.register({("gh", "repo"): spec})
        _run_gh_with_retry(["gh", "repo", "view"])

        assert len(sleep_calls) == 1
        assert sleep_calls[0] == pytest.approx(0.0, abs=1e-9)

    def test_retry_banner_printed(
        self,
        mock_subprocess: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Retry banner is printed to console on transient failure."""
        monkeypatch.setattr(github_mod.time, "sleep", lambda *_: None)
        monkeypatch.setattr(github_mod.random, "uniform", lambda *_: 0.0)
        monkeypatch.setenv("DOIT_GH_RETRIES", "1")

        call_count = 0

        def spec(cmd: list[str]) -> MagicMock | BaseException:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return subprocess.CalledProcessError(
                    returncode=1, cmd=cmd, stderr="503 Service Unavailable"
                )
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_subprocess.register({("gh", "pr"): spec})

        with patch("tools.doit.github.Console") as mock_console_cls:
            mock_console = MagicMock()
            mock_console_cls.return_value = mock_console
            _run_gh_with_retry(["gh", "pr", "view"])

        printed = " ".join(str(call.args[0]) for call in mock_console.print.call_args_list)
        assert "Retry" in printed
        assert "1/1" in printed


# ---------------------------------------------------------------------------
# Coverage paydown for the mandated workflow paths (#708)
#
# AGENTS.md requires `doit issue`, `doit pr` and `doit pr_merge` for every
# change, so a defect in any of them blocks all work and is expensive to undo.
# #689 made the gap visible; these cover it.
# ---------------------------------------------------------------------------


class TestParseMarkdownSections:
    """`_parse_markdown_sections` splits an issue body into its `##` sections."""

    def test_splits_on_level_two_headers(self) -> None:
        content = "## Problem\nIt breaks.\n\n## Proposed Solution\nFix it.\n"

        assert _parse_markdown_sections(content) == {
            "Problem": "It breaks.",
            "Proposed Solution": "Fix it.",
        }

    def test_content_before_the_first_header_is_dropped(self) -> None:
        """Preamble belongs to no section, so it cannot satisfy a required one."""
        assert _parse_markdown_sections("stray preamble\n\n## Problem\nreal\n") == {
            "Problem": "real"
        }

    def test_deeper_headers_stay_inside_their_section(self) -> None:
        """`###` is body text, not a section boundary."""
        sections = _parse_markdown_sections("## Problem\n### Detail\nnested\n")

        assert list(sections) == ["Problem"]
        assert "### Detail" in sections["Problem"]

    def test_empty_content_yields_no_sections(self) -> None:
        assert _parse_markdown_sections("") == {}


class TestValidateIssueContent:
    """`_validate_issue_content` gates issue creation on required sections."""

    def test_missing_required_section_is_rejected(self) -> None:
        console = Console(file=io.StringIO())

        assert _validate_issue_content({}, "feature", console) is False
        assert "Missing required sections" in console.file.getvalue()  # type: ignore[attr-defined]

    def test_section_present_but_empty_is_rejected(self) -> None:
        """Whitespace is not content — an empty heading must not pass."""
        console = Console(file=io.StringIO())
        sections = dict.fromkeys(get_required_sections("feature"), "   \n  ")

        assert _validate_issue_content(sections, "feature", console) is False

    def test_complete_sections_pass(self) -> None:
        console = Console(file=io.StringIO())
        sections = dict.fromkeys(get_required_sections("feature"), "real content here")

        assert _validate_issue_content(sections, "feature", console) is True

    def test_placeholder_text_warns_but_still_passes(self) -> None:
        """A warning, not a rejection: the text may be legitimately similar."""
        console = Console(file=io.StringIO())
        sections = dict.fromkeys(get_required_sections("feature"), "Describe the problem")

        assert _validate_issue_content(sections, "feature", console) is True
        assert "placeholder" in console.file.getvalue().lower()  # type: ignore[attr-defined]


class TestReadBodyFile:
    """`_read_body_file` backs `--body-file`, which AGENTS.md recommends."""

    def test_reads_existing_file(self, tmp_path: Path) -> None:
        body = tmp_path / "body.md"
        body.write_text("## Problem\ncontent\n", encoding="utf-8")

        assert _read_body_file(str(body), Console(file=io.StringIO())) == "## Problem\ncontent\n"

    def test_missing_file_reports_and_returns_none(self, tmp_path: Path) -> None:
        console = Console(file=io.StringIO())

        assert _read_body_file(str(tmp_path / "absent.md"), console) is None
        assert "File not found" in console.file.getvalue()  # type: ignore[attr-defined]

    def test_unreadable_file_reports_and_returns_none(self, tmp_path: Path) -> None:
        """A directory passed as a file must not raise past the caller."""
        console = Console(file=io.StringIO())

        assert _read_body_file(str(tmp_path), console) is None
        assert "Error reading file" in console.file.getvalue()  # type: ignore[attr-defined]

    def test_error_keeps_a_bracketed_path(self, tmp_path: Path) -> None:
        """The error quotes the path, which is text, not markup (#900)."""
        folder = tmp_path / "[draft]"
        folder.mkdir()
        # soft_wrap: a long tmp_path would otherwise wrap inside "[draft]".
        console = Console(file=io.StringIO(), soft_wrap=True)

        assert _read_body_file(str(folder), console) is None
        assert "[draft]" in _plain(console.file.getvalue())  # type: ignore[attr-defined]

    def test_error_keeps_backslashes_and_shortcodes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Escaped, the error dropped the backslash before `[1]` and replaced `:memo:` (#914).

        `read_text` is patched to raise the message, so the test does not depend on the OS.
        """
        body = tmp_path / "body.md"
        body.write_text("x", encoding="utf-8")
        message = r"cannot read C:\notes\[1].md :memo:"

        def fail(*_args: object, **_kwargs: object) -> str:
            raise OSError(message)

        monkeypatch.setattr(Path, "read_text", fail)
        console = Console(file=io.StringIO(), soft_wrap=True)

        assert _read_body_file(str(body), console) is None
        output = _plain(console.file.getvalue())  # type: ignore[attr-defined]
        assert f"Error reading file: {message}" in output

    @pytest.mark.parametrize("name", ["[x].md", "[/x].md", r"C:\notes\[1].md", ":memo:.md"])
    def test_missing_file_keeps_a_bracketed_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
    ) -> None:
        """The path is the user's `--body-file` value, text rather than markup (#907).

        Relative to tmp_path, so the only backslash before a `[` is the one a name spells out.
        A Windows path keeps it, and `:memo:` stays text (#914).
        """
        monkeypatch.chdir(tmp_path)
        console = Console(file=io.StringIO(), soft_wrap=True)

        assert _read_body_file(name, console) is None
        output = _plain(console.file.getvalue())  # type: ignore[attr-defined]
        assert f"File not found: {name}" in output


def _issue_action() -> Callable[..., None]:
    """Return the `create_issue` action that `doit issue` runs."""
    action: Callable[..., None] = task_issue()["actions"][0]
    return action


class TestCreateIssue:
    """`doit issue` — AGENTS.md mandates it for every issue (#708)."""

    @staticmethod
    def _valid_body(issue_type: str = "feature") -> str:
        return "\n".join(
            f"## {section}\nreal content for {section}\n"
            for section in get_required_sections(issue_type)
        )

    def test_creates_issue_from_body_file(
        self, tmp_path: Path, mock_subprocess: MagicMock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        body = tmp_path / "body.md"
        body.write_text(self._valid_body(), encoding="utf-8")
        mock_subprocess.register(
            {("gh", "issue", "create"): {"stdout": "https://github.com/o/r/issues/42\n"}}
        )

        _issue_action()(type="feature", title="feat: a thing", body_file=str(body))

        cmd = mock_subprocess.call_args.args[0]
        assert cmd[:3] == ["gh", "issue", "create"]
        assert "feat: a thing" in cmd
        assert "https://github.com/o/r/issues/42" in capsys.readouterr().out

    def test_creates_issue_from_inline_body(self, mock_subprocess: MagicMock) -> None:
        mock_subprocess.register({("gh", "issue", "create"): {"stdout": "url\n"}})

        _issue_action()(type="feature", title="feat: x", body=self._valid_body())

        assert mock_subprocess.call_count == 1

    def test_labels_come_from_the_template(self, mock_subprocess: MagicMock) -> None:
        """The label set is the template's, not the caller's — AGENTS.md relies on this."""
        mock_subprocess.register({("gh", "issue", "create"): {"stdout": "url\n"}})

        _issue_action()(type="bug", title="bug: x", body=self._valid_body("bug"))

        cmd = mock_subprocess.call_args.args[0]
        assert "--label" in cmd
        assert cmd[cmd.index("--label") + 1]

    def test_unknown_issue_type_exits(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exc:
            _issue_action()(type="not-a-type", title="x", body="## Problem\ncontent")

        assert exc.value.code == 1

    @pytest.mark.parametrize("issue_type", ["[x]", "[/x]", r"bug\[1]", ":bug:"])
    def test_prints_a_bracketed_type_verbatim(
        self, capsys: pytest.CaptureFixture[str], issue_type: str
    ) -> None:
        """The opening panel prints `--type` before it is validated (#907, #914)."""
        with pytest.raises(SystemExit) as exc:
            _issue_action()(type=issue_type, title="x", body="## Problem\ncontent")

        assert exc.value.code == 1
        assert f"Creating {issue_type} Issue" in _plain(capsys.readouterr().out)

    def test_missing_body_file_exits(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit) as exc:
            _issue_action()(type="feature", title="x", body_file=str(tmp_path / "nope.md"))

        assert exc.value.code == 1

    def test_incomplete_body_is_rejected_before_calling_gh(
        self, mock_subprocess: MagicMock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Validation must gate the API call, not follow it."""
        with pytest.raises(SystemExit) as exc:
            _issue_action()(type="feature", title="x", body="## Problem\n")

        assert exc.value.code == 1
        assert mock_subprocess.call_count == 0
        assert "validation failed" in capsys.readouterr().out.lower()

    def test_gh_failure_exits_nonzero(self, mock_subprocess: MagicMock) -> None:
        mock_subprocess.register(
            {("gh", "issue", "create"): subprocess.CalledProcessError(1, ["gh"], stderr="denied")}
        )

        with pytest.raises(SystemExit) as exc:
            _issue_action()(type="feature", title="x", body=self._valid_body())

        assert exc.value.code == 1

    def test_title_is_prompted_when_absent(self, mock_subprocess: MagicMock) -> None:
        mock_subprocess.register({("gh", "issue", "create"): {"stdout": "url\n"}})

        with patch("builtins.input", return_value="feat: prompted title"):
            _issue_action()(type="feature", body=self._valid_body())

        assert "feat: prompted title" in mock_subprocess.call_args.args[0]

    def test_empty_prompted_title_exits(self, mock_subprocess: MagicMock) -> None:
        with patch("builtins.input", return_value="   "), pytest.raises(SystemExit) as exc:
            _issue_action()(type="feature", body=self._valid_body())

        assert exc.value.code == 1
        assert mock_subprocess.call_count == 0


def _pr_action() -> Callable[..., None]:
    """Return the `create_pr` action that `doit pr` runs."""
    action: Callable[..., None] = task_pr()["actions"][0]
    return action


class TestCreatePr:
    """`doit pr` — AGENTS.md mandates it for every PR (#708)."""

    @staticmethod
    def _on_branch(name: str) -> MagicMock:
        return MagicMock(stdout=f"{name}\n", returncode=0)

    def test_refuses_to_open_a_pr_from_main(self, capsys: pytest.CaptureFixture[str]) -> None:
        """The NEVER-commit-to-main rule has a PR-shaped counterpart."""
        with (
            patch("tools.doit.github.subprocess.run", return_value=self._on_branch("main")),
            pytest.raises(SystemExit) as exc,
        ):
            _pr_action()(title="feat: x", body="## Description\nx")

        assert exc.value.code == 1
        assert "Cannot create PR from main" in capsys.readouterr().out

    def test_creates_pr_and_reports_the_url(self, capsys: pytest.CaptureFixture[str]) -> None:
        with (
            patch(
                "tools.doit.github.subprocess.run",
                return_value=self._on_branch("feat/42-thing"),
            ),
            patch("tools.doit.github._check_branch_up_to_date"),
            patch("tools.doit.github._ensure_branch_pushed"),
            patch(
                "tools.doit.github._run_gh_with_retry",
                return_value=MagicMock(stdout="https://github.com/o/r/pull/7\n"),
            ) as mock_gh,
        ):
            _pr_action()(title="feat: x", body="## Description\nx\n\nAddresses #42")

        cmd = mock_gh.call_args.args[0]
        assert cmd[:3] == ["gh", "pr", "create"]
        assert "https://github.com/o/r/pull/7" in capsys.readouterr().out

    def test_draft_flag_is_forwarded(self) -> None:
        with (
            patch(
                "tools.doit.github.subprocess.run",
                return_value=self._on_branch("feat/42-thing"),
            ),
            patch("tools.doit.github._check_branch_up_to_date"),
            patch("tools.doit.github._ensure_branch_pushed"),
            patch(
                "tools.doit.github._run_gh_with_retry", return_value=MagicMock(stdout="url\n")
            ) as mock_gh,
        ):
            _pr_action()(title="feat: x", body="## Description\nx", draft=True)

        assert "--draft" in mock_gh.call_args.args[0]

    def test_no_update_check_skips_the_up_to_date_guard(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """`--no-update-check` is the documented override; it must actually skip."""
        with (
            patch(
                "tools.doit.github.subprocess.run",
                return_value=self._on_branch("feat/42-thing"),
            ),
            patch("tools.doit.github._check_branch_up_to_date") as mock_check,
            patch("tools.doit.github._ensure_branch_pushed"),
            patch("tools.doit.github._run_gh_with_retry", return_value=MagicMock(stdout="u\n")),
        ):
            _pr_action()(title="feat: x", body="## Description\nx", no_update_check=True)

        mock_check.assert_not_called()
        assert "Skipping up-to-date check" in capsys.readouterr().out

    def test_up_to_date_guard_runs_by_default(self) -> None:
        with (
            patch(
                "tools.doit.github.subprocess.run",
                return_value=self._on_branch("feat/42-thing"),
            ),
            patch("tools.doit.github._check_branch_up_to_date") as mock_check,
            patch("tools.doit.github._ensure_branch_pushed"),
            patch("tools.doit.github._run_gh_with_retry", return_value=MagicMock(stdout="u\n")),
        ):
            _pr_action()(title="feat: x", body="## Description\nx")

        mock_check.assert_called_once()

    def test_no_push_is_forwarded_to_the_push_guard(self) -> None:
        with (
            patch(
                "tools.doit.github.subprocess.run",
                return_value=self._on_branch("feat/42-thing"),
            ),
            patch("tools.doit.github._check_branch_up_to_date"),
            patch("tools.doit.github._ensure_branch_pushed") as mock_push,
            patch("tools.doit.github._run_gh_with_retry", return_value=MagicMock(stdout="u\n")),
        ):
            _pr_action()(title="feat: x", body="## Description\nx", no_push=True)

        assert mock_push.call_args.args[2] is True

    def test_gh_failure_exits_nonzero(self) -> None:
        with (
            patch(
                "tools.doit.github.subprocess.run",
                return_value=self._on_branch("feat/42-thing"),
            ),
            patch("tools.doit.github._check_branch_up_to_date"),
            patch("tools.doit.github._ensure_branch_pushed"),
            patch(
                "tools.doit.github._run_gh_with_retry",
                side_effect=subprocess.CalledProcessError(1, ["gh"], stderr="denied"),
            ),
            pytest.raises(SystemExit) as exc,
        ):
            _pr_action()(title="feat: x", body="## Description\nx")

        assert exc.value.code == 1

    def test_missing_body_file_exits(self, tmp_path: Path) -> None:
        with (
            patch(
                "tools.doit.github.subprocess.run",
                return_value=self._on_branch("feat/42-thing"),
            ),
            patch("tools.doit.github._check_branch_up_to_date"),
            patch("tools.doit.github._ensure_branch_pushed"),
            pytest.raises(SystemExit) as exc,
        ):
            _pr_action()(title="feat: x", body_file=str(tmp_path / "absent.md"))

        assert exc.value.code == 1

    def test_base_is_forwarded_to_gh_and_the_up_to_date_check(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """`--base` opens the PR against the branch it builds on (#855)."""
        with (
            patch(
                "tools.doit.github.subprocess.run",
                return_value=self._on_branch("feat/2-upper"),
            ),
            patch("tools.doit.github._check_branch_up_to_date") as mock_check,
            patch("tools.doit.github._ensure_branch_pushed"),
            patch(
                "tools.doit.github._run_gh_with_retry",
                return_value=MagicMock(stdout="https://github.com/o/r/pull/8\n"),
            ) as mock_gh,
        ):
            _pr_action()(title="feat: x", body="## Description\nx", base="feat/1-lower")

        cmd = mock_gh.call_args.args[0]
        assert cmd[cmd.index("--base") + 1] == "feat/1-lower"
        assert mock_check.call_args.kwargs["base"] == "feat/1-lower"
        # doit pr_merge refuses the PR until it targets main, so say how to get there.
        assert "gh pr edit https://github.com/o/r/pull/8 --base main" in capsys.readouterr().out

    def test_without_base_the_pr_targets_main_as_before(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with (
            patch(
                "tools.doit.github.subprocess.run",
                return_value=self._on_branch("feat/42-thing"),
            ),
            patch("tools.doit.github._check_branch_up_to_date") as mock_check,
            patch("tools.doit.github._ensure_branch_pushed"),
            patch(
                "tools.doit.github._run_gh_with_retry", return_value=MagicMock(stdout="url\n")
            ) as mock_gh,
        ):
            _pr_action()(title="feat: x", body="## Description\nx")

        assert "--base" not in mock_gh.call_args.args[0]
        assert mock_check.call_args.kwargs["base"] == "main"
        assert "retarget" not in capsys.readouterr().out


class TestGetPrInfo:
    """``_get_pr_info`` — the fields `doit pr_merge` decides on."""

    def test_requests_the_base_branch(self, mock_subprocess: MagicMock) -> None:
        """The base-branch guard reads ``baseRefName``; without it, the guard never runs (#853)."""
        pr = {"number": 42, "baseRefName": "main"}
        mock_subprocess.register({("gh", "pr", "view"): {"stdout": json.dumps(pr)}})

        info = _get_pr_info("42", Console(file=io.StringIO(), width=200))

        cmd = mock_subprocess.call_args.args[0]
        assert "baseRefName" in cmd[cmd.index("--json") + 1].split(",")
        assert info == pr

    def test_requests_the_head_branch_and_whether_it_is_a_fork(
        self, mock_subprocess: MagicMock
    ) -> None:
        """`doit pr_merge` looks the branch up among the worktrees, unless a fork owns it (#863)."""
        mock_subprocess.register({("gh", "pr", "view"): {"stdout": "{}"}})

        _get_pr_info("42", Console(file=io.StringIO(), width=200))

        cmd = mock_subprocess.call_args.args[0]
        fields = cmd[cmd.index("--json") + 1].split(",")
        assert {"headRefName", "isCrossRepository"} <= set(fields)


class TestDelegationContext:
    """Tests for the ``delegation_context`` doit task and its helpers (#985).

    The host CLI runs this task before delegating a task to another agent, so the
    delegated prompt can read a file instead of shelling out to ``gh`` itself.
    """

    @staticmethod
    def _action() -> "Callable[..., None]":
        action = task_delegation_context()["actions"][0]
        return action  # type: ignore[no-any-return]

    @staticmethod
    def _console() -> Console:
        return Console(file=io.StringIO(), width=200)

    def test_missing_kind_exits(self, mock_subprocess: MagicMock) -> None:
        """No ``--kind`` → SystemExit(1), no gh calls."""
        with pytest.raises(SystemExit) as excinfo:
            self._action()(kind="", n="1", out="ctx")

        assert excinfo.value.code == 1
        mock_subprocess.assert_not_called()

    def test_invalid_kind_exits(self, mock_subprocess: MagicMock) -> None:
        """An unknown ``--kind`` value → SystemExit(1), no gh calls."""
        with pytest.raises(SystemExit) as excinfo:
            self._action()(kind="bogus", n="1", out="ctx")

        assert excinfo.value.code == 1
        mock_subprocess.assert_not_called()

    def test_missing_number_exits(self, mock_subprocess: MagicMock) -> None:
        """No ``--n`` → SystemExit(1), no gh calls."""
        with pytest.raises(SystemExit) as excinfo:
            self._action()(kind="issue", n="", out="ctx")

        assert excinfo.value.code == 1
        mock_subprocess.assert_not_called()

    def test_missing_out_exits(self, mock_subprocess: MagicMock) -> None:
        """No ``--out`` → SystemExit(1), no gh calls."""
        with pytest.raises(SystemExit) as excinfo:
            self._action()(kind="issue", n="1", out="")

        assert excinfo.value.code == 1
        mock_subprocess.assert_not_called()

    def test_issue_kind_writes_issue_and_comments_json(
        self, tmp_path: Path, mock_subprocess: MagicMock
    ) -> None:
        """``--kind=issue`` writes ``issue.json`` (sans comments) and ``comments.json``."""
        payload = {
            "number": 985,
            "title": "refactor: host fetches GitHub data",
            "body": "issue body",
            "labels": [{"name": "refactor"}],
            "assignees": [],
            "comments": [
                {
                    "author": {"login": "endavis"},
                    "body": "## Implementation Plan for #985",
                }
            ],
        }
        mock_subprocess.register({("gh", "issue", "view"): {"stdout": json.dumps(payload)}})
        out_dir = tmp_path / "ctx"

        self._action()(kind="issue", n="985", out=str(out_dir))

        issue_data = json.loads((out_dir / "issue.json").read_text(encoding="utf-8"))
        assert issue_data["number"] == 985
        assert issue_data["title"] == payload["title"]
        assert "comments" not in issue_data

        comments_data = json.loads((out_dir / "comments.json").read_text(encoding="utf-8"))
        assert comments_data["comments"][0]["body"] == "## Implementation Plan for #985"

        cmd = mock_subprocess.call_args.args[0]
        assert cmd[:4] == ["gh", "issue", "view", "985"]
        assert "comments" in cmd[cmd.index("--json") + 1].split(",")

    def test_issue_kind_missing_issue_errors_and_writes_nothing(
        self, tmp_path: Path, mock_subprocess: MagicMock
    ) -> None:
        """A nonexistent issue surfaces a clear error, not a silent empty file."""
        mock_subprocess.register(
            {
                ("gh", "issue", "view"): subprocess.CalledProcessError(
                    returncode=1,
                    cmd=["gh", "issue", "view"],
                    stderr="GraphQL: Could not resolve to an Issue",
                )
            }
        )
        out_dir = tmp_path / "ctx"

        with pytest.raises(SystemExit) as excinfo:
            self._action()(kind="issue", n="99999", out=str(out_dir))

        assert excinfo.value.code == 1
        assert not out_dir.exists()

    def test_pr_kind_writes_pr_json_and_diff(
        self, tmp_path: Path, mock_subprocess: MagicMock
    ) -> None:
        """``--kind=pr`` writes ``pr.json`` and the raw diff to ``diff.txt``."""
        payload = {
            "number": 42,
            "title": "feat: add export",
            "body": "pr body",
            "baseRefName": "main",
            "headRefName": "feat/42-export",
        }
        mock_subprocess.register(
            {
                ("gh", "pr", "view"): {"stdout": json.dumps(payload)},
                ("gh", "pr", "diff"): {"stdout": "diff --git a/x b/x\n+added\n"},
            }
        )
        out_dir = tmp_path / "ctx"

        self._action()(kind="pr", n="42", out=str(out_dir))

        pr_data = json.loads((out_dir / "pr.json").read_text(encoding="utf-8"))
        assert pr_data == payload
        assert (out_dir / "diff.txt").read_text(encoding="utf-8") == "diff --git a/x b/x\n+added\n"

        view_cmd = mock_subprocess.call_args_list[0].args[0]
        assert view_cmd == [
            "gh",
            "pr",
            "view",
            "42",
            "--json",
            "number,title,body,baseRefName,headRefName",
        ]
        assert mock_subprocess.call_args_list[1].args[0] == ["gh", "pr", "diff", "42"]

    def test_pr_kind_missing_pr_errors_and_writes_nothing(
        self, tmp_path: Path, mock_subprocess: MagicMock
    ) -> None:
        """A nonexistent PR surfaces a clear error, not a silent empty file."""
        mock_subprocess.register(
            {
                ("gh", "pr", "view"): subprocess.CalledProcessError(
                    returncode=1, cmd=["gh", "pr", "view"], stderr="no pull requests found"
                )
            }
        )
        out_dir = tmp_path / "ctx"

        with pytest.raises(SystemExit) as excinfo:
            self._action()(kind="pr", n="999", out=str(out_dir))

        assert excinfo.value.code == 1
        assert not out_dir.exists()

    def test_pr_kind_diff_failure_errors_and_writes_nothing(
        self, tmp_path: Path, mock_subprocess: MagicMock
    ) -> None:
        """A ``gh pr diff`` failure after a successful ``gh pr view`` still writes nothing."""
        payload = {
            "number": 42,
            "title": "feat: add export",
            "body": "pr body",
            "baseRefName": "main",
            "headRefName": "feat/42-export",
        }
        mock_subprocess.register(
            {
                ("gh", "pr", "view"): {"stdout": json.dumps(payload)},
                ("gh", "pr", "diff"): subprocess.CalledProcessError(
                    returncode=1, cmd=["gh", "pr", "diff"], stderr="boom"
                ),
            }
        )
        out_dir = tmp_path / "ctx"

        with pytest.raises(SystemExit) as excinfo:
            self._action()(kind="pr", n="42", out=str(out_dir))

        assert excinfo.value.code == 1
        assert not out_dir.exists()

    def test_creates_nested_output_directory(
        self, tmp_path: Path, mock_subprocess: MagicMock
    ) -> None:
        """A multi-level ``--out`` is created, matching ``tmp/agents/<host>/<task>-<n>/``."""
        mock_subprocess.register(
            {("gh", "issue", "view"): {"stdout": json.dumps({"number": 1, "comments": []})}}
        )
        out_dir = tmp_path / "agents" / "claude" / "multi-plan-1"

        self._action()(kind="issue", n="1", out=str(out_dir))

        assert out_dir.is_dir()
        assert (out_dir / "issue.json").exists()
        assert (out_dir / "comments.json").exists()

    def test_fetch_issue_context_helper_used_directly(
        self, tmp_path: Path, mock_subprocess: MagicMock
    ) -> None:
        """``_fetch_issue_context`` can be called directly (used by the task action)."""
        mock_subprocess.register(
            {("gh", "issue", "view"): {"stdout": json.dumps({"number": 7, "comments": []})}}
        )
        out_dir = tmp_path / "ctx"

        _fetch_issue_context("7", out_dir, self._console())

        assert json.loads((out_dir / "issue.json").read_text(encoding="utf-8"))["number"] == 7

    def test_fetch_pr_context_helper_used_directly(
        self, tmp_path: Path, mock_subprocess: MagicMock
    ) -> None:
        """``_fetch_pr_context`` can be called directly (used by the task action)."""
        mock_subprocess.register(
            {
                ("gh", "pr", "view"): {"stdout": json.dumps({"number": 7})},
                ("gh", "pr", "diff"): {"stdout": "diff\n"},
            }
        )
        out_dir = tmp_path / "ctx"

        _fetch_pr_context("7", out_dir, self._console())

        assert json.loads((out_dir / "pr.json").read_text(encoding="utf-8"))["number"] == 7
        assert (out_dir / "diff.txt").read_text(encoding="utf-8") == "diff\n"


class TestGetDefaultBranch:
    """``_get_default_branch`` — the only base `doit pr_merge` merges into (#853)."""

    @staticmethod
    def _make_console() -> Console:
        return Console(file=io.StringIO(), width=200)

    def test_returns_the_repository_default_branch(self, mock_subprocess: MagicMock) -> None:
        mock_subprocess.register({("gh", "repo", "view"): {"stdout": "trunk\n"}})

        assert _get_default_branch(self._make_console()) == "trunk"
        cmd = mock_subprocess.call_args.args[0]
        assert cmd[cmd.index("--json") + 1] == "defaultBranchRef"

    def test_falls_back_to_main_with_a_warning(self, mock_subprocess: MagicMock) -> None:
        """A lookup failure is reported, not swallowed."""
        console = self._make_console()
        mock_subprocess.register(
            {
                ("gh", "repo", "view"): subprocess.CalledProcessError(
                    1, ["gh"], stderr="HTTP 404: Not Found"
                )
            }
        )

        assert _get_default_branch(console) == "main"
        output = console.file.getvalue()  # type: ignore[attr-defined]
        assert "HTTP 404" in output
        assert "Assuming 'main'" in output


@pytest.fixture(autouse=True)
def _no_real_branch_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep every test away from a real `git pull` (#891).

    `doit pr_merge` fast-forwards the checkout it starts on when that is the PR's
    base. Unless a test says otherwise, the checkout is on no branch.
    """
    monkeypatch.setattr(github_mod, "_current_branch", lambda: None)


def _merge_action() -> Callable[..., None]:
    """Return the `merge_pr` action that `doit pr_merge` runs."""
    action: Callable[..., None] = task_pr_merge()["actions"][0]
    return action


_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _plain(text: str) -> str:
    """Remove ANSI color codes, which split substrings such as `[x]` when FORCE_COLOR is set."""
    return _ANSI.sub("", text)


class TestMergePr:
    """`doit pr_merge` — the mandated path that mutates remote state (#708).

    A defect here is the most expensive of the three: it lands, or fails to
    land, a squash commit on `main`.
    """

    @staticmethod
    def _pr(**overrides: object) -> dict[str, object]:
        info: dict[str, object] = {
            "number": 42,
            "title": "feat: add a thing",
            "body": "## Description\nx\n\nAddresses #7",
            "state": "OPEN",
        }
        info.update(overrides)
        return info

    def test_merges_with_a_conventional_squash_subject(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with (
            patch("tools.doit.github._get_pr_info", return_value=self._pr()),
            patch("tools.doit.github._run_gh_with_retry") as mock_gh,
        ):
            _merge_action()(pr="42")

        cmd = mock_gh.call_args.args[0]
        assert cmd[:5] == ["gh", "pr", "merge", "42", "--squash"]
        subject = cmd[cmd.index("--subject") + 1]
        assert "merges PR #42" in subject and "addresses #7" in subject
        assert "merged successfully" in capsys.readouterr().out

    def test_fast_forwards_the_base_it_was_run_from(self) -> None:
        """gh pulls the base only when it switches to it, so the task does it here (#891)."""
        with (
            patch("tools.doit.github._get_pr_info", return_value=self._pr(baseRefName="main")),
            patch("tools.doit.github._get_default_branch", return_value="main"),
            patch("tools.doit.github._current_branch", return_value="main"),
            patch("tools.doit.github._run_gh_with_retry"),
            patch("tools.doit.github._fast_forward_base") as mock_ff,
        ):
            _merge_action()(pr="42")

        assert mock_ff.call_args.args[0] == "main"

    def test_leaves_the_base_to_gh_when_run_from_the_prs_branch(self) -> None:
        """gh's --delete-branch switches to the base and pulls it itself."""
        with (
            patch("tools.doit.github._get_pr_info", return_value=self._pr(baseRefName="main")),
            patch("tools.doit.github._get_default_branch", return_value="main"),
            patch("tools.doit.github._current_branch", return_value="feat/1-x"),
            patch("tools.doit.github._run_gh_with_retry"),
            patch("tools.doit.github._fast_forward_base") as mock_ff,
        ):
            _merge_action()(pr="42")

        mock_ff.assert_not_called()

    def test_a_failed_merge_pulls_nothing(self) -> None:
        with (
            patch("tools.doit.github._get_pr_info", return_value=self._pr(baseRefName="main")),
            patch("tools.doit.github._get_default_branch", return_value="main"),
            patch("tools.doit.github._current_branch", return_value="main"),
            patch(
                "tools.doit.github._run_gh_with_retry",
                side_effect=subprocess.CalledProcessError(1, ["gh"], stderr="not mergeable"),
            ),
            patch("tools.doit.github._fast_forward_base") as mock_ff,
            pytest.raises(SystemExit),
        ):
            _merge_action()(pr="42")

        mock_ff.assert_not_called()

    def test_missing_pr_info_exits(self) -> None:
        with (
            patch("tools.doit.github._get_pr_info", return_value=None),
            pytest.raises(SystemExit) as exc,
        ):
            _merge_action()(pr="42")

        assert exc.value.code == 1

    @pytest.mark.parametrize("state", ["MERGED", "CLOSED", "DRAFT"])
    def test_refuses_a_pr_that_is_not_open(self, state: str) -> None:
        """Re-merging a merged PR, or merging a closed one, must not proceed."""
        with (
            patch("tools.doit.github._get_pr_info", return_value=self._pr(state=state)),
            patch("tools.doit.github._run_gh_with_retry") as mock_gh,
            pytest.raises(SystemExit) as exc,
        ):
            _merge_action()(pr="42")

        assert exc.value.code == 1
        mock_gh.assert_not_called()

    def test_refuses_a_non_conventional_title(self, capsys: pytest.CaptureFixture[str]) -> None:
        """The squash subject becomes a commit on main, so the format is enforced."""
        with (
            patch(
                "tools.doit.github._get_pr_info",
                return_value=self._pr(title="added some stuff"),
            ),
            patch("tools.doit.github._run_gh_with_retry") as mock_gh,
            pytest.raises(SystemExit) as exc,
        ):
            _merge_action()(pr="42")

        assert exc.value.code == 1
        mock_gh.assert_not_called()
        assert "conventional commit format" in capsys.readouterr().out

    def test_warns_when_no_issue_is_linked(self, capsys: pytest.CaptureFixture[str]) -> None:
        """A warning, not a refusal — some PRs legitimately link nothing."""
        with (
            patch(
                "tools.doit.github._get_pr_info",
                return_value=self._pr(body="## Description\nno link here"),
            ),
            patch("tools.doit.github._run_gh_with_retry"),
        ):
            _merge_action()(pr="42")

        assert "No linked issues" in capsys.readouterr().out

    def test_delete_branch_is_opt_out(self) -> None:
        with (
            patch("tools.doit.github._get_pr_info", return_value=self._pr()),
            patch("tools.doit.github._run_gh_with_retry") as mock_gh,
        ):
            _merge_action()(pr="42", delete_branch=False)

        assert "--delete-branch" not in mock_gh.call_args.args[0]

    def test_auto_close_closes_linked_issues(self) -> None:
        """`--auto-close` is what AGENTS.md offers instead of a manual close."""
        with (
            patch("tools.doit.github._get_pr_info", return_value=self._pr()),
            patch("tools.doit.github._run_gh_with_retry"),
            patch("tools.doit.github._close_linked_issues") as mock_close,
        ):
            _merge_action()(pr="42", auto_close=True)

        assert mock_close.call_args.args[0] == ["7"]

    def test_without_auto_close_it_reminds_instead(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with (
            patch("tools.doit.github._get_pr_info", return_value=self._pr()),
            patch("tools.doit.github._run_gh_with_retry"),
            patch("tools.doit.github._close_linked_issues") as mock_close,
        ):
            _merge_action()(pr="42")

        mock_close.assert_not_called()
        assert "Reminder: Update linked issues" in capsys.readouterr().out

    def test_merge_failure_exits_nonzero(self) -> None:
        with (
            patch("tools.doit.github._get_pr_info", return_value=self._pr()),
            patch(
                "tools.doit.github._run_gh_with_retry",
                side_effect=subprocess.CalledProcessError(1, ["gh"], stderr="not mergeable"),
            ),
            pytest.raises(SystemExit) as exc,
        ):
            _merge_action()(pr="42")

        assert exc.value.code == 1

    @pytest.mark.parametrize(
        ("base", "default"),
        [
            ("feat/1-lower", "main"),  # built on an unmerged branch
            ("main", "trunk"),  # the default branch is not always main
        ],
    )
    def test_refuses_a_pr_whose_base_is_not_the_default_branch(
        self, base: str, default: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """GitHub merges into the base, so this would land beside `main`, not on it (#853).

        Nothing is merged, and no issue is closed although `--auto-close` asks for it.
        """
        with (
            patch("tools.doit.github._get_pr_info", return_value=self._pr(baseRefName=base)),
            patch("tools.doit.github._get_default_branch", return_value=default),
            patch("tools.doit.github._run_gh_with_retry") as mock_gh,
            patch("tools.doit.github._close_linked_issues") as mock_close,
            pytest.raises(SystemExit) as exc,
        ):
            _merge_action()(pr="42", auto_close=True)

        assert exc.value.code == 1
        mock_gh.assert_not_called()
        mock_close.assert_not_called()
        out = capsys.readouterr().out
        assert f"targets '{base}'" in out
        assert f"gh pr edit 42 --base {default}" in out

    @pytest.mark.parametrize("branch", ["main", "trunk"])
    def test_merges_a_pr_that_targets_the_default_branch(self, branch: str) -> None:
        with (
            patch("tools.doit.github._get_pr_info", return_value=self._pr(baseRefName=branch)),
            patch("tools.doit.github._get_default_branch", return_value=branch),
            patch("tools.doit.github._run_gh_with_retry") as mock_gh,
        ):
            _merge_action()(pr="42")

        assert mock_gh.call_args.args[0][:4] == ["gh", "pr", "merge", "42"]

    def test_explains_a_stacked_pr_refusal(self, capsys: pytest.CaptureFixture[str]) -> None:
        """GitHub's refusal for a PR in a native stack, as observed on #850 (#853)."""
        stderr = (
            "GraphQL: This pull request is part of a stack and must be merged using the "
            "asynchronous merge REST API. (mergePullRequest)"
        )
        with (
            patch("tools.doit.github._get_pr_info", return_value=self._pr(baseRefName="main")),
            patch("tools.doit.github._get_default_branch", return_value="main"),
            patch(
                "tools.doit.github._run_gh_with_retry",
                side_effect=subprocess.CalledProcessError(1, ["gh"], stderr=stderr),
            ),
            pytest.raises(SystemExit) as exc,
        ):
            _merge_action()(pr="42")

        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "does not support" in out
        assert "gh stack unstack" in out

    def test_other_merge_failures_get_no_stack_explanation(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with (
            patch("tools.doit.github._get_pr_info", return_value=self._pr()),
            patch(
                "tools.doit.github._run_gh_with_retry",
                side_effect=subprocess.CalledProcessError(1, ["gh"], stderr="not mergeable"),
            ),
            pytest.raises(SystemExit),
        ):
            _merge_action()(pr="42")

        assert "stack" not in capsys.readouterr().out

    @pytest.mark.parametrize("title", ["fix: read [tool.x]", r"fix: :bug: C:\x\[1]"])
    def test_prints_a_bracketed_title_verbatim(
        self, capsys: pytest.CaptureFixture[str], title: str
    ) -> None:
        """Rich read `[tool.x]` as a markup tag and dropped it from every line (#893).

        Escaped, it still lost the backslash before `[1]` and turned `:bug:` into an emoji (#914).
        """
        with (
            patch("tools.doit.github._get_pr_info", return_value=self._pr(title=title)),
            patch("tools.doit.github._run_gh_with_retry"),
        ):
            _merge_action()(pr="42")

        out = _plain(capsys.readouterr().out)
        assert f"PR #42: {title}" in out
        assert f"  {title} (merges PR #42, addresses #7)" in out
        assert f"Commit: {title} (merges PR #42, addresses #7)" in out

    def test_a_closing_tag_in_the_title_does_not_stop_the_merge(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """`[/tmp]` raised MarkupError on the first print, before `gh pr merge` ran (#893)."""
        with (
            patch(
                "tools.doit.github._get_pr_info",
                return_value=self._pr(title="fix: strip [/tmp] prefix"),
            ),
            patch("tools.doit.github._run_gh_with_retry") as mock_gh,
        ):
            _merge_action()(pr="42")

        mock_gh.assert_called_once()
        assert "PR #42: fix: strip [/tmp] prefix" in _plain(capsys.readouterr().out)

    @pytest.mark.parametrize(
        "stderr", ["refusing [/x]: not mergeable", r"refusing C:\x\[1]: :x: not mergeable"]
    )
    def test_prints_gh_stderr_verbatim(
        self, capsys: pytest.CaptureFixture[str], stderr: str
    ) -> None:
        """gh's error text is printed as text, not parsed as markup (#893).

        Escaped, it still lost the backslash before `[1]` and turned `:x:` into an emoji (#914).
        """
        with (
            patch("tools.doit.github._get_pr_info", return_value=self._pr()),
            patch(
                "tools.doit.github._run_gh_with_retry",
                side_effect=subprocess.CalledProcessError(1, ["gh"], stderr=stderr),
            ),
            pytest.raises(SystemExit) as exc,
        ):
            _merge_action()(pr="42")

        assert exc.value.code == 1
        assert stderr in _plain(capsys.readouterr().out)


class TestMergePrWithWorktree:
    """`doit pr_merge` for a PR whose branch a linked worktree has checked out (#863).

    gh's `--delete-branch` would check out `main` in that worktree, which git
    refuses while `main` is checked out anywhere else, so the task deletes the
    branch itself after the merge.
    """

    WORKTREE = Path("/src/project/worktrees/feat/1-x")

    @staticmethod
    def _pr(**overrides: object) -> dict[str, object]:
        info: dict[str, object] = {
            "number": 42,
            "title": "feat: add a thing",
            "body": "## Description\nx\n\nAddresses #7",
            "state": "OPEN",
            "headRefName": "feat/1-x",
            "isCrossRepository": False,
        }
        info.update(overrides)
        return info

    def test_leaves_the_branch_to_the_task(self) -> None:
        with (
            patch("tools.doit.github._get_pr_info", return_value=self._pr()),
            patch("tools.doit.github.worktree_for_branch", return_value=self.WORKTREE) as mock_find,
            patch("tools.doit.github._run_gh_with_retry") as mock_gh,
            patch("tools.doit.github._finish_branch_in_worktree") as mock_finish,
        ):
            _merge_action()(pr="42")

        mock_find.assert_called_once_with("feat/1-x")
        assert "--delete-branch" not in mock_gh.call_args.args[0]
        assert mock_finish.call_args.args[:3] == (42, "feat/1-x", self.WORKTREE)

    def test_a_branch_no_worktree_holds_is_left_to_gh(self) -> None:
        with (
            patch("tools.doit.github._get_pr_info", return_value=self._pr()),
            patch("tools.doit.github.worktree_for_branch", return_value=None),
            patch("tools.doit.github._run_gh_with_retry") as mock_gh,
            patch("tools.doit.github._finish_branch_in_worktree") as mock_finish,
        ):
            _merge_action()(pr="42")

        assert "--delete-branch" in mock_gh.call_args.args[0]
        mock_finish.assert_not_called()

    def test_a_fork_branch_is_never_looked_up(self) -> None:
        """A fork's branch name can match an unrelated local branch."""
        with (
            patch(
                "tools.doit.github._get_pr_info",
                return_value=self._pr(isCrossRepository=True),
            ),
            patch("tools.doit.github.worktree_for_branch") as mock_find,
            patch("tools.doit.github._run_gh_with_retry") as mock_gh,
        ):
            _merge_action()(pr="42")

        mock_find.assert_not_called()
        assert "--delete-branch" in mock_gh.call_args.args[0]

    def test_keeping_the_branch_keeps_the_worktree(self) -> None:
        with (
            patch("tools.doit.github._get_pr_info", return_value=self._pr()),
            patch("tools.doit.github.worktree_for_branch") as mock_find,
            patch("tools.doit.github._run_gh_with_retry"),
            patch("tools.doit.github._finish_branch_in_worktree") as mock_finish,
        ):
            _merge_action()(pr="42", delete_branch=False)

        mock_find.assert_not_called()
        mock_finish.assert_not_called()

    def test_a_cleanup_failure_is_not_a_failed_merge(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The PR has merged, so the issues still close and the task still succeeds."""
        with (
            patch("tools.doit.github._get_pr_info", return_value=self._pr()),
            patch("tools.doit.github.worktree_for_branch", return_value=self.WORKTREE),
            patch("tools.doit.github._run_gh_with_retry"),
            patch("tools.doit.github._close_linked_issues") as mock_close,
            patch("tools.doit.github._merged_head", return_value="abc123"),
            patch("tools.doit.github._delete_remote_branch"),
            patch(
                "tools.doit.github.remove_merged_worktree",
                side_effect=subprocess.CalledProcessError(1, ["git"], stderr="disk full"),
            ),
        ):
            _merge_action()(pr="42", auto_close=True)

        mock_close.assert_called_once()
        out = capsys.readouterr().out
        assert "merged successfully" in out
        assert "Cleanup after the merge failed: disk full" in out
        assert "Failed to merge PR" not in out

    def test_fast_forwards_main_after_removing_the_worktree(self) -> None:
        """Merged from the main checkout on `main`, which gh neither switches nor pulls (#891)."""
        steps: list[str] = []
        with (
            patch("tools.doit.github._get_pr_info", return_value=self._pr(baseRefName="main")),
            patch("tools.doit.github._get_default_branch", return_value="main"),
            patch("tools.doit.github.worktree_for_branch", return_value=self.WORKTREE),
            patch("tools.doit.github._current_branch", return_value="main"),
            patch("tools.doit.github._run_gh_with_retry"),
            patch(
                "tools.doit.github._finish_branch_in_worktree",
                side_effect=lambda *_: steps.append("remove worktree"),
            ),
            patch(
                "tools.doit.github._fast_forward_base",
                side_effect=lambda *_: steps.append("fast-forward main"),
            ),
        ):
            _merge_action()(pr="42")

        assert steps == ["remove worktree", "fast-forward main"]


class TestWorktreeHolding:
    def test_a_git_failure_leaves_the_branch_to_gh(self) -> None:
        with patch(
            "tools.doit.github.worktree_for_branch",
            side_effect=subprocess.CalledProcessError(128, ["git"], stderr="not a git repository"),
        ):
            assert _worktree_holding({"headRefName": "feat/1-x"}) is None

    def test_a_pr_without_a_head_branch_is_not_looked_up(self) -> None:
        with patch("tools.doit.github.worktree_for_branch") as mock_find:
            assert _worktree_holding({}) is None

        mock_find.assert_not_called()


class TestFinishBranchInWorktree:
    """After the merge: the branch on GitHub, then the worktree and local branch (#863)."""

    WORKTREE = Path("/src/project/worktrees/feat/1-x")

    @staticmethod
    def _console() -> Console:
        return Console(file=io.StringIO(), width=200)

    def test_an_unmerged_pr_deletes_nothing(self) -> None:
        console = self._console()
        with (
            patch("tools.doit.github._merged_head", return_value=None),
            patch("tools.doit.github._delete_remote_branch") as mock_remote,
            patch("tools.doit.github.remove_merged_worktree") as mock_local,
        ):
            _finish_branch_in_worktree(42, "feat/1-x", self.WORKTREE, console)

        mock_remote.assert_not_called()
        mock_local.assert_not_called()
        assert "in place" in console.file.getvalue()  # type: ignore[attr-defined]

    @pytest.mark.parametrize("name", ["[x]", "[/x]", r"x\[1]", ":memo:"])
    def test_an_unmerged_pr_prints_the_worktree_path_verbatim(self, name: str) -> None:
        """The path is text, not markup (#920)."""
        worktree = self.WORKTREE.parent / name
        console = self._console()
        with patch("tools.doit.github._merged_head", return_value=None):
            _finish_branch_in_worktree(42, "feat/1-x", worktree, console)

        out = _plain(console.file.getvalue())  # type: ignore[attr-defined]
        assert f"Left feat/1-x and its worktree {worktree} in place." in out

    def test_a_merged_pr_deletes_its_branch_everywhere(self) -> None:
        console = self._console()
        with (
            patch("tools.doit.github._merged_head", return_value="abc123"),
            patch("tools.doit.github._delete_remote_branch") as mock_remote,
            patch("tools.doit.github.remove_merged_worktree") as mock_local,
        ):
            _finish_branch_in_worktree(42, "feat/1-x", self.WORKTREE, console)

        mock_remote.assert_called_once_with("feat/1-x", console)
        mock_local.assert_called_once_with(self.WORKTREE, "feat/1-x", "abc123", console)

    def test_an_os_error_is_reported_not_raised(self) -> None:
        console = self._console()
        with (
            patch("tools.doit.github._merged_head", return_value="abc123"),
            patch("tools.doit.github._delete_remote_branch"),
            patch(
                "tools.doit.github.remove_merged_worktree",
                side_effect=OSError("Permission denied"),
            ),
        ):
            _finish_branch_in_worktree(42, "feat/1-x", self.WORKTREE, console)

        assert "Permission denied" in console.file.getvalue()  # type: ignore[attr-defined]


class TestOpenEditorWithTemplate:
    """The issue and PR editor."""

    @pytest.mark.parametrize(
        "editor", ["/opt/[x]/vi", "/opt/[/x]/vi", r"C:\tools\[1]\vi.exe", "/opt/:memo:/vi"]
    )
    def test_prints_the_editor_verbatim(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], editor: str
    ) -> None:
        """`$EDITOR` is the user's text, not markup (#920). It fails here, so nothing is read."""
        monkeypatch.setenv("COLUMNS", "1000")
        with (
            patch("tools.doit.github._get_editor", return_value=editor),
            patch("tools.doit.github.subprocess.run", return_value=MagicMock(returncode=1)),
        ):
            assert _open_editor_with_template("body") is None

        assert f"Opening {editor}..." in _plain(capsys.readouterr().out).splitlines()


class TestCurrentBranch:
    def test_returns_the_checked_out_branch(self, mock_subprocess: MagicMock) -> None:
        mock_subprocess.register({("git", "branch", "--show-current"): {"stdout": "main\n"}})

        assert _current_branch() == "main"

    def test_a_detached_head_is_no_branch(self, mock_subprocess: MagicMock) -> None:
        mock_subprocess.register({("git", "branch", "--show-current"): {"stdout": "\n"}})

        assert _current_branch() is None

    def test_a_git_failure_is_no_branch(self, mock_subprocess: MagicMock) -> None:
        mock_subprocess.register(
            {
                ("git", "branch", "--show-current"): subprocess.CalledProcessError(
                    128, ["git"], stderr="fatal: not a git repository"
                )
            }
        )

        assert _current_branch() is None


class TestFastForwardBase:
    """After the merge: the checkout the task ran from, when that is the PR's base (#891)."""

    @staticmethod
    def _console() -> Console:
        return Console(file=io.StringIO(), width=200, color_system=None)

    def test_pulls_the_base_fast_forward_only(self, mock_subprocess: MagicMock) -> None:
        console = self._console()
        mock_subprocess.register({("git", "pull"): {"stdout": ""}})

        _fast_forward_base("main", console)

        assert mock_subprocess.call_args.args[0] == ["git", "pull", "--ff-only", "origin", "main"]
        assert "Fast-forwarded main" in console.file.getvalue()  # type: ignore[attr-defined]

    def test_a_failed_pull_is_reported_not_raised(self, mock_subprocess: MagicMock) -> None:
        """The PR has merged, so a pull that cannot fast-forward only warns."""
        console = self._console()
        mock_subprocess.register(
            {
                ("git", "pull"): subprocess.CalledProcessError(
                    128, ["git"], stderr="fatal: Not possible to fast-forward, aborting."
                )
            }
        )

        _fast_forward_base("main", console)

        out = console.file.getvalue()  # type: ignore[attr-defined]
        assert "git pull --ff-only origin main" in out
        assert "Not possible to fast-forward" in out


class TestMergedHead:
    @staticmethod
    def _console() -> Console:
        return Console(file=io.StringIO(), width=200)

    def test_returns_the_head_the_pr_merged(self, mock_subprocess: MagicMock) -> None:
        pr = {"state": "MERGED", "headRefOid": "abc123"}
        mock_subprocess.register({("gh", "pr", "view"): {"stdout": json.dumps(pr)}})

        assert _merged_head(42, self._console()) == "abc123"
        assert mock_subprocess.call_args.args[0] == [
            "gh",
            "pr",
            "view",
            "42",
            "--json",
            "state,headRefOid",
        ]

    @pytest.mark.parametrize("state", ["OPEN", "CLOSED"])
    def test_an_unmerged_pr_returns_none(self, mock_subprocess: MagicMock, state: str) -> None:
        console = self._console()
        pr = {"state": state, "headRefOid": "abc123"}
        mock_subprocess.register({("gh", "pr", "view"): {"stdout": json.dumps(pr)}})

        assert _merged_head(42, console) is None
        assert f"is {state}, not merged" in console.file.getvalue()  # type: ignore[attr-defined]

    def test_a_lookup_failure_returns_none(self, mock_subprocess: MagicMock) -> None:
        console = self._console()
        mock_subprocess.register(
            {
                ("gh", "pr", "view"): subprocess.CalledProcessError(
                    1, ["gh"], stderr="GraphQL: Could not resolve to a PullRequest"
                )
            }
        )

        assert _merged_head(42, console) is None
        assert "Could not resolve" in console.file.getvalue()  # type: ignore[attr-defined]


class TestDeleteRemoteBranch:
    """What `gh pr merge --delete-branch` would have done on GitHub (#863)."""

    SETTING = ("gh", "repo", "view")

    @staticmethod
    def _console() -> Console:
        return Console(file=io.StringIO(), width=200)

    @staticmethod
    def _api_calls(mock_subprocess: MagicMock) -> list[list[str]]:
        calls = [call.args[0] for call in mock_subprocess.call_args_list]
        return [cmd for cmd in calls if cmd[:2] == ["gh", "api"]]

    def test_left_to_github_when_the_repository_deletes_head_branches(
        self, mock_subprocess: MagicMock
    ) -> None:
        mock_subprocess.register({self.SETTING: {"stdout": "true\n"}})

        _delete_remote_branch("feat/1-x", self._console())

        assert self._api_calls(mock_subprocess) == []

    def test_deletes_the_branch_through_the_api_otherwise(self, mock_subprocess: MagicMock) -> None:
        console = self._console()
        mock_subprocess.register({self.SETTING: {"stdout": "false\n"}, ("gh", "api"): {}})

        _delete_remote_branch("feat/1-x", console)

        assert self._api_calls(mock_subprocess) == [
            ["gh", "api", "--method", "DELETE", "repos/{owner}/{repo}/git/refs/heads/feat/1-x"]
        ]
        assert "Deleted branch feat/1-x on GitHub" in console.file.getvalue()  # type: ignore[attr-defined]

    def test_a_setting_lookup_failure_still_deletes(self, mock_subprocess: MagicMock) -> None:
        mock_subprocess.register(
            {
                self.SETTING: subprocess.CalledProcessError(1, ["gh"], stderr="GraphQL: denied"),
                ("gh", "api"): {},
            }
        )

        _delete_remote_branch("feat/1-x", self._console())

        assert len(self._api_calls(mock_subprocess)) == 1

    def test_quotes_a_name_that_would_cut_the_endpoint_short(
        self, mock_subprocess: MagicMock
    ) -> None:
        """Unquoted, `feat/1-x#y` would delete `feat/1-x`: the rest reads as a URL fragment."""
        mock_subprocess.register({self.SETTING: {"stdout": "false\n"}, ("gh", "api"): {}})

        _delete_remote_branch("feat/1-x#y", self._console())

        endpoint = self._api_calls(mock_subprocess)[0][-1]
        assert endpoint.endswith("/git/refs/heads/feat/1-x%23y")

    def test_a_failed_delete_is_reported(self, mock_subprocess: MagicMock) -> None:
        console = self._console()
        mock_subprocess.register(
            {
                self.SETTING: {"stdout": "false\n"},
                ("gh", "api"): subprocess.CalledProcessError(
                    1, ["gh"], stderr="gh: Reference does not exist (HTTP 422)"
                ),
            }
        )

        _delete_remote_branch("feat/1-x", console)

        assert "Reference does not exist" in console.file.getvalue()  # type: ignore[attr-defined]

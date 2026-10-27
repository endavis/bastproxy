"""Tests for tools/doit/git.py task wiring.

Verifies that ``task_commit``, ``task_bump``, and ``task_changelog`` gate
their ``cz`` invocations on ``uv pip show commitizen`` (via
``install_check_or_skip``) so real failures — pre-commit hook rejections,
tag/version bump failures, changelog generation failures — propagate
instead of being swallowed by the legacy ``|| echo 'not installed'`` pattern.

Addresses issue #527. ``TestWorktree`` covers ``doit worktree`` (#854).
``TestWorktreeForBranch`` and ``TestRemoveMergedWorktree`` cover how
``doit pr_merge`` finds and removes a merged PR's worktree (#863).
"""

from __future__ import annotations

import io
import os
import re
import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from rich.console import Console

from tools.doit.git import (
    _main_checkout,
    remove_merged_worktree,
    task_bump,
    task_changelog,
    task_commit,
    task_pre_commit_install,
    task_worktree,
    worktree_for_branch,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

# FORCE_COLOR makes Rich color captured output, and the codes split substrings such as `[x]`.
_ANSI = re.compile(r"\x1b\[[0-9;]*m")

# Directory names Rich mangled as markup (#920): it dropped `[x]`, crashed on `[/x]`, dropped the
# backslash before `[1]` and turned `:memo:` into an emoji. Windows refuses `:` in a file name.
_PATH_NAMES = [
    "[x]",
    "[/x]",
    r"x\[1]",
    pytest.param(
        ":memo:", marks=pytest.mark.skipif(os.name == "nt", reason="Windows refuses : in a name")
    ),
]


class TestGitTaskGates:
    """Each git task gates ``cz`` via ``uv pip show commitizen``.

    The package name is ``commitizen`` (CLI is ``cz``). All three tasks
    share the same gating package; the underlying ``cz`` subcommand differs.
    """

    def test_commit_gates_on_commitizen_package(self) -> None:
        action = task_commit()["actions"][0]
        assert isinstance(action, str)
        assert "uv pip show commitizen" in action
        assert "commitizen not installed. Run: doit install_dev" in action
        assert "uv run cz commit" in action
        # Bug-fix invariant: the bare-swallow pattern must be gone.
        assert "|| echo 'commitizen not installed" not in action

    def test_bump_gates_on_commitizen_package(self) -> None:
        action = task_bump()["actions"][0]
        assert isinstance(action, str)
        assert "uv pip show commitizen" in action
        assert "commitizen not installed. Run: doit install_dev" in action
        assert "uv run cz bump" in action
        assert "|| echo 'commitizen not installed" not in action

    def test_changelog_gates_on_commitizen_package(self) -> None:
        action = task_changelog()["actions"][0]
        assert isinstance(action, str)
        assert "uv pip show commitizen" in action
        assert "commitizen not installed. Run: doit install_dev" in action
        assert "uv run cz changelog" in action
        assert "|| echo 'commitizen not installed" not in action


class TestPreCommitInstall:
    """`pre_commit_install` and the config must agree on the hook set (#749 D1).

    The task installs whatever `default_install_hook_types` declares. That is the
    right design — one source for the set — but it couples two files silently:
    remove the declaration and the task keeps passing while `commit-msg` stops
    being installed, which is the #741 failure exactly. These tests hold the two
    together.
    """

    @staticmethod
    def _declared_hook_types() -> list[str]:
        config = yaml.safe_load((REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
        return list(config.get("default_install_hook_types") or [])

    def test_task_delegates_the_hook_set_to_the_config(self) -> None:
        """A single bare install, so the config decides which types are installed."""
        actions = task_pre_commit_install()["actions"]
        assert actions == ["uv run pre-commit install"], (
            "Enumerating --hook-type here re-creates the bug this fixed: the list "
            "drifts from `default_install_hook_types` and describes a hook set that "
            "is no longer the hook set."
        )

    def test_config_declares_the_hook_types_the_task_relies_on(self) -> None:
        """The bare install is only sufficient while the config declares the set."""
        declared = self._declared_hook_types()
        assert declared, (
            "`default_install_hook_types` is gone from .pre-commit-config.yaml, so "
            "`pre-commit install` now installs only `pre-commit` and every other hook "
            "type stops running. Restore it, or make the task enumerate the set again."
        )

    def test_commit_msg_is_among_them(self) -> None:
        """`commit-msg` carries conventional commits and the branch/issue check."""
        assert "commit-msg" in self._declared_hook_types(), (
            "Without `commit-msg`, neither conventional-commit validation nor the "
            "commit/branch issue check runs -- silently, because a hook that was "
            "never installed cannot fail (#741)."
        )


def _fake_git(
    fail: dict[str, subprocess.CalledProcessError] | None = None, valid_name: bool = True
) -> Callable[..., MagicMock]:
    """Stand in for ``subprocess.run``; *fail* maps a git subcommand to the error it raises."""

    def run(cmd: list[str], **_kwargs: object) -> MagicMock:
        if fail and cmd[1] in fail:
            raise fail[cmd[1]]
        ok = valid_name or cmd[1] != "check-ref-format"
        return MagicMock(returncode=0 if ok else 1, stdout="", stderr="")

    return run


class TestWorktree:
    """`doit worktree` — a checkout with its own environment (#854)."""

    BRANCH = "feat/42-add-export"

    @pytest.fixture
    def mocks(self, tmp_path: Path) -> Iterator[tuple[MagicMock, MagicMock]]:
        """Patch git (``subprocess.run``) and ``uv sync`` (``run_streamed``)."""
        with (
            patch("tools.doit.git._main_checkout", return_value=tmp_path),
            patch("tools.doit.git.subprocess.run", side_effect=_fake_git()) as mock_run,
            patch("tools.doit.git.run_streamed") as mock_sync,
        ):
            yield mock_run, mock_sync

    @staticmethod
    def _create(branch: str | None) -> None:
        action: Callable[..., None] = task_worktree()["actions"][0]
        action(branch=branch)

    @staticmethod
    def _cmds(mock_run: MagicMock) -> list[list[str]]:
        return [call.args[0] for call in mock_run.call_args_list]

    def test_branches_from_a_fresh_origin_main_without_tracking(
        self, mocks: tuple[MagicMock, MagicMock], tmp_path: Path
    ) -> None:
        """No upstream, so `doit pr` pushes the branch rather than trusting origin/main."""
        mock_run, _ = mocks
        self._create(self.BRANCH)

        cmds = self._cmds(mock_run)
        fetch = ["git", "fetch", "origin", "main"]
        path = str(tmp_path / "worktrees" / self.BRANCH)
        add = ["git", "worktree", "add", "--no-track", "-b", self.BRANCH, path, "origin/main"]
        assert cmds.index(fetch) < cmds.index(add)

    def test_syncs_its_own_environment_without_virtual_env(
        self,
        mocks: tuple[MagicMock, MagicMock],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """An inherited VIRTUAL_ENV names the main checkout's .venv; the sync must not see it."""
        _, mock_sync = mocks
        # Absolute on every OS. "/shared/uv-cache" has no drive, so on Windows it
        # is not absolute and is rightly resolved against the current drive.
        cache = tmp_path / "uv-cache"
        monkeypatch.setenv("VIRTUAL_ENV", "/main/.venv")
        monkeypatch.setenv("UV_CACHE_DIR", str(cache))
        self._create(self.BRANCH)

        mock_sync.assert_called_once()
        assert mock_sync.call_args.args[0] == ["uv", "sync", "--all-extras", "--dev"]
        assert mock_sync.call_args.kwargs["cwd"] == tmp_path / "worktrees" / self.BRANCH
        env = mock_sync.call_args.kwargs["env"]
        assert "VIRTUAL_ENV" not in env
        assert env["UV_CACHE_DIR"] == str(cache)

    def test_a_relative_uv_cache_stays_this_checkouts_cache(
        self,
        mocks: tuple[MagicMock, MagicMock],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """base.py's relative default would otherwise resolve inside the new worktree."""
        _, mock_sync = mocks
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("UV_CACHE_DIR", "tmp/.uv_cache")
        self._create(self.BRANCH)

        env = mock_sync.call_args.kwargs["env"]
        assert env["UV_CACHE_DIR"] == str((tmp_path / "tmp" / ".uv_cache").resolve())

    def test_prints_how_to_work_there_and_how_to_remove_it(
        self,
        mocks: tuple[MagicMock, MagicMock],
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._create(self.BRANCH)

        out = capsys.readouterr().out
        path = tmp_path / "worktrees" / self.BRANCH
        assert f"cd {path}" in out
        assert "uv run doit check" in out
        assert "Never pass --active" in out
        assert f"git worktree remove {path}" in out

    def test_points_at_pr_merge_to_remove_it(
        self,
        mocks: tuple[MagicMock, MagicMock],
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Merged from the main checkout, the PR takes its worktree with it (#863)."""
        self._create(self.BRANCH)

        lines = capsys.readouterr().out.splitlines()
        assert f"  cd {tmp_path}" in lines
        assert "  uv run doit pr_merge --pr=<number>" in lines

    def test_requires_a_branch(self, mocks: tuple[MagicMock, MagicMock]) -> None:
        mock_run, mock_sync = mocks
        with pytest.raises(SystemExit) as exc:
            self._create(None)

        assert exc.value.code == 1
        mock_run.assert_not_called()
        mock_sync.assert_not_called()

    def test_refuses_an_invalid_branch_name(self, mocks: tuple[MagicMock, MagicMock]) -> None:
        """The name becomes a path under worktrees/, so it is checked before anything runs."""
        mock_run, mock_sync = mocks
        mock_run.side_effect = _fake_git(valid_name=False)
        with pytest.raises(SystemExit) as exc:
            self._create("feat/bad name")

        assert exc.value.code == 1
        assert [cmd[1] for cmd in self._cmds(mock_run)] == ["check-ref-format"]
        mock_sync.assert_not_called()

    @pytest.mark.parametrize("name", ["feat/1-[x]", "feat/1-[/x]", r"feat/1-\[1]", "feat/:memo:"])
    def test_prints_a_rejected_name_verbatim(
        self,
        mocks: tuple[MagicMock, MagicMock],
        capsys: pytest.CaptureFixture[str],
        name: str,
    ) -> None:
        """The name is text, not markup: Rich would drop `[x]` and crash on `[/x]` (#907).

        Escaped, it still lost the backslash before `[1]` and turned `:memo:` into an emoji (#914).
        """
        mock_run, _ = mocks
        mock_run.side_effect = _fake_git(valid_name=False)
        with pytest.raises(SystemExit) as exc:
            self._create(name)

        assert exc.value.code == 1
        assert f"Not a valid branch name: {name}" in _ANSI.sub("", capsys.readouterr().out)

    @pytest.mark.parametrize("name", ["[x]", "[/x]", r"x\[1]", ":memo:"])
    def test_prints_the_paths_verbatim(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        name: str,
    ) -> None:
        """The checkout's path is text, not markup (#920).

        git and uv are mocked, so the path never has to exist, and `:memo:` works on Windows too.
        """
        monkeypatch.setenv("COLUMNS", "1000")  # a long tmp_path must not wrap
        root = tmp_path / name
        with (
            patch("tools.doit.git._main_checkout", return_value=root),
            patch("tools.doit.git.subprocess.run", side_effect=_fake_git()),
            patch("tools.doit.git.run_streamed"),
        ):
            self._create(self.BRANCH)

        lines = _ANSI.sub("", capsys.readouterr().out).splitlines()
        path = root / "worktrees" / self.BRANCH
        assert f"Created {path} on {self.BRANCH}, from origin/main." in lines
        assert f"  cd {path}" in lines
        assert f"  cd {root}" in lines
        assert f"  git worktree remove {path}" in lines

    @pytest.mark.parametrize("name", ["../escape", "/tmp/escape", "feat/../../escape"])
    def test_git_rejects_names_that_would_leave_worktrees_dir(self, name: str) -> None:
        """The path check relies on git refusing these; pin that with the real git."""
        result = subprocess.run(
            ["git", "check-ref-format", "--branch", name],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0

    def test_fetch_failure_warns_and_still_creates(
        self, mocks: tuple[MagicMock, MagicMock], capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Offline, the last fetched origin/main is still a sound base; `doit pr` checks later."""
        mock_run, mock_sync = mocks
        error = subprocess.CalledProcessError(128, ["git"], stderr="could not resolve host")
        mock_run.side_effect = _fake_git(fail={"fetch": error})
        self._create(self.BRANCH)

        assert "worktree" in [cmd[1] for cmd in self._cmds(mock_run)]
        mock_sync.assert_called_once()
        assert "could not resolve host" in capsys.readouterr().out

    def test_worktree_add_failure_exits_before_syncing(
        self, mocks: tuple[MagicMock, MagicMock], capsys: pytest.CaptureFixture[str]
    ) -> None:
        mock_run, mock_sync = mocks
        error = subprocess.CalledProcessError(
            128, ["git"], stderr="fatal: a branch named 'feat/42-add-export' already exists"
        )
        mock_run.side_effect = _fake_git(fail={"worktree": error})
        with pytest.raises(SystemExit) as exc:
            self._create(self.BRANCH)

        assert exc.value.code == 1
        mock_sync.assert_not_called()
        assert "already exists" in capsys.readouterr().out

    def test_sync_failure_exits_and_keeps_the_worktree(
        self, mocks: tuple[MagicMock, MagicMock], capsys: pytest.CaptureFixture[str]
    ) -> None:
        """No silent revert: the worktree stays, with the command to retry."""
        mock_run, mock_sync = mocks
        mock_sync.side_effect = subprocess.CalledProcessError(1, ["uv"])
        with pytest.raises(SystemExit) as exc:
            self._create(self.BRANCH)

        assert exc.value.code == 1
        assert ["git", "worktree", "remove"] not in [cmd[:3] for cmd in self._cmds(mock_run)]
        assert "uv sync --all-extras --dev" in capsys.readouterr().out


def test_main_checkout_is_the_first_listed_worktree() -> None:
    """Run from a linked worktree, `doit worktree` still creates beside the main checkout."""
    porcelain = (
        "worktree /src/project\nHEAD abc\nbranch refs/heads/main\n\n"
        "worktree /src/project/worktrees/feat/1-x\nHEAD def\nbranch refs/heads/feat/1-x\n"
    )
    with patch("tools.doit.git.subprocess.run", return_value=MagicMock(stdout=porcelain)):
        assert _main_checkout() == Path("/src/project")


def test_worktrees_directory_is_gitignored() -> None:
    """A worktree inside the repository must never show as untracked, or be committed."""
    result = subprocess.run(
        ["git", "check-ignore", "-q", "worktrees/feat/42-add-export/pyproject.toml"],
        cwd=REPO_ROOT,
        check=False,
    )
    assert result.returncode == 0


def test_claude_code_worktrees_are_ignored_by_their_own_rule() -> None:
    """Claude Code's worktree tool uses `.claude/worktrees/` (#860).

    Until #860 that directory was ignored only because `worktrees/` matched at
    every level, so anchoring that rule would have exposed it.
    """
    result = subprocess.run(
        ["git", "check-ignore", "-v", ".claude/worktrees/847-trial/pyproject.toml"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    source = result.stdout.split("\t")[0]  # "<file>:<line>:<pattern>"
    assert source.endswith(":.claude/worktrees/")


def test_other_directories_named_worktrees_stay_tracked() -> None:
    """The rule is anchored to the root, so a `docs/worktrees/` page can be committed (#860)."""
    result = subprocess.run(
        ["git", "check-ignore", "-q", "docs/worktrees/notes.md"],
        cwd=REPO_ROOT,
        check=False,
    )
    assert result.returncode == 1


def _git(cwd: Path, *args: str) -> str:
    """Run git in *cwd* with a fixed identity; return its stripped stdout."""
    result = subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=Test", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


@pytest.fixture
def main_checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A real repository to run from, ignoring what this one does for the tests below."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / ".gitignore").write_text(
        ".venv/\n__pycache__/\n.envrc.local\n/mutants/\n/worktrees/\ntmp/*\n!tmp/.gitkeep\n",
        encoding="utf-8",
    )
    (repo / "tmp").mkdir()
    (repo / "tmp" / ".gitkeep").touch()
    _git(repo, "add", ".gitignore", "tmp/.gitkeep")
    _git(repo, "commit", "-q", "-m", "init")
    monkeypatch.chdir(repo)
    return repo


def _add_worktree(repo: Path, branch: str, path: Path | None = None) -> tuple[Path, str]:
    """Create *branch* in a worktree with one commit; return its path and that commit."""
    path = path or repo / "worktrees" / branch
    _git(repo, "worktree", "add", "-q", "-b", branch, str(path))
    (path / "export.py").write_text("x = 1\n", encoding="utf-8")
    _git(path, "add", "export.py")
    _git(path, "commit", "-q", "-m", "feat: add export")
    return path, _git(path, "rev-parse", "HEAD")


def _has_branch(repo: Path, branch: str) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


class TestWorktreeForBranch:
    """Which linked worktree holds a PR's branch (#863)."""

    def test_returns_the_worktree_that_has_the_branch_checked_out(
        self, main_checkout: Path
    ) -> None:
        path, _ = _add_worktree(main_checkout, "feat/1-x")

        found = worktree_for_branch("feat/1-x")

        assert found is not None
        assert found.resolve() == path.resolve()

    def test_never_returns_the_main_checkout(self, main_checkout: Path) -> None:
        """gh's --delete-branch handles a branch checked out there."""
        _add_worktree(main_checkout, "feat/1-x")

        assert worktree_for_branch("main") is None

    def test_returns_none_for_a_branch_no_worktree_has_checked_out(
        self, main_checkout: Path
    ) -> None:
        _git(main_checkout, "branch", "feat/2-y")

        assert worktree_for_branch("feat/2-y") is None


class TestRemoveMergedWorktree:
    """`doit pr_merge` removes a merged PR's worktree and branch, with real git (#863)."""

    BRANCH = "feat/1-add-export"

    @staticmethod
    def _remove(path: Path, branch: str, merged_head: str) -> str:
        output = io.StringIO()
        remove_merged_worktree(path, branch, merged_head, Console(file=output, width=200))
        return output.getvalue()

    def test_removes_the_worktree_its_branch_and_the_emptied_directory(
        self, main_checkout: Path
    ) -> None:
        path, head = _add_worktree(main_checkout, self.BRANCH)

        out = self._remove(path, self.BRANCH, head)

        assert not path.exists()
        assert not (main_checkout / "worktrees" / "feat").exists()
        assert (main_checkout / "worktrees").is_dir()
        assert not _has_branch(main_checkout, self.BRANCH)
        assert "Removed worktree" in out
        assert "Deleted local branch" in out

    def test_rebuildable_ignored_files_do_not_keep_it(self, main_checkout: Path) -> None:
        """Every worktree has a .venv; deleting it with the worktree loses nothing."""
        path, head = _add_worktree(main_checkout, self.BRANCH)
        (path / ".venv" / "bin").mkdir(parents=True)
        (path / ".venv" / "bin" / "python").write_text("", encoding="utf-8")
        (path / "__pycache__").mkdir()
        (path / "__pycache__" / "export.cpython-312.pyc").write_bytes(b"")

        self._remove(path, self.BRANCH, head)

        assert not path.exists()

    def test_pre_commit_store_does_not_keep_it(self, main_checkout: Path) -> None:
        """PRE_COMMIT_HOME under tmp/ (#998); pre-commit rebuilds its store on next run."""
        path, head = _add_worktree(main_checkout, self.BRANCH)
        (path / "tmp" / ".pre-commit").mkdir(parents=True)
        (path / "tmp" / ".pre-commit" / "db.db").write_text("", encoding="utf-8")

        self._remove(path, self.BRANCH, head)

        assert not path.exists()

    def test_mutmut_cache_does_not_keep_it(self, main_checkout: Path) -> None:
        """mutants/ is mutmut's copy of the project (#1000); the next run makes it again."""
        path, head = _add_worktree(main_checkout, self.BRANCH)
        (path / "mutants").mkdir()
        (path / "mutants" / "mutmut-stats.json").write_text("{}\n", encoding="utf-8")

        self._remove(path, self.BRANCH, head)

        assert not path.exists()

    @pytest.mark.parametrize(
        ("name", "status"),
        [
            ("notes.md", "?? notes.md"),  # untracked: git refuses
            ("export.py", " M export.py"),  # modified: git refuses
            (".envrc.local", "!! .envrc.local"),  # ignored: git would delete it
        ],
    )
    def test_files_the_merge_did_not_take_keep_it(
        self, main_checkout: Path, name: str, status: str
    ) -> None:
        path, head = _add_worktree(main_checkout, self.BRANCH)
        (path / name).write_text("local\n", encoding="utf-8")

        out = self._remove(path, self.BRANCH, head)

        assert (path / name).exists()
        assert _has_branch(main_checkout, self.BRANCH)
        lines = out.splitlines()
        assert f"  {status}" in lines
        assert f"  git worktree remove {path}" in lines
        assert f"  git branch -D {self.BRANCH}" in lines

    def test_a_branch_that_moved_past_the_merged_commit_is_kept(self, main_checkout: Path) -> None:
        """`-D` would drop the commit the PR never merged."""
        path, merged = _add_worktree(main_checkout, self.BRANCH)
        (path / "export.py").write_text("x = 2\n", encoding="utf-8")
        _git(path, "commit", "-q", "-am", "fix: not pushed")

        out = self._remove(path, self.BRANCH, merged)

        assert not path.exists()
        assert _has_branch(main_checkout, self.BRANCH)
        assert f"Kept local branch {self.BRANCH}" in out

    def test_from_inside_the_worktree_it_prints_the_commands(
        self, main_checkout: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The task runs in the directory it would delete, so it removes nothing."""
        path, head = _add_worktree(main_checkout, self.BRANCH)
        root = _main_checkout()
        monkeypatch.chdir(path)

        out = self._remove(path, self.BRANCH, head)

        assert path.is_dir()
        assert _has_branch(main_checkout, self.BRANCH)
        lines = out.splitlines()
        assert "runs inside the worktree" in out
        assert f"  cd {root}" in lines
        assert f"  git worktree remove {path}" in lines
        assert f"  git branch -D {self.BRANCH}" in lines

    def test_a_worktree_outside_worktrees_dir_is_left_alone(
        self, main_checkout: Path, tmp_path: Path
    ) -> None:
        """Another tool made it, such as Claude Code in .claude/worktrees/."""
        path, head = _add_worktree(main_checkout, self.BRANCH, tmp_path / "elsewhere")

        out = self._remove(path, self.BRANCH, head)

        assert path.is_dir()
        assert _has_branch(main_checkout, self.BRANCH)
        assert "did not create" in out

    def test_a_sibling_worktree_keeps_the_shared_directory(self, main_checkout: Path) -> None:
        path, head = _add_worktree(main_checkout, self.BRANCH)
        sibling, _ = _add_worktree(main_checkout, "feat/2-other")

        self._remove(path, self.BRANCH, head)

        assert not path.exists()
        assert sibling.is_dir()

    def test_a_git_refusal_is_reported_and_keeps_the_branch(self, main_checkout: Path) -> None:
        path, head = _add_worktree(main_checkout, self.BRANCH)
        _git(main_checkout, "worktree", "lock", str(path))

        out = self._remove(path, self.BRANCH, head)

        assert path.is_dir()
        assert _has_branch(main_checkout, self.BRANCH)
        assert "git worktree remove failed" in out

    @pytest.mark.parametrize("name", _PATH_NAMES)
    def test_prints_a_removed_path_verbatim(self, main_checkout: Path, name: str) -> None:
        """The path is text, not markup (#920)."""
        path, head = _add_worktree(main_checkout, self.BRANCH, main_checkout / "worktrees" / name)

        out = _ANSI.sub("", self._remove(path, self.BRANCH, head))

        assert not path.exists()
        assert f"Removed worktree {path}" in out.splitlines()

    @pytest.mark.parametrize("name", _PATH_NAMES)
    def test_prints_a_kept_path_verbatim(self, main_checkout: Path, name: str) -> None:
        path, head = _add_worktree(main_checkout, self.BRANCH, main_checkout / "worktrees" / name)
        (path / "notes.md").write_text("local\n", encoding="utf-8")

        out = _ANSI.sub("", self._remove(path, self.BRANCH, head))

        assert path.is_dir()
        assert f"Left {path} in place." in out

    @pytest.mark.parametrize("name", _PATH_NAMES)
    def test_prints_a_path_outside_worktrees_dir_verbatim(
        self, main_checkout: Path, tmp_path: Path, name: str
    ) -> None:
        path, head = _add_worktree(main_checkout, self.BRANCH, tmp_path / name)

        out = _ANSI.sub("", self._remove(path, self.BRANCH, head))

        assert path.is_dir()
        assert f"{self.BRANCH} is checked out in {path}, which" in out

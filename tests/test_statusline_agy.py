"""Tests for tools/statusline/agy-statusline.sh."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _strip(text: str) -> str:
    """Remove ANSI color codes so exact substrings aren't split by color spans."""
    return _ANSI.sub("", text)


# The helper is a bash script targeting Linux/macOS; the Windows GitHub Actions
# runner's `bash` resolves to wsl.exe (which has no installed distribution),
# so subprocess invocations cannot exercise the real shell behavior.
pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="bash helper is Linux/macOS only; Windows runner has no usable bash",
)

REPO_ROOT = Path(__file__).resolve().parent.parent
AGY = REPO_ROOT / "tools" / "statusline" / "agy-statusline.sh"


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point HOME at a throwaway directory for every test in this module.

    The script calls `gh api user`. `gh` resolves its state directory as
    ``$XDG_STATE_HOME``, falling back to ``$HOME/.local/state`` — and with HOME
    unset that fallback is *relative*, so `gh` wrote ``.local/state/gh/device-id``
    into the current working directory, which under pytest is the repository
    root. Every run of this module dirtied the working tree (#698).

    The sibling statusline modules already pin HOME to a tmp dir; this one did
    not.
    """
    monkeypatch.setenv("HOME", str(tmp_path))


def _run(payload: str, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Invoke the statusline script with the given JSON payload on stdin."""
    # HOME is forwarded deliberately — see `_isolated_home`. A child without it
    # writes into the repository.
    env = {"PATH": os.environ["PATH"], "HOME": os.environ["HOME"]}
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", str(AGY)],
        input=payload,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )


def _make_git_repo(path: Path, branch: str = "trunk") -> None:
    """Create a minimal git repo on `branch` with a single commit."""
    path.mkdir(parents=True, exist_ok=True)

    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-C", str(path), *args],
            check=True,
            capture_output=True,
            text=True,
        )

    git("init", "-q")
    git("checkout", "-q", "-b", branch)
    (path / "README.md").write_text("x", encoding="utf-8")
    git("add", "-A")
    git("-c", "user.email=t@example.com", "-c", "user.name=Test", "commit", "-q", "-m", "init")


_QUOTA_PAYLOAD = json.dumps(
    {
        "model": {"display_name": "Gemini 3 Pro"},
        "sandbox": {"enabled": True},
        "quota": {
            "gemini-5h": {"remaining_fraction": 1.0},
            "gemini-weekly": {"remaining_fraction": 0.9},
        },
    }
)


def test_script_exists_and_executable() -> None:
    """Script must exist at the expected path and be executable."""
    assert AGY.exists(), f"Script not found: {AGY}"
    assert os.access(AGY, os.X_OK), f"Script not executable: {AGY}"


def test_script_syntax_valid() -> None:
    """bash -n must report no syntax errors."""
    result = subprocess.run(
        ["bash", "-n", str(AGY)],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, f"Syntax error:\n{result.stderr}"


def test_directory_and_branch_from_local_git(tmp_path: Path) -> None:
    """Directory (package name) and branch are computed from the workspace git repo."""
    repo = tmp_path / "myproj"
    _make_git_repo(repo, "trunk")
    payload = json.dumps({"workspace": {"current_dir": str(repo)}, "model": {"display_name": "M"}})
    result = _run(payload, {"HOME": str(tmp_path)})
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "myproj" in result.stdout  # directory / package name
    assert "trunk" in result.stdout  # branch computed locally via git


def test_git_status_reports_uncommitted(tmp_path: Path) -> None:
    """An uncommitted file is reflected in the git status segment."""
    repo = tmp_path / "proj"
    _make_git_repo(repo, "main")
    (repo / "dirty.txt").write_text("x", encoding="utf-8")  # untracked → uncommitted
    payload = json.dumps({"workspace": {"current_dir": str(repo)}})
    result = _run(payload, {"HOME": str(tmp_path)})
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "uncommitted" in result.stdout


def test_model_from_payload() -> None:
    """model.display_name is rendered."""
    result = _run(json.dumps({"model": {"display_name": "Gemini 3 Pro"}}))
    assert result.returncode == 0
    assert "Gemini 3 Pro" in result.stdout


def test_agent_state_label_appears() -> None:
    """agent_state is rendered as a label."""
    result = _run(json.dumps({"agent_state": "working"}))
    assert result.returncode == 0
    assert "working" in result.stdout


def test_context_bar_and_token_count() -> None:
    """Context bar renders from token occupancy and shows the window size."""
    payload = json.dumps(
        {
            "context_window": {
                "context_window_size": 1000000,
                "current_usage": {"input_tokens": 250000},
            }
        }
    )
    result = _run(payload)
    assert result.returncode == 0
    assert any(ch in result.stdout for ch in ("░", "▄", "█"))
    assert "25%" in result.stdout
    assert "of 1000k tokens" in result.stdout


def test_empty_json_exits_zero_with_defaults() -> None:
    """Empty JSON object falls back to defaults: rc 0, idle state, no crash."""
    result = _run("{}")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "idle" in result.stdout
    assert result.stdout.strip() != ""


def test_malformed_stdin_exits_zero_with_defaults() -> None:
    """Non-JSON stdin falls back to all defaults and exits 0 without crashing."""
    result = _run("not json")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert result.stdout.strip() != ""


def test_quota_absent_by_default() -> None:
    """Without AGY_STATUSLINE_EXTRAS, the quota segment is not rendered."""
    result = _run(_QUOTA_PAYLOAD)
    assert result.returncode == 0
    assert "5h:" not in result.stdout


def test_quota_present_when_enabled() -> None:
    """AGY_STATUSLINE_EXTRAS=1 appends 5h and weekly quota (used = 1 - remaining)."""
    result = _run(_QUOTA_PAYLOAD, {"AGY_STATUSLINE_EXTRAS": "1"})
    assert result.returncode == 0
    out = _strip(result.stdout)
    assert "5h:0%" in out  # remaining_fraction 1.0 → 0% used
    assert "wk:10%" in out  # remaining_fraction 0.9 → 10% used


def test_sandbox_indicator_when_enabled() -> None:
    """Sandbox lock indicator appears when sandbox.enabled and extras are on."""
    result = _run(_QUOTA_PAYLOAD, {"AGY_STATUSLINE_EXTRAS": "1"})
    assert result.returncode == 0
    assert "🔒" in result.stdout


def test_sandbox_absent_when_disabled() -> None:
    """No sandbox indicator when the sandbox is disabled, even with extras on."""
    payload = json.dumps({"model": {"display_name": "M"}, "sandbox": {"enabled": False}})
    result = _run(payload, {"AGY_STATUSLINE_EXTRAS": "1"})
    assert result.returncode == 0
    assert "🔒" not in result.stdout


def test_invocation_does_not_write_into_the_repository() -> None:
    """No invocation may leave `gh`'s state directory in the repository.

    `.local/` at the repository root only ever appears from this bug: real
    `gh` usage writes to `~/.local/state`, and only a child launched without
    HOME falls back to a relative path (#698).

    Asserted absolutely rather than as a before/after diff. A diff passes
    vacuously when an earlier test in the module already created the
    directory — which is exactly what happened while developing this guard, so
    the first assertion below covers sibling tests and the second covers this
    one.
    """
    local_state = REPO_ROOT / ".local"

    assert not local_state.exists(), (
        "another test already wrote .local/ into the repository root; "
        "HOME isolation has regressed (see _isolated_home)"
    )

    _run(json.dumps({"model": {"display_name": "Gemini 3 Pro"}}))

    assert not local_state.exists(), "this invocation created .local/ in the repository root"

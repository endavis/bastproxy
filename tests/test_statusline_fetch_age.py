"""Tests for the FETCH_HEAD age in both statusline scripts' git sync status.

GNU `stat -f` means "filesystem status": it exits 1 but still prints to
stdout, so a `$(stat -f %m f || stat -c %Y f)` capture holds both outputs and
the age arithmetic fails. These tests pin the sync-status rendering on the
runner's real `stat`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

# The statusline scripts are bash targeting Linux/macOS; the Windows GitHub
# Actions runner's `bash` resolves to wsl.exe (which has no installed
# distribution), so subprocess invocations cannot exercise real shell behavior.
pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="bash statusline scripts are Linux/macOS only; Windows runner has no usable bash",
)

REPO_ROOT = Path(__file__).resolve().parent.parent
CLAUDE_STATUSLINE = REPO_ROOT / ".claude" / "statusline-command.sh"
AGY_STATUSLINE = REPO_ROOT / "tools" / "statusline" / "agy-statusline.sh"

SCRIPTS = pytest.mark.parametrize(
    "script",
    [
        pytest.param(CLAUDE_STATUSLINE, id="claude"),
        pytest.param(AGY_STATUSLINE, id="agy"),
    ],
)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        timeout=10,
    )


def _make_synced_clone(tmp_path: Path) -> Path:
    """Create a clone whose branch tracks, and matches, its upstream."""
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "--bare", "-b", "main", str(origin))
    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", str(origin), str(clone))
    _git(clone, "checkout", "-q", "-b", "main")
    _git(clone, "commit", "-q", "--allow-empty", "--no-verify", "-m", "init")
    _git(clone, "push", "-q", "--no-verify", "-u", "origin", "main")
    return clone


def _run(script: Path, clone: Path, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    """Invoke a statusline script pointed at the clone."""
    payload = json.dumps(
        {
            "model": {"display_name": "TestModel"},
            "cwd": str(clone),
            "workspace": {"current_dir": str(clone)},
            "transcript_path": "",
            "context_window": {"context_window_size": 200000},
        }
    )
    env = {
        "HOME": str(tmp_path),
        "PATH": os.environ["PATH"],
        "CLAUDE_PROJECT_DIR": str(REPO_ROOT),
    }
    return subprocess.run(
        ["bash", str(script)],
        input=payload,
        cwd=clone,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )


@SCRIPTS
def test_fetch_head_age_rendered(script: Path, tmp_path: Path) -> None:
    """A FETCH_HEAD five minutes old renders as `synced 5m ago`."""
    clone = _make_synced_clone(tmp_path)
    fetch_head = clone / ".git" / "FETCH_HEAD"
    fetch_head.write_text("", encoding="utf-8")
    five_min_ago = time.time() - 300
    os.utime(fetch_head, (five_min_ago, five_min_ago))

    result = _run(script, clone, tmp_path)

    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "arithmetic" not in result.stderr
    assert "0 files uncommitted, synced 5m ago" in result.stdout


@SCRIPTS
def test_no_fetch_head_renders_plain_synced(script: Path, tmp_path: Path) -> None:
    """Without FETCH_HEAD the sync status is `synced` with no age."""
    clone = _make_synced_clone(tmp_path)

    result = _run(script, clone, tmp_path)

    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "0 files uncommitted, synced)" in result.stdout

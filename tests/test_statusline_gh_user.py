"""Tests for the GitHub user segment shared by both statusline scripts.

`gh api` writes the HTTP error body to stdout on failure, so a naive
`$(gh api ... || echo "")` capture renders the error JSON into the statusline.
These tests pin the degradation behavior for both scripts.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
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

# Each script reads its own payload shape; supplying both keys exercises either.
_PAYLOAD = json.dumps(
    {
        "model": {"display_name": "TestModel"},
        "cwd": "/",
        "workspace": {"current_dir": "/"},
        "transcript_path": "",
        "context_window": {"context_window_size": 200000},
    }
)

# The literal body GitHub returns for an expired or invalid token.
_BAD_CREDENTIALS_BODY = """{
  "message": "Bad credentials",
  "documentation_url": "https://docs.github.com/rest",
  "status": "401"
}"""


def _stub_gh(tmp_path: Path, *, stdout: str, stderr: str = "", exit_code: int = 0) -> Path:
    """Create a `gh` stub on a fresh bin dir and return that dir."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(
        "#!/bin/bash\n"
        f"cat <<'STDOUT_EOF'\n{stdout}\nSTDOUT_EOF\n"
        f"cat >&2 <<'STDERR_EOF'\n{stderr}\nSTDERR_EOF\n"
        f"exit {exit_code}\n",
        encoding="utf-8",
    )
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
    return bin_dir


def _run(script: Path, bin_dir: Path, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    """Invoke a statusline script with the stub bin dir ahead of the real PATH."""
    env = {
        "HOME": str(tmp_path),
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "CLAUDE_PROJECT_DIR": str(REPO_ROOT),
    }
    return subprocess.run(
        ["bash", str(script)],
        input=_PAYLOAD,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )


@SCRIPTS
def test_gh_failure_body_not_rendered(script: Path, tmp_path: Path) -> None:
    """A 401 body on gh's stdout must not leak into the statusline."""
    bin_dir = _stub_gh(
        tmp_path,
        stdout=_BAD_CREDENTIALS_BODY,
        stderr="gh: Bad credentials (HTTP 401)\n",
        exit_code=1,
    )

    result = _run(script, bin_dir, tmp_path)

    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "Bad credentials" not in result.stdout
    assert "documentation_url" not in result.stdout
    assert '"status": "401"' not in result.stdout
    # The whole user segment degrades away rather than rendering a bare marker.
    assert "@" not in result.stdout


@SCRIPTS
def test_gh_missing_renders_no_user_segment(script: Path, tmp_path: Path) -> None:
    """A `gh` that is absent (exit 127, no stdout) yields no user segment."""
    bin_dir = _stub_gh(tmp_path, stdout="", stderr="gh: command not found\n", exit_code=127)

    result = _run(script, bin_dir, tmp_path)

    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "@" not in result.stdout


@SCRIPTS
def test_gh_success_renders_login(script: Path, tmp_path: Path) -> None:
    """A successful `gh api user` still renders the login, prefixed with `@`."""
    bin_dir = _stub_gh(tmp_path, stdout="octocat", exit_code=0)

    result = _run(script, bin_dir, tmp_path)

    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "@octocat" in result.stdout

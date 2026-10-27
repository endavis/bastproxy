"""Tests for the missing-`jq` guard shared by both statusline scripts.

Without `jq`, every `jq` invocation in these bash scripts would write a
"command not found" diagnostic to stderr on each render and the fields that
depend on it would silently render blank. Both scripts guard on `command -v
jq` before using it and print a one-line message instead (#930).
"""

from __future__ import annotations

import json
import shutil
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

# Utilities the scripts invoke; `jq` is deliberately excluded so the PATH
# built from this list reproduces a host with no jq installed.
_REQUIRED_TOOLS = (
    "bash",
    "git",
    "basename",
    "cat",
    "sed",
    "head",
    "wc",
    "tr",
    "date",
    "stat",
    "awk",
)


def _path_without_jq(tmp_path: Path) -> Path:
    """Build a bin dir holding the scripts' dependencies but no `jq`."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in _REQUIRED_TOOLS:
        resolved = shutil.which(tool)
        if resolved is not None:
            (bin_dir / tool).symlink_to(resolved)
    assert shutil.which("jq", path=str(bin_dir)) is None, "jq must not be reachable"
    return bin_dir


def _run(script: Path, bin_dir: Path, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    """Invoke a statusline script with a PATH that has no `jq`."""
    return subprocess.run(
        ["bash", str(script)],
        input=_PAYLOAD,
        env={"HOME": str(tmp_path), "PATH": str(bin_dir)},
        capture_output=True,
        text=True,
        timeout=10,
    )


@SCRIPTS
def test_missing_jq_exits_zero_with_one_line_message(script: Path, tmp_path: Path) -> None:
    """Without `jq`, the script exits 0 and prints a single actionable line."""
    result = _run(script, _path_without_jq(tmp_path), tmp_path)

    assert result.returncode == 0
    assert "jq not installed" in result.stdout
    assert "doit install_jq" in result.stdout


@SCRIPTS
def test_missing_jq_writes_nothing_to_stderr(script: Path, tmp_path: Path) -> None:
    """A missing `jq` must not emit a shell diagnostic on every render."""
    result = _run(script, _path_without_jq(tmp_path), tmp_path)

    assert result.stderr == "", f"unexpected stderr: {result.stderr!r}"
    assert "command not found" not in result.stderr

"""Tests for the Python version segment shared by both statusline scripts.

A statusline runs on every render, so a missing `python` binary must degrade
silently rather than writing a shell diagnostic to stderr each time. The
unversioned `python` is absent on Debian/Ubuntu without `python-is-python3`
and outside an activated virtualenv, so this is a routine condition.
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

# Utilities the scripts invoke; `python` is deliberately excluded so the PATH
# built from this list reproduces a host with no unversioned python.
_REQUIRED_TOOLS = (
    "bash",
    "jq",
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


def _path_without_python(tmp_path: Path) -> Path:
    """Build a bin dir holding the scripts' dependencies but no `python`."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in _REQUIRED_TOOLS:
        resolved = shutil.which(tool)
        if resolved is not None:
            (bin_dir / tool).symlink_to(resolved)
    assert shutil.which("python", path=str(bin_dir)) is None, "python must not be reachable"
    return bin_dir


def _run(script: Path, bin_dir: Path, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    """Invoke a statusline script with a PATH that has no `python`."""
    return subprocess.run(
        ["bash", str(script)],
        input=_PAYLOAD,
        env={"HOME": str(tmp_path), "PATH": str(bin_dir)},
        capture_output=True,
        text=True,
        timeout=10,
    )


@SCRIPTS
def test_missing_python_writes_nothing_to_stderr(script: Path, tmp_path: Path) -> None:
    """A missing `python` must not emit a shell diagnostic on every render."""
    result = _run(script, _path_without_python(tmp_path), tmp_path)

    assert result.returncode == 0
    assert result.stderr == "", f"unexpected stderr: {result.stderr!r}"
    assert "command not found" not in result.stderr


@SCRIPTS
def test_missing_python_omits_version_segment(script: Path, tmp_path: Path) -> None:
    """Without `python`, the version segment is dropped but the line still renders."""
    result = _run(script, _path_without_python(tmp_path), tmp_path)

    assert result.returncode == 0
    assert "Python:" not in result.stdout
    assert result.stdout.strip() != "", "statusline must still render its other segments"


@SCRIPTS
def test_python_version_rendered_when_available(script: Path, tmp_path: Path) -> None:
    """With `python` on PATH, its dotted version is rendered."""
    bin_dir = _path_without_python(tmp_path)
    # Symlink the running interpreter, not whatever `python` PATH resolves to,
    # so the asserted version always matches sys.version_info on every CI leg.
    (bin_dir / "python").symlink_to(sys.executable)

    result = _run(script, bin_dir, tmp_path)

    assert result.returncode == 0, f"stderr: {result.stderr}"
    expected = ".".join(str(part) for part in sys.version_info[:3])
    assert f"Python: {expected}" in result.stdout

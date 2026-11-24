"""Tests for running the package with ``python -m bastproxy``."""

import os
import subprocess
import sys
from pathlib import Path


def test_python_m_bastproxy_help(tmp_path: Path) -> None:
    """``python -m bastproxy --help`` prints the usage and exits 0."""
    env = {**os.environ, "BASTPROXY_HOME": str(tmp_path)}
    result = subprocess.run(  # noqa: S603  # fixed argv: this interpreter running the package
        [sys.executable, "-m", "bastproxy", "--help"],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout
    assert "--port" in result.stdout

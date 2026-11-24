"""The autouse fixture in conftest keeps tests off the developer's git config (#1292)."""

import os
import subprocess
from pathlib import Path


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)


def test_env_points_at_empty_config() -> None:
    config = Path(os.environ["GIT_CONFIG_GLOBAL"])
    assert config.is_file()
    assert config.read_text(encoding="utf-8") == ""
    assert os.environ["GIT_CONFIG_NOSYSTEM"] == "1"


def test_global_config_is_empty(tmp_path: Path) -> None:
    result = _git(tmp_path, "config", "--global", "--list")
    assert result.stdout.strip() == ""


def test_tag_works_despite_signing_default(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    assert _git(tmp_path, "config", "tag.gpgsign").stdout.strip() == ""
    assert _git(tmp_path, "config", "user.name", "T").returncode == 0
    assert _git(tmp_path, "config", "user.email", "t@example.com").returncode == 0
    assert _git(tmp_path, "commit", "--allow-empty", "-m", "x").returncode == 0
    result = _git(tmp_path, "tag", "-a", "v0", "-m", "v0")
    assert result.returncode == 0, result.stderr

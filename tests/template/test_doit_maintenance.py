"""`doit cleanup` and `doit completions_install` print the paths they touch as text (#920).

Rich read them as markup: it dropped `[x]`, crashed on `[/x]`, dropped the backslash before `[1]`
and turned `:memo:` into an emoji.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from tools.doit.maintenance import task_cleanup, task_completions_install, task_update_deps

# FORCE_COLOR makes Rich color captured output, and the codes split substrings such as `[x]`.
_ANSI = re.compile(r"\x1b\[[0-9;]*m")

_NOT_ON_WINDOWS = pytest.mark.skipif(os.name == "nt", reason="Windows refuses : in a name")

# Real directories. On Windows `x\[1]` is two of them, and `:` cannot be in a name.
_PATH_NAMES = ["[x]", "[/x]", r"x\[1]", pytest.param(":memo:", marks=_NOT_ON_WINDOWS)]


def _run(task: Callable[[], dict[str, Any]]) -> None:
    action: Callable[[], None] = task()["actions"][0]
    action()


def _lines(capsys: pytest.CaptureFixture[str]) -> list[str]:
    return _ANSI.sub("", capsys.readouterr().out).splitlines()


class TestCleanup:
    @pytest.mark.parametrize("name", _PATH_NAMES)
    def test_prints_the_removed_cache_paths_verbatim(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        name: str,
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("COLUMNS", "1000")
        package = Path(name)
        (package / "__pycache__").mkdir(parents=True)
        (package / "stale.pyc").write_bytes(b"")

        _run(task_cleanup)

        # os.walk(".") reaches them one directory at a time, joined with os.sep.
        found = os.path.join(".", *package.parts)
        lines = _lines(capsys)
        assert f"  Removing {os.path.join(found, '__pycache__')}..." in lines
        assert f"  Removing {os.path.join(found, 'stale.pyc')}..." in lines
        assert not (package / "__pycache__").exists()

    @pytest.mark.parametrize(
        "name",
        [
            "[x]",
            pytest.param(r"x\[1]", marks=pytest.mark.skipif(os.name == "nt", reason="two names")),
            pytest.param(":memo:", marks=_NOT_ON_WINDOWS),
        ],
    )
    def test_prints_a_removed_egg_info_verbatim(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        name: str,
    ) -> None:
        """Only a top-level `*.egg-info` is removed, so the name cannot hold a separator."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("COLUMNS", "1000")
        Path(f"{name}.egg-info").mkdir()

        _run(task_cleanup)

        assert f"  Removing {name}.egg-info..." in _lines(capsys)
        assert not Path(f"{name}.egg-info").exists()


class TestCleanupLeavesTheUvCache:
    def test_runs_no_uv_cache_command(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """tmp/.uv_cache is removed with tmp/; the shared uv cache is never touched (#1094)."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "tmp" / ".uv_cache").mkdir(parents=True)
        (tmp_path / "tmp" / ".uv_cache" / "x").write_text("", encoding="utf-8")

        with (
            patch("tools.doit.maintenance.subprocess.run") as mock_run,
            patch("tools.doit.maintenance.subprocess.check_call") as mock_call,
        ):
            _run(task_cleanup)

        assert not (tmp_path / "tmp" / ".uv_cache").exists()
        assert mock_run.call_count == 0
        assert mock_call.call_count == 0


class TestUpdateDepsEnvironment:
    @staticmethod
    def _envs(monkeypatch: pytest.MonkeyPatch, value: str | None) -> list[dict[str, str] | None]:
        if value is None:
            monkeypatch.delenv("UV_CACHE_DIR", raising=False)
        else:
            monkeypatch.setenv("UV_CACHE_DIR", value)
        with patch("tools.doit.maintenance.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1  # stop after the sync
            with pytest.raises(SystemExit):
                _run(task_update_deps)
        return [call.kwargs.get("env") for call in mock_run.call_args_list]

    def test_unset_injects_no_cache_dir(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for env in self._envs(monkeypatch, None):
            assert env is None or "UV_CACHE_DIR" not in env

    def test_a_set_value_is_inherited(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        value = str(tmp_path / "cache")
        envs = self._envs(monkeypatch, value)
        assert envs
        for env in envs:
            assert env is None or env["UV_CACHE_DIR"] == value


class TestCompletionsInstall:
    @pytest.mark.parametrize("name", _PATH_NAMES)
    def test_prints_the_paths_verbatim(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        name: str,
    ) -> None:
        """The shell config files, then the lines to add by hand once both are set up."""
        home = tmp_path / name / "home"
        home.mkdir(parents=True)
        for rc in (".bashrc", ".zshrc"):
            (home / rc).write_text("", encoding="utf-8")
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("USERPROFILE", str(home))  # what expanduser reads on Windows
        project = tmp_path / name / "project"
        (project / "completions").mkdir(parents=True)
        for script in ("doit.bash", "doit.zsh"):
            (project / "completions" / script).write_text("", encoding="utf-8")
        monkeypatch.chdir(project)
        monkeypatch.setenv("COLUMNS", "1000")

        _run(task_completions_install)  # adds the lines
        _run(task_completions_install)  # finds them, and prints them for adding by hand

        out = _ANSI.sub("", capsys.readouterr().out)
        lines = out.splitlines()
        for rc in (".bashrc", ".zshrc"):
            assert f"✓ Added to {os.path.join(home, rc)}" in lines
            assert f"Already in {os.path.join(home, rc)}" in lines
        completions = os.path.join(os.path.abspath(os.getcwd()), "completions")
        assert f'source "{os.path.join(completions, "doit.bash")}"  (Bash)' in out
        assert f'source "{os.path.join(completions, "doit.zsh")}"   (Zsh)' in out

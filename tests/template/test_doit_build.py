"""Tests for tools/doit/build.py's `wheel_check` task (issue #837).

`_check_wheel` installs the exact wheel that will ship into a throwaway venv,
imports it, and runs every console script with `--help` — catching a
packaging regression (missing module, broken entry point, missing
`py.typed`) that unit tests of the source tree cannot see.

The integration tests below build synthetic, installable wheels with
`zipfile` and exercise the real `uv venv` / `uv pip install` toolchain
against them. This stays hermetic per `tests/test_hermetic_suite.py` and
`tests/conftest.py`: the wheels carry no dependencies, so the install resolves
nothing from an index, and nothing reaches the network or a real `gh`.
"""

from __future__ import annotations

import subprocess  # nosec B404 - the point of this module is to drive subprocess-based checks
import zipfile
from pathlib import Path

import pytest

from tools.doit import build as build_mod
from tools.doit.build import (
    _check_wheel,
    _find_wheel,
    _import_name,
    _missing_py_typed,
    _scripts,
    _snapshot_source_tree,
    _venv_python,
    _venv_script,
)


def _write_pyproject(
    root: Path,
    *,
    import_name: str = "foo_pkg",
    package_dir: str | None = None,
    scripts: dict[str, str] | None = None,
) -> None:
    """Write a minimal `pyproject.toml` at ``root`` for `_check_wheel` to read."""
    package_dir = package_dir if package_dir is not None else f"src/{import_name}"
    scripts = {} if scripts is None else scripts
    scripts_toml = "\n".join(f'"{name}" = "{target}"' for name, target in scripts.items())
    content = f"""\
[project]
name = "{import_name.replace("_", "-")}"
version = "0.1.0"

[project.scripts]
{scripts_toml}

[tool.hatch.build.targets.wheel]
packages = ["{package_dir}"]
"""
    (root / "pyproject.toml").write_text(content, encoding="utf-8")


def _build_wheel(
    dist_dir: Path,
    *,
    import_name: str = "foo_pkg",
    version: str = "0.1.0",
    include_py_typed: bool = True,
    include_package: bool = True,
    entry_points: dict[str, str] | None = None,
) -> Path:
    """Build a minimal, installable wheel by hand with `zipfile`.

    ``entry_points`` maps a console-script name to its `module:function`
    target string verbatim — the function need not exist, which is how the
    broken-entry-point test is constructed. A `RECORD` listing every member
    is required: `uv pip install` refused an otherwise-valid wheel without
    one during manual verification for this issue.
    """
    dist_dir.mkdir(parents=True, exist_ok=True)
    whl_path = dist_dir / f"{import_name}-{version}-py3-none-any.whl"
    dist_info = f"{import_name}-{version}.dist-info"

    members: dict[str, bytes] = {}
    if include_package:
        members[f"{import_name}/__init__.py"] = f'__version__ = "{version}"\n'.encode()
        members[f"{import_name}/cli.py"] = b"def main():\n    print('hi')\n"
        if include_py_typed:
            members[f"{import_name}/py.typed"] = b""

    members[f"{dist_info}/METADATA"] = (
        f"Metadata-Version: 2.1\nName: {import_name.replace('_', '-')}\nVersion: {version}\n"
    ).encode()
    members[f"{dist_info}/WHEEL"] = (
        b"Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    )
    if entry_points:
        lines = "\n".join(f"{name} = {target}" for name, target in entry_points.items())
        members[f"{dist_info}/entry_points.txt"] = f"[console_scripts]\n{lines}\n".encode()

    record_name = f"{dist_info}/RECORD"
    record_lines = "\n".join(f"{name},," for name in members) + f"\n{record_name},,\n"
    members[record_name] = record_lines.encode()

    with zipfile.ZipFile(whl_path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)

    return whl_path


def _git(repo: Path, *args: str) -> str:
    """Run ``git`` in ``repo`` with a fixed identity and no signing; return stdout."""
    result = subprocess.run(  # nosec B603 B607 - fixed argv, no shell
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        capture_output=True,
        text=True,
        check=True,
        cwd=repo,
    )
    return result.stdout


def _init_repo(repo: Path) -> None:
    """Make ``repo`` a git repository with its current files committed."""
    _git(repo, "init", "--quiet")
    _git(repo, "add", "--all")
    _git(repo, "commit", "--quiet", "--allow-empty", "-m", "init")


class TestCheckWheelIntegration:
    """`_check_wheel` against real, synthetic wheels (slow: real `uv venv`/install)."""

    def test_good_wheel_passes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        _write_pyproject(tmp_path, scripts={"foo-cli": "foo_pkg.cli:main"})
        dist_dir = tmp_path / "dist"
        _build_wheel(dist_dir, entry_points={"foo-cli": "foo_pkg.cli:main"})

        failures = _check_wheel(str(dist_dir))

        assert failures == []

    def test_missing_py_typed_fails_and_names_the_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        _write_pyproject(tmp_path)
        dist_dir = tmp_path / "dist"
        _build_wheel(dist_dir, include_py_typed=False)

        failures = _check_wheel(str(dist_dir))

        assert any("foo_pkg/py.typed" in f for f in failures), failures

    def test_entry_point_naming_missing_function_fails_and_names_script(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        _write_pyproject(tmp_path, scripts={"foo-cli": "foo_pkg.cli:nope"})
        dist_dir = tmp_path / "dist"
        _build_wheel(dist_dir, entry_points={"foo-cli": "foo_pkg.cli:nope"})

        failures = _check_wheel(str(dist_dir))

        assert any("foo-cli" in f for f in failures), failures

    def test_missing_package_dir_fails_import(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        _write_pyproject(tmp_path)
        dist_dir = tmp_path / "dist"
        _build_wheel(dist_dir, include_package=False)

        failures = _check_wheel(str(dist_dir))

        assert any("importing" in f and "foo_pkg" in f for f in failures), failures


class TestCheckWheelBuildsWhenNoDistGiven:
    """With no ``--dist``, `_check_wheel` must build a wheel itself first."""

    def test_builds_then_checks_the_result(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        _write_pyproject(tmp_path, scripts={"foo-cli": "foo_pkg.cli:main"})
        _init_repo(tmp_path)
        real_run = build_mod.subprocess.run

        def fake_run(
            cmd: list[str],
            capture_output: bool = False,
            text: bool = False,
            check: bool = False,
            cwd: Path | None = None,
        ) -> subprocess.CompletedProcess[str]:
            if cmd[:2] == ["uv", "build"]:
                out_dir = Path(cmd[cmd.index("--out-dir") + 1])
                _build_wheel(out_dir, entry_points={"foo-cli": "foo_pkg.cli:main"})
                return subprocess.CompletedProcess(cmd, 0, "", "")
            return real_run(cmd, capture_output=capture_output, text=text, check=check, cwd=cwd)

        monkeypatch.setattr(build_mod.subprocess, "run", fake_run)

        failures = _check_wheel("")

        assert failures == []

    def test_build_failure_is_reported(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        _write_pyproject(tmp_path)
        _init_repo(tmp_path)
        real_run = build_mod.subprocess.run

        def fake_run(
            cmd: list[str],
            capture_output: bool = False,
            text: bool = False,
            check: bool = False,
            cwd: Path | None = None,
        ) -> subprocess.CompletedProcess[str]:
            if cmd[:2] == ["uv", "build"]:
                return subprocess.CompletedProcess(cmd, 1, "", "boom")
            if cmd[0] == "git":
                return real_run(cmd, capture_output=capture_output, text=text, check=check, cwd=cwd)
            raise AssertionError(f"unexpected cmd: {cmd}")

        monkeypatch.setattr(build_mod.subprocess, "run", fake_run)

        failures = _check_wheel("")

        assert len(failures) == 1
        assert "uv build --wheel" in failures[0]
        assert "boom" in failures[0]

    def test_builds_from_snapshot_not_source_tree(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The build runs in a snapshot, so its version hook cannot rewrite `src/` (#937)."""
        monkeypatch.chdir(tmp_path)
        _write_pyproject(tmp_path, scripts={"foo-cli": "foo_pkg.cli:main"})
        (tmp_path / ".gitignore").write_text("_version.py\n", encoding="utf-8")
        version_file = tmp_path / "src" / "foo_pkg" / "_version.py"
        version_file.parent.mkdir(parents=True)
        version_file.write_text("__version__ = 'old'\n", encoding="utf-8")
        _init_repo(tmp_path)
        real_run = build_mod.subprocess.run
        build_cwds: list[Path] = []

        def fake_run(
            cmd: list[str],
            capture_output: bool = False,
            text: bool = False,
            check: bool = False,
            cwd: Path | None = None,
        ) -> subprocess.CompletedProcess[str]:
            if cmd[:2] == ["uv", "build"]:
                assert cwd is not None
                build_cwds.append(cwd)
                # Stand in for hatch-vcs: rewrite the version file where the build runs.
                (cwd / "src" / "foo_pkg").mkdir(parents=True, exist_ok=True)
                (cwd / "src" / "foo_pkg" / "_version.py").write_text(
                    "__version__ = 'new'\n", encoding="utf-8"
                )
                out_dir = Path(cmd[cmd.index("--out-dir") + 1])
                _build_wheel(out_dir, entry_points={"foo-cli": "foo_pkg.cli:main"})
                return subprocess.CompletedProcess(cmd, 0, "", "")
            return real_run(cmd, capture_output=capture_output, text=text, check=check, cwd=cwd)

        monkeypatch.setattr(build_mod.subprocess, "run", fake_run)

        failures = _check_wheel("")

        assert failures == []
        assert len(build_cwds) == 1
        assert build_cwds[0].resolve() != tmp_path.resolve()
        assert version_file.read_text(encoding="utf-8") == "__version__ = 'old'\n"

    def test_not_a_git_repo_is_reported(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        _write_pyproject(tmp_path)
        monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))

        failures = _check_wheel("")

        assert len(failures) == 1
        assert "could not snapshot the source tree" in failures[0]


class TestSnapshotSourceTree:
    """`_snapshot_source_tree` copies the working tree into a clone at the same commit."""

    def _make_repo(self, root: Path) -> Path:
        repo = root / "repo"
        repo.mkdir()
        (repo / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
        (repo / "tracked.txt").write_text("committed\n", encoding="utf-8")
        (repo / "deleted.txt").write_text("gone soon\n", encoding="utf-8")
        (repo / "pkg").mkdir()
        (repo / "pkg" / "mod.py").write_text("x = 1\n", encoding="utf-8")
        _init_repo(repo)
        return repo

    def test_copies_working_tree_state(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = self._make_repo(tmp_path)
        (repo / "tracked.txt").write_text("edited\n", encoding="utf-8")
        (repo / "untracked.txt").write_text("new\n", encoding="utf-8")
        (repo / "ignored.txt").write_text("secret\n", encoding="utf-8")
        (repo / "deleted.txt").unlink()
        monkeypatch.chdir(repo)
        dest = tmp_path / "snapshot"

        _snapshot_source_tree(dest)

        assert (dest / "tracked.txt").read_text(encoding="utf-8") == "edited\n"
        assert (dest / "untracked.txt").read_text(encoding="utf-8") == "new\n"
        assert (dest / "pkg" / "mod.py").read_text(encoding="utf-8") == "x = 1\n"
        assert not (dest / "ignored.txt").exists()
        assert not (dest / "deleted.txt").exists()

    def test_snapshot_is_at_source_head(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = self._make_repo(tmp_path)
        _git(repo, "tag", "v1.2.3")
        monkeypatch.chdir(repo)
        dest = tmp_path / "snapshot"

        _snapshot_source_tree(dest)

        assert _git(dest, "rev-parse", "HEAD") == _git(repo, "rev-parse", "HEAD")
        assert _git(dest, "describe", "--tags").strip() == "v1.2.3"
        assert _git(dest, "status", "--porcelain", "--untracked-files=no") == ""

    def test_source_index_is_not_written(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = self._make_repo(tmp_path)
        (repo / "tracked.txt").write_text("edited\n", encoding="utf-8")
        index = repo / ".git" / "index"
        before = index.read_bytes()
        monkeypatch.chdir(repo)

        _snapshot_source_tree(tmp_path / "snapshot")

        assert index.read_bytes() == before

    def test_not_a_git_repo_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))

        with pytest.raises(ValueError, match="git rev-parse HEAD"):
            _snapshot_source_tree(tmp_path / "snapshot")


class TestImportName:
    """`_import_name` prefers the hatch wheel packages list over `project.name`."""

    def test_uses_hatch_wheel_packages_last_segment(self) -> None:
        pyproject = {
            "project": {"name": "something-else"},
            "tool": {"hatch": {"build": {"targets": {"wheel": {"packages": ["src/real_pkg"]}}}}},
        }
        assert _import_name(pyproject) == "real_pkg"

    def test_falls_back_to_normalized_project_name(self) -> None:
        pyproject = {"project": {"name": "my-cool-pkg"}}
        assert _import_name(pyproject) == "my_cool_pkg"

    def test_empty_packages_list_falls_back(self) -> None:
        pyproject = {
            "project": {"name": "my-cool-pkg"},
            "tool": {"hatch": {"build": {"targets": {"wheel": {"packages": []}}}}},
        }
        assert _import_name(pyproject) == "my_cool_pkg"


class TestScripts:
    def test_returns_sorted_script_names(self) -> None:
        pyproject = {"project": {"scripts": {"b-cli": "x:y", "a-cli": "x:z"}}}
        assert _scripts(pyproject) == ["a-cli", "b-cli"]

    def test_empty_when_no_scripts_table(self) -> None:
        assert _scripts({"project": {"name": "foo"}}) == []


class TestFindWheel:
    def test_zero_wheels_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match=r"no \*\.whl found"):
            _find_wheel(tmp_path)

    def test_one_wheel_returns_it(self, tmp_path: Path) -> None:
        wheel = tmp_path / "pkg-0.1.0-py3-none-any.whl"
        wheel.write_bytes(b"")
        assert _find_wheel(tmp_path) == wheel

    def test_two_wheels_raises(self, tmp_path: Path) -> None:
        (tmp_path / "pkg-0.1.0-py3-none-any.whl").write_bytes(b"")
        (tmp_path / "pkg-0.2.0-py3-none-any.whl").write_bytes(b"")
        with pytest.raises(ValueError, match="found 2"):
            _find_wheel(tmp_path)

    def test_non_wheel_files_are_ignored(self, tmp_path: Path) -> None:
        (tmp_path / "sbom.json").write_text("{}", encoding="utf-8")
        (tmp_path / "pkg-0.1.0.tar.gz").write_bytes(b"")
        wheel = tmp_path / "pkg-0.1.0-py3-none-any.whl"
        wheel.write_bytes(b"")
        assert _find_wheel(tmp_path) == wheel


class TestMissingPyTyped:
    def test_present_returns_none(self, tmp_path: Path) -> None:
        wheel = tmp_path / "pkg-0.1.0-py3-none-any.whl"
        with zipfile.ZipFile(wheel, "w") as zf:
            zf.writestr("foo_pkg/py.typed", "")
        assert _missing_py_typed(wheel, "foo_pkg") is None

    def test_absent_returns_expected_path(self, tmp_path: Path) -> None:
        wheel = tmp_path / "pkg-0.1.0-py3-none-any.whl"
        with zipfile.ZipFile(wheel, "w") as zf:
            zf.writestr("foo_pkg/__init__.py", "")
        assert _missing_py_typed(wheel, "foo_pkg") == "foo_pkg/py.typed"


class TestVenvPaths:
    def test_venv_python_posix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(build_mod.platform, "system", lambda: "Linux")
        assert _venv_python(Path("/fake/venv")) == Path("/fake/venv/bin/python")

    def test_venv_python_windows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(build_mod.platform, "system", lambda: "Windows")
        assert _venv_python(Path("C:/venv")) == Path("C:/venv/Scripts/python.exe")

    def test_venv_script_posix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(build_mod.platform, "system", lambda: "Linux")
        assert _venv_script(Path("/fake/venv"), "foo-cli") == Path("/fake/venv/bin/foo-cli")

    def test_venv_script_windows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(build_mod.platform, "system", lambda: "Windows")
        assert _venv_script(Path("C:/venv"), "foo-cli") == Path("C:/venv/Scripts/foo-cli.exe")

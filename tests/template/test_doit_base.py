"""Tests for tools/doit/base.py helpers."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from doit.exceptions import TaskFailed
from rich.console import Console

from tools.doit.base import (
    install_check_or_skip,
    optional_root_dirs,
    optional_root_files,
    verbatim,
    warn_if_env_drifted,
)


class TestWarnIfEnvDrifted:
    """``warn_if_env_drifted`` warns but never fails (#1033).

    Replaces the ``uv-sync-on-pull``/``uv-sync-on-checkout`` pre-commit hooks,
    which auto-ran ``uv sync`` on ``git checkout``/``git pull`` before anyone
    had reviewed the branch. This runs only when a developer runs ``doit
    check``/``doit test`` themselves, and only warns -- it never syncs.
    """

    def test_runs_the_check_only_command(self) -> None:
        """The subprocess call is ``uv sync --all-extras --dev --check``, never a real sync."""
        with patch("tools.doit.base.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            warn_if_env_drifted()

        mock_run.assert_called_once_with(
            ["uv", "sync", "--all-extras", "--dev", "--check"],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_in_sync_prints_nothing(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Exit 0 (environment matches ``uv.lock``) -> no output."""
        with patch("tools.doit.base.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            warn_if_env_drifted()

        assert capsys.readouterr().out == ""

    def test_out_of_sync_prints_the_reminder_and_does_not_raise(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Non-zero exit (drifted) -> the reminder prints and the function returns normally."""
        with patch("tools.doit.base.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            warn_if_env_drifted()  # must not raise

        assert (
            "environment does not match uv.lock — run: doit install_dev" in capsys.readouterr().out
        )

    def test_reminder_does_not_claim_uv_lock_changed(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Drift is environment vs lock, so the message must not say the lock changed."""
        with patch("tools.doit.base.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            warn_if_env_drifted()

        assert "uv.lock changed" not in capsys.readouterr().out


def _touch(tmp_path: Path, rel: str) -> Path:
    """Create ``rel`` under ``tmp_path`` and return the absolute path."""
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("", encoding="utf-8")
    return target


class TestOptionalRootFiles:
    """Tests for the ``optional_root_files`` helper."""

    def test_empty_input_returns_empty_string(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No names -> empty string (safe to concatenate)."""
        monkeypatch.chdir(tmp_path)
        assert optional_root_files() == ""

    def test_missing_file_returns_empty_string(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Absent candidate -> empty string."""
        monkeypatch.chdir(tmp_path)
        assert optional_root_files("bootstrap.py") == ""

    def test_present_file_returns_space_prefixed_name(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Existing file -> ``' bootstrap.py'`` (single leading space)."""
        monkeypatch.chdir(tmp_path)
        _touch(tmp_path, "bootstrap.py")

        result = optional_root_files("bootstrap.py")
        assert result == " bootstrap.py"
        # Exactly one leading space.
        assert result.startswith(" ")
        assert not result.startswith("  ")

    def test_two_present_files_preserve_argument_order(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Multiple present names -> argument order preserved, single space separators."""
        monkeypatch.chdir(tmp_path)
        _touch(tmp_path, "a.py")
        _touch(tmp_path, "b.py")

        assert optional_root_files("a.py", "b.py") == " a.py b.py"
        # Swapping the argument order swaps the output order too.
        assert optional_root_files("b.py", "a.py") == " b.py a.py"

    def test_mix_of_present_and_absent_filters_out_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Only the present names survive; missing ones are silently skipped."""
        monkeypatch.chdir(tmp_path)
        _touch(tmp_path, "a.py")

        assert optional_root_files("a.py", "missing.py") == " a.py"
        assert optional_root_files("missing.py", "a.py") == " a.py"

    def test_single_leading_space_and_separator(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Output uses exactly one leading space and one separator between names."""
        monkeypatch.chdir(tmp_path)
        _touch(tmp_path, "x.py")
        _touch(tmp_path, "y.py")

        result = optional_root_files("x.py", "y.py")
        # No double-spaces anywhere in the output.
        assert "  " not in result
        # Exactly two names separated by exactly one space.
        assert result == " x.py y.py"

    def test_directory_with_matching_name_is_not_treated_as_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A directory named ``bootstrap.py`` must not satisfy the is_file() guard."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "bootstrap.py").mkdir()

        assert optional_root_files("bootstrap.py") == ""


class TestOptionalRootDirs:
    """Tests for the ``optional_root_dirs`` helper (sibling of ``optional_root_files``)."""

    def test_empty_input_returns_empty_string(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No names -> empty string (safe to concatenate)."""
        monkeypatch.chdir(tmp_path)
        assert optional_root_dirs() == ""

    def test_missing_dir_returns_empty_string(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Absent candidate -> empty string."""
        monkeypatch.chdir(tmp_path)
        assert optional_root_dirs("examples") == ""

    def test_present_dir_returns_space_prefixed_name_with_trailing_slash(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Existing directory -> ``' examples/'`` (leading space, trailing slash)."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "examples").mkdir()

        result = optional_root_dirs("examples")
        assert result == " examples/"
        # Exactly one leading space.
        assert result.startswith(" ")
        assert not result.startswith("  ")

    def test_two_present_dirs_preserve_argument_order(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Multiple present names -> argument order preserved, single space separators."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()

        assert optional_root_dirs("a", "b") == " a/ b/"
        # Swapping the argument order swaps the output order too.
        assert optional_root_dirs("b", "a") == " b/ a/"

    def test_mix_of_present_and_absent_filters_out_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Only the present names survive; missing ones are silently skipped."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "a").mkdir()

        assert optional_root_dirs("a", "missing") == " a/"
        assert optional_root_dirs("missing", "a") == " a/"

    def test_file_with_matching_name_is_not_treated_as_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A file named ``examples`` must not satisfy the is_dir() guard."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "examples").write_text("", encoding="utf-8")

        assert optional_root_dirs("examples") == ""


# ---------------------------------------------------------------------------
# install_check_or_skip
# ---------------------------------------------------------------------------


_PROBE_HINT = "bandit not installed. Run: doit install_dev"


def _probe_result(returncode: int) -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess(args=[], returncode=returncode)


class TestInstallCheckOrSkip:
    """Tests for ``install_check_or_skip``, which runs without a POSIX shell (#1291).

    The probe is a Python ``subprocess.run`` with list arguments, so it works the same
    under cmd.exe and POSIX shells. ``subprocess.run`` is patched for the probe and the
    guarded command is a ``python -c`` one-liner, so nothing here needs ``uv`` or bash.
    """

    def test_probe_uses_project_venv_with_list_args_and_no_shell(self) -> None:
        """The probe imports the module via ``uv run --no-sync python`` (#1193)."""
        action = install_check_or_skip("bandit", _PROBE_HINT, "echo hi")
        with patch("tools.doit.base.subprocess.run", return_value=_probe_result(0)) as run:
            action.execute()
        argv = run.call_args.args[0]
        assert argv == ["uv", "run", "--no-sync", "python", "-c", "import bandit"]
        assert not run.call_args.kwargs.get("shell")
        assert run.call_args.kwargs["stdout"] == subprocess.DEVNULL
        assert run.call_args.kwargs["stderr"] == subprocess.DEVNULL

    def test_module_defaults_to_package_with_underscores(self) -> None:
        """Without ``module``, hyphens in the package name become underscores."""
        action = install_check_or_skip("pip-audit", "missing", "echo hi")
        with patch("tools.doit.base.subprocess.run", return_value=_probe_result(0)) as run:
            action.execute()
        assert run.call_args.args[0][-1] == "import pip_audit"

    def test_explicit_module_overrides_default(self) -> None:
        """An explicit ``module`` is imported instead of the derived name."""
        action = install_check_or_skip("pip-licenses", "missing", "echo hi", module="piplicenses")
        with patch("tools.doit.base.subprocess.run", return_value=_probe_result(0)) as run:
            action.execute()
        assert run.call_args.args[0][-1] == "import piplicenses"

    def test_not_installed_prints_hint_and_skips_command(self) -> None:
        """A failed probe writes the hint, returns None and never runs the command."""
        action = install_check_or_skip("bandit", _PROBE_HINT, "echo ran")
        out = StringIO()
        with (
            patch("tools.doit.base.subprocess.run", return_value=_probe_result(1)),
            patch("doit.action.subprocess.Popen") as popen,
        ):
            result = action.execute(out=out)
        assert result is None
        assert _PROBE_HINT in out.getvalue()
        assert action.out is not None
        assert _PROBE_HINT in action.out
        popen.assert_not_called()

    def test_not_installed_without_out_stream_still_passes(self) -> None:
        """``out=None`` (doit's default) must not break the skip path."""
        action = install_check_or_skip("bandit", _PROBE_HINT, "echo ran")
        with patch("tools.doit.base.subprocess.run", return_value=_probe_result(1)):
            assert action.execute() is None

    def test_installed_and_tool_succeeds_returns_none_without_hint(self) -> None:
        """A passing probe runs the command; success prints no hint."""
        command = f'"{sys.executable}" -c "print(42)"'
        action = install_check_or_skip("bandit", _PROBE_HINT, command)
        out = StringIO()
        with patch("tools.doit.base.subprocess.run", return_value=_probe_result(0)):
            result = action.execute(out=out)
        assert result is None
        assert action.out is not None
        assert "42" in action.out
        assert _PROBE_HINT not in out.getvalue()

    def test_installed_and_tool_fails_propagates_failure(self) -> None:
        """A real tool failure is not masked: it is the bug fix from issue #527."""
        command = f'"{sys.executable}" -c "raise SystemExit(3)"'
        action = install_check_or_skip("bandit", _PROBE_HINT, command)
        with patch("tools.doit.base.subprocess.run", return_value=_probe_result(0)):
            result = action.execute()
        assert isinstance(result, TaskFailed)
        assert _PROBE_HINT not in (action.out or "")

    def test_str_is_the_command(self) -> None:
        """doit's ``title_with_actions`` prints ``str(action)``, so it shows the command."""
        action = install_check_or_skip("bandit", _PROBE_HINT, "uv run bandit -q")
        assert str(action) == "Cmd: uv run bandit -q"


DOIT_DIR = Path(__file__).resolve().parents[2] / "tools" / "doit"


def _install_hints() -> list[tuple[str, str | None]]:
    """Return (file:line, hint) for every ``install_check_or_skip`` call in ``tools/doit``.

    The hint is None when it is not a string literal, so the test can say so instead of
    skipping a hint it cannot read.
    """
    found: list[tuple[str, str | None]] = []
    for module in sorted(DOIT_DIR.glob("*.py")):
        for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "install_check_or_skip"
            ):
                continue
            hints = node.args[1:2] + [kw.value for kw in node.keywords if kw.arg == "hint"]
            hint = hints[0] if hints else None
            value = hint.value if isinstance(hint, ast.Constant) else None
            text = value if isinstance(value, str) else None
            found.append((f"{module.name}:{node.lineno}", text))
    return found


class TestInstallHints:
    """Every install hint in ``tools/doit`` names ``doit install_dev`` (#889).

    The tools the hints ask for are in the ``dev`` and ``security`` extras, and ``uv sync``
    uninstalls every extra it is not asked for. The hints said ``uv sync`` and
    ``uv sync --extra security``, and following either one uninstalled ``doit``, the tool
    that printed the hint.
    """

    def test_the_scan_finds_hints(self) -> None:
        assert _install_hints(), f"no install_check_or_skip calls found in {DOIT_DIR}"

    def test_every_hint_names_install_dev(self) -> None:
        wrong = [
            f"{where}: {hint!r}"
            for where, hint in _install_hints()
            if hint is None or not hint.endswith("Run: doit install_dev")
        ]
        assert not wrong, (
            "these install hints do not end in 'Run: doit install_dev' "
            "(None means the hint is not a string literal):\n  " + "\n  ".join(wrong)
        )


class TestVerbatim:
    """Tests for the ``verbatim`` helper (#914)."""

    @pytest.mark.parametrize(
        "text",
        [
            r"C:\notes\[1].md",  # a backslash before a [ that opens no tag
            r"C:\notes\[Draft].md",
            "[/x] and [red]",  # tags
            ":memo: :sparkles:",  # emoji shortcodes
        ],
    )
    def test_prints_the_text_as_given(self, text: str) -> None:
        # color_system=None: no ANSI codes, even when FORCE_COLOR is set.
        console = Console(file=StringIO(), soft_wrap=True, color_system=None)

        console.print(verbatim(text, "red"))

        assert console.file.getvalue() == f"{text}\n"  # type: ignore[attr-defined]

    def test_applies_the_style_to_the_whole_text(self) -> None:
        text = verbatim("Stderr: [x]", "bold red")

        assert text.plain == "Stderr: [x]"
        assert text.style == "bold red"


class TestNoUvCacheDefault:
    """Importing base.py leaves uv's cache alone, so uv's shared default applies (#1094)."""

    @staticmethod
    def _imported_value(env_value: str | None) -> str:
        env = {k: v for k, v in os.environ.items() if k != "UV_CACHE_DIR"}
        if env_value is not None:
            env["UV_CACHE_DIR"] = env_value
        code = (
            "import os; import tools.doit.base as b; "
            "print(repr(os.environ.get('UV_CACHE_DIR'))); "
            "print(hasattr(b, 'UV_CACHE_DIR'))"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            env=env,
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(__file__).resolve().parents[2],
        )
        return result.stdout

    def test_unset_stays_unset(self) -> None:
        assert self._imported_value(None).splitlines()[0] == "None"

    def test_a_set_value_is_unchanged(self, tmp_path: Path) -> None:
        value = str(tmp_path / "cache")
        assert self._imported_value(value).splitlines()[0] == repr(value)

    def test_no_longer_exports_the_constant(self) -> None:
        assert self._imported_value(None).splitlines()[1] == "False"

    def test_envrc_leaves_uv_cache_unset(self) -> None:
        """direnv must not point uv or pre-commit at a per-checkout cache.

        The other tool caches stay in tmp/.
        """
        envrc = (Path(__file__).resolve().parents[2] / ".envrc").read_text(encoding="utf-8")
        exports = {
            line.split("=", 1)[0].split()[-1]: line
            for line in envrc.splitlines()
            if line.strip().startswith("export ")
        }
        assert "UV_CACHE_DIR" not in exports
        assert "PRE_COMMIT_HOME" not in exports
        for name in ("RUFF_CACHE_DIR", "MYPY_CACHE_DIR", "COVERAGE_FILE"):
            assert "/tmp/" in exports[name], name

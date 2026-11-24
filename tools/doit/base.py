"""Base utilities and configuration for doit tasks."""

import os
import subprocess  # nosec B404  # subprocess is required to run doit sub-tasks
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import TextIO

from doit.action import CmdAction
from doit.exceptions import TaskError, TaskFailed
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# Configuration
DOIT_CONFIG = {
    "verbosity": 2,
    "default_tasks": ["default"],
}


def success_message() -> None:
    """Print success message after all checks pass."""
    console = Console()
    console.print()
    console.print(
        Panel.fit(
            "[bold green]✓ All checks passed![/bold green]", border_style="green", padding=(1, 2)
        )
    )
    console.print()


def verbatim(text: str, style: str = "") -> Text:
    """Wrap text a task did not write, so the console prints it exactly as given.

    Rich reads a ``str`` passed to ``console.print`` or ``Panel`` as markup, and replaces
    emoji shortcodes such as ``:memo:``. ``rich.markup.escape()`` only stops a ``[`` from
    opening a tag. Rich still drops a backslash before a ``[`` that does not open one, and
    still replaces the shortcodes (#914). A ``Text`` is neither parsed nor replaced.

    Use it for command output, exceptions, commit subjects, PR titles, and paths or flag
    values from the user.

    Args:
        text: The text to print.
        style: A Rich style for the whole text, such as ``"red"`` or ``"bold cyan"``.

    Returns:
        ``text`` as a ``Text`` with ``style``.
    """
    return Text(text, style=style)


def optional_root_files(*names: str) -> str:
    """Return a shell-ready, space-prefixed suffix of existing root-level files.

    Builds a string such as ``" bootstrap.py"`` (leading space, space-separated)
    containing only the names that exist as files at the current working
    directory. Missing names are silently skipped; argument order is preserved
    for the names that survive.

    Designed for safe concatenation onto an existing command string used in a
    ``doit`` task action, so tasks can reference root-level files (e.g.
    ``bootstrap.py``) that are present in the template but deleted by the
    consumer-project cleanup step. Empty input or no surviving names yields
    ``""``, making concatenation a no-op.

    Args:
        *names: Candidate filenames at the current working directory.

    Returns:
        ``""`` when no names survive, otherwise ``" " + " ".join(survivors)``.
    """
    survivors = [name for name in names if Path(name).is_file()]
    if not survivors:
        return ""
    return " " + " ".join(survivors)


def optional_root_dirs(*names: str) -> str:
    """Return a shell-ready, space-prefixed suffix of existing root-level directories.

    Sibling of :func:`optional_root_files` with the same contract, but tests
    ``Path(name).is_dir()`` instead of ``is_file()``. Builds a string such as
    ``" examples/"`` (leading space, space-separated, each survivor suffixed
    with a trailing slash) containing only the names that exist as
    directories at the current working directory. Missing names are silently
    skipped; argument order is preserved for the names that survive.

    Designed for safe concatenation onto an existing command string used in a
    ``doit`` task action, so tasks can reference root-level directories (e.g.
    ``examples/``) that are present in the template but deleted by the
    consumer-project cleanup step. Empty input or no surviving names yields
    ``""``, making concatenation a no-op.

    Args:
        *names: Candidate directory names at the current working directory,
            given without a trailing slash (e.g. ``"examples"``).

    Returns:
        ``""`` when no names survive, otherwise
        ``" " + " ".join(f"{name}/" for name in survivors)``.
    """
    survivors = [name for name in names if Path(name).is_dir()]
    if not survivors:
        return ""
    return " " + " ".join(f"{name}/" for name in survivors)


def _module_installed(module: str) -> bool:
    """Return whether ``module`` imports in the project ``.venv``.

    Runs ``uv run --no-sync python -c "import <module>"`` with list arguments and no
    shell, so the probe behaves the same under cmd.exe and POSIX shells. It does not use
    ``uv pip show``: that honours ``UV_PYTHON`` and inspects whatever interpreter it names,
    so it reported tools missing from ``.venv`` as absent (or present when they were not).
    See issue #1193.

    Args:
        module: The importable module name.

    Returns:
        ``True`` when the import succeeds.
    """
    result = subprocess.run(
        ["uv", "run", "--no-sync", "python", "-c", f"import {module}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


# ``CmdAction`` ships no type information, so mypy sees ``Any`` as the base class. That is a
# ``misc`` error only under ``disallow_subclassing_any``; ``unused-ignore`` keeps a project that
# turns it off but keeps ``warn_unused_ignores`` from failing on this line.
class _GuardedCmdAction(CmdAction):  # type: ignore[misc, unused-ignore]  # doit has no stubs
    """A ``CmdAction`` that skips itself, with a hint, when its tool is not installed."""

    def __init__(self, command: str, module: str, hint: str) -> None:
        super().__init__(command)
        self._module = module
        self._hint = hint

    def execute(
        self, out: TextIO | None = None, err: TextIO | None = None
    ) -> TaskFailed | TaskError | None:
        """Run the command, or print the hint and pass when the module is missing.

        Returns:
            ``None`` when skipped or when the command succeeds, otherwise the failure
            ``CmdAction`` reports, so the tool's exit code reaches doit unmasked (#527).
        """
        if not _module_installed(self._module):
            text = self._hint + "\n"
            if out is not None:
                out.write(text)
            self.out = text
            self.err = ""
            self.result = text
            return None
        result: TaskFailed | TaskError | None = super().execute(out, err)
        return result


def install_check_or_skip(
    package: str, hint: str, command: str, *, module: str | None = None
) -> CmdAction:
    """Build a doit action that runs ``command`` only when ``package`` is installed.

    When the package's module cannot be imported, the action prints ``hint`` and passes,
    so a missing optional extra does not fail the task. When it can, the action runs
    ``command`` and its real exit code reaches the operator unmasked. Replaces the
    ``cmd || echo 'not installed'`` pattern, which always swallowed real failures. See
    issue #527.

    The probe runs in Python (see :func:`_module_installed`), not in a shell snippet
    prefixed to ``command``: the snippet used ``/dev/null`` and ``|| { ...; }``, which
    cmd.exe cannot parse. ``command`` itself still runs through the platform shell, so it
    must be written for both cmd.exe and POSIX shells, so it uses double quotes,
    never single. See issue #1291.

    Args:
        package: The distribution name (e.g. ``"bandit"``, ``"cyclonedx-bom"``).
            Used to derive ``module`` when that is not given.
        hint: Human-readable install instruction printed when the package is absent
            (e.g. ``"bandit not installed. Run: doit install_dev"``).
        command: The command to run when the package is installed.
        module: The importable module name when it differs from ``package`` with ``-``
            replaced by ``_`` (e.g. ``"piplicenses"`` for ``pip-licenses``).

    Returns:
        A doit ``CmdAction`` for use in a task's ``actions`` list.
    """
    module_name = module if module is not None else package.replace("-", "_")
    return _GuardedCmdAction(command, module_name, hint)


def warn_if_env_drifted() -> None:
    """Warn, but do not fail, when the environment has drifted from ``uv.lock``.

    Runs ``uv sync --all-extras --dev --check``, which exits non-zero when the
    installed environment no longer matches ``uv.lock`` (verified with uv
    0.9.8: exit 0 and "Would make no changes" in sync, non-zero otherwise).
    On a non-zero exit this prints a one-line reminder and returns — it never
    raises or calls ``sys.exit``, so the doit task that called it keeps going.

    This is the replacement for `uv-sync-on-pull`/`uv-sync-on-checkout`
    (#1033): those `post-merge`/`post-checkout` pre-commit hooks ran `uv sync`
    automatically on `git checkout`/`git pull`, before anyone had reviewed the
    branch. The code that reminds a developer to sync now runs only when they
    choose to run a `doit` task — `doit check` and `doit test` call this
    first — on a branch they have already decided to trust.
    """
    result = subprocess.run(
        ["uv", "sync", "--all-extras", "--dev", "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        console = Console()
        console.print(
            verbatim("environment does not match uv.lock — run: doit install_dev", "yellow"),
            soft_wrap=True,
        )


def _child_env(env: Mapping[str, str] | None) -> dict[str, str]:
    """Build the environment for a child process spawned by a streaming helper.

    Always sets ``PYTHONUNBUFFERED=1`` so Python children (including descendants
    like ``pytest``, ``mypy``, ``cz``) flush stdout line-by-line to pipes instead
    of block-buffering to process exit. Without this, streaming appears to work
    in tests that explicitly flush, but real tools — whose output is the whole
    point of streaming — deliver everything in one burst at process end.

    A caller-supplied ``PYTHONUNBUFFERED`` is respected.
    """
    merged = dict(env if env is not None else os.environ)
    merged.setdefault("PYTHONUNBUFFERED", "1")
    return merged


def run_streamed(
    cmd: list[str],
    *,
    env: Mapping[str, str] | None = None,
    check: bool = True,
    cwd: str | os.PathLike[str] | None = None,
) -> None:
    """Run a subprocess with stdout/stderr inherited from the parent.

    Unlike ``subprocess.run(..., capture_output=True)``, this function does not
    buffer output: the child process writes directly to the parent's stdout and
    stderr so the user sees progress live. This is the right choice for long-
    running steps whose output we do not need to parse (``doit check``,
    ``git pull``, ``git push``, ``git commit``, ``gh pr create``).

    Args:
        cmd: Command to run, as a list of args (no shell expansion).
        env: Optional environment mapping. If ``None``, the child inherits the
            parent's environment.
        check: When ``True`` (default), a non-zero exit raises
            ``subprocess.CalledProcessError``.
        cwd: Optional working directory for the child process.

    Raises:
        subprocess.CalledProcessError: If ``check`` is ``True`` and the child
            exits with a non-zero return code.
    """
    subprocess.run(
        cmd,
        env=_child_env(env),
        check=check,
        cwd=cwd,
    )


def run_teed(
    cmd: list[str],
    *,
    env: Mapping[str, str] | None = None,
    check: bool = True,
    cwd: str | os.PathLike[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess, streaming output to stdout while also capturing it.

    Merges stderr into stdout (so the captured buffer reflects interleaved
    output as a user would see it), streams each line to ``sys.stdout`` as it
    arrives, and returns a ``CompletedProcess`` whose ``stdout`` contains the
    full captured output. ``stderr`` is always empty because it was merged.

    This is the right choice when the caller both needs live output (long step,
    hooks, etc.) *and* needs to parse the output afterwards (e.g. regex-extract
    the version printed by ``cz bump``).

    On non-zero exit with ``check=True``, raises ``CalledProcessError`` with
    ``stdout`` populated so existing error-path logging keeps working.

    Args:
        cmd: Command to run, as a list of args (no shell expansion).
        env: Optional environment mapping. If ``None``, the child inherits the
            parent's environment.
        check: When ``True`` (default), a non-zero exit raises
            ``subprocess.CalledProcessError``.
        cwd: Optional working directory for the child process.

    Returns:
        ``subprocess.CompletedProcess[str]`` with ``stdout`` set to the full
        captured output and ``stderr`` set to ``""``.

    Raises:
        subprocess.CalledProcessError: If ``check`` is ``True`` and the child
            exits with a non-zero return code. The exception's ``stdout``
            attribute contains the captured output.
    """
    # Popen with stdout piped and stderr merged into stdout. We read lines
    # from the pipe, echo each to sys.stdout (so the user sees live output),
    # and buffer them for the caller.
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=_child_env(env),
        cwd=cwd,
        text=True,
        # bufsize=1 configures only the parent-side TextIOWrapper for reading
        # the pipe. Child-side flushing is controlled via PYTHONUNBUFFERED=1
        # in _child_env() — without it, Python children block-buffer to pipes.
        bufsize=1,
    )

    buffer: list[str] = []
    # process.stdout is non-None because we asked for subprocess.PIPE.
    assert process.stdout is not None  # invariant from Popen args
    try:
        for line in process.stdout:
            buffer.append(line)
            sys.stdout.write(line)
            sys.stdout.flush()
    except BaseException:
        # Streaming raised (broken parent stdout, KeyboardInterrupt, etc.).
        # Kill the child so wait() below doesn't hang waiting for a process
        # that may be blocked on a full pipe buffer.
        process.kill()
        raise
    finally:
        process.stdout.close()
        process.wait()

    returncode = process.returncode
    captured = "".join(buffer)

    if check and returncode != 0:
        raise subprocess.CalledProcessError(
            returncode=returncode,
            cmd=cmd,
            output=captured,
            stderr="",
        )

    return subprocess.CompletedProcess(
        args=cmd,
        returncode=returncode,
        stdout=captured,
        stderr="",
    )

"""The unit suite must not reach real external binaries (#710).

Before this, a full run invoked the real `gh` 18 times — 14 of them
`gh api user --jq .login`, a *network* call. Results then depended on whether the
developer happened to be authenticated, which is exactly the trap #689 spent time
diagnosing: a 0.54pp coverage difference between a maintainer's machine and CI,
caused by a branch that ran in one environment and not the other.

`tests/conftest.py::_hermetic_path` puts a stub `gh` ahead of the real one for
every test. These tests keep that fixture honest — that it is installed, that it
answers what the code under test calls, and that it is loud rather than silent
when something unmocked slips through.

Known limitation, stated rather than papered over: on Windows a PATH stub cannot
intercept ``subprocess.run(["gh", ...])`` from Python at all, because
``CreateProcess`` searches only ``gh`` and ``gh.exe`` and never consults
``PATHEXT`` for ``.CMD``. Shell scripts under test *are* covered there, because
Git Bash resolves the extensionless launcher. Python code that shells out should
mock ``subprocess.run`` — ``test_setup_repo.py`` already does for both token
branches — and this fixture is the backstop for everything else.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys  # nosec B404 - the point of this module is to inspect subprocess behaviour
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _stub_dir() -> Path:
    return Path(os.environ["PATH"].split(os.pathsep)[0])


def _run_gh(*args: str) -> subprocess.CompletedProcess[str]:
    """Exercise the stub's dispatch directly.

    Invoking bare ``gh`` would not work on Windows: ``CreateProcess`` searches
    only for ``gh`` and ``gh.exe``, never ``gh.CMD``, so a Python-level
    ``subprocess.run(["gh", ...])`` cannot be intercepted by a PATH stub there
    at all. Running the dispatch module keeps these assertions meaningful on
    every platform; the launchers are asserted separately.
    """
    return subprocess.run(  # nosec B603 - fixed argv, no shell
        [sys.executable, str(_stub_dir() / "_gh_stub.py"), *args],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_the_stub_is_ahead_of_any_real_gh() -> None:
    """`gh` must resolve into a pytest tmp dir, not to a system install."""
    resolved = shutil.which("gh")
    assert resolved is not None, "the stub should always be resolvable"
    assert "hermetic-bin" in resolved, (
        f"`gh` resolves to {resolved!r}, not the hermetic stub — the autouse "
        "fixture in conftest.py is not installed for this test"
    )


def test_the_stub_answers_what_the_code_under_test_calls() -> None:
    """The three commands the suite actually invokes must be handled."""
    assert _run_gh("--version").returncode == 0
    assert "stub" in _run_gh("--version").stdout

    auth = _run_gh("auth", "status")
    assert auth.returncode == 0
    # No token markers: `_check_token_permissions` must take its else branch.
    assert "github_pat_" not in auth.stderr + auth.stdout
    assert "gho_" not in auth.stderr + auth.stdout

    # Unauthenticated, so the statusline renders no user segment.
    assert _run_gh("api", "user", "--jq", ".login").returncode != 0


def test_an_unmocked_call_fails_loudly() -> None:
    """Anything the stub does not answer must fail visibly, not return success.

    A stub that silently exits 0 for unknown commands would let a new unmocked
    call pass while quietly doing nothing — the failure mode this whole backlog
    keeps finding.
    """
    result = _run_gh("pr", "create", "--title", "should never run")

    assert result.returncode == 127
    assert "HERMETIC-STUB" in result.stderr
    assert "#710" in result.stderr


def test_no_test_module_forwards_the_unfiltered_path() -> None:
    """A test that rebuilds `env` from `os.environ["PATH"]` inherits the stub.

    The statusline tests construct a minimal environment for the scripts they
    run. They must copy the *current* PATH — which the fixture has already
    prefixed — rather than reconstructing one from a hardcoded value.
    """
    needles = ('"PATH": "', "'PATH': '")
    offenders = []
    for path in sorted(REPO_ROOT.glob("tests/**/test_*.py")):
        if path.resolve() == Path(__file__).resolve():
            continue  # this module carries the needles as data, not as usage
        text = path.read_text(encoding="utf-8")
        if any(needle in text for needle in needles):
            offenders.append(str(path.relative_to(REPO_ROOT)))

    assert not offenders, (
        f"these tests hardcode a PATH instead of inheriting the hermetic one: {offenders}"
    )


def test_path_prefix_is_a_real_directory() -> None:
    """Guard against the fixture silently no-opping if tmp handling changes.

    Windows also needs `gh.CMD`: it resolves executables through PATHEXT, so an
    extensionless shell script is invisible to it. The first version of this
    fixture no-opped there and the suite kept calling the real binary — caught
    by `test_the_stub_is_ahead_of_any_real_gh` on the Windows CI cells.
    """
    first = Path(os.environ["PATH"].split(os.pathsep)[0])
    assert first.is_dir()
    assert (first / "_gh_stub.py").exists(), "the shared dispatch must be present"
    assert (first / "gh").exists(), "the POSIX/Git-Bash launcher must be present"
    if os.name == "nt":
        assert (first / "gh.CMD").exists(), "Windows needs a PATHEXT-resolvable launcher"

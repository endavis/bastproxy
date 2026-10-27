"""A doc that tells a developer to sync must not uninstall the development tools (#889).

The development tools, `doit` included, are the `dev` and `security` extras, and `uv sync`
uninstalls every extra it is not asked for. A plain `uv sync`, a `uv sync --dev` (which selects
dependency groups, and this project has none) or a `uv sync --extra security` therefore removes
the tools the reader is about to run. The docs told developers to run all three (#889).

Two checks keep them out:

- every `uv sync` in a fenced code block passes `--all-extras`, as `doit install_dev` does,
  unless the block is for an environment that only runs the program;
- no line suggests `uv sync --extra security`, except to say never to.

The allowlist holds the runtime syncs. Each entry says why its reader is not developing.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {
    ".git",
    ".venv",
    "site",
    "node_modules",
    "__pycache__",
    "tmp",
    ".mypy_cache",
    "worktrees",
}

# `uv sync` and its arguments, up to a shell operator, a comment or a closing quote.
SYNC = re.compile(r"\buv sync\b(?P<args>[^;&|#'\"`\n]*)")
SECURITY_ONLY = re.compile(r"\buv sync\b[^;&|#'\"`\n]*--extra[ =]security")

# (doc, fenced line) pairs whose reader runs the program rather than developing it.
RUNTIME_SYNCS: dict[tuple[str, str], str] = {
    ("docs/development/extensions.md", "RUN uv sync --no-dev"): "a production Dockerfile",
    ("docs/examples/api.md", "RUN uv sync --frozen --no-dev"): "a production Dockerfile",
    ("docs/development/doit-tasks-reference.md", "uv sync"): "the `install` task's equivalent",
    ("docs/development/release-and-automation.md", "uv sync"): "the run-the-program-only option",
}


def _markdown_files(root: Path) -> list[Path]:
    return [
        path
        for path in sorted(root.rglob("*.md"))
        if not any(part in SKIP_DIRS for part in path.relative_to(root).parts)
    ]


def _fenced_syncs(root: Path = REPO_ROOT) -> list[tuple[str, str]]:
    """Return (doc, line) for every line in a fenced code block that runs `uv sync`."""
    found: list[tuple[str, str]] = []
    for doc in _markdown_files(root):
        fenced = False
        for raw in doc.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if line.startswith("```"):
                fenced = not fenced
            elif fenced and not line.startswith("#") and SYNC.search(line.split(" #")[0]):
                found.append((doc.relative_to(root).as_posix(), line))
    return found


def _is_dev_sync(line: str) -> bool:
    return all("--all-extras" in match["args"].split() for match in SYNC.finditer(line))


def test_fenced_syncs_keep_the_dev_tools() -> None:
    wrong = [
        f"{doc}: {line}"
        for doc, line in _fenced_syncs()
        if not _is_dev_sync(line) and (doc, line) not in RUNTIME_SYNCS
    ]
    assert not wrong, (
        "these syncs uninstall the development tools:\n  "
        + "\n  ".join(wrong)
        + "\nUse `uv sync --all-extras --dev` for a first sync and `doit install_dev` after that,"
        " or add the line to RUNTIME_SYNCS with the reason its reader only runs the program."
    )


def test_no_doc_suggests_a_security_only_sync() -> None:
    """`uv sync --extra security` keeps that extra and uninstalls the `dev` one, `doit` included."""
    wrong = [
        f"{doc.relative_to(REPO_ROOT)}:{number}: {line.strip()}"
        for doc in _markdown_files(REPO_ROOT)
        for number, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), start=1)
        if SECURITY_ONLY.search(line) and "never" not in line.lower()
    ]
    assert not wrong, "these lines suggest a security-only sync:\n  " + "\n  ".join(wrong)


def test_the_scanner_finds_dev_syncs() -> None:
    """Guard the checks above against passing on a scan that matched nothing."""
    assert any(_is_dev_sync(line) for _, line in _fenced_syncs()), (
        "no fenced `uv sync --all-extras` found; the scanner is not matching"
    )


def test_runtime_syncs_are_still_used() -> None:
    """An entry whose line is gone is a suppression to drop. A deleted doc drops its entries."""
    found = set(_fenced_syncs())
    stale = [
        f"{doc}: {line}"
        for doc, line in RUNTIME_SYNCS
        if (REPO_ROOT / doc).is_file() and (doc, line) not in found
    ]
    assert not stale, "RUNTIME_SYNCS entries no longer in their docs:\n  " + "\n  ".join(stale)


def test_the_scanner_reads_only_fenced_commands(tmp_path: Path) -> None:
    doc = tmp_path / "docs" / "setup.md"
    doc.parent.mkdir()
    doc.write_text(
        "A plain `uv sync` uninstalls the tools.\n"
        "```bash\n"
        "# uv sync here is a comment\n"
        "uv sync  # removes the dev tools\n"
        "uv sync --all-extras --dev && doit check\n"
        "```\n"
        "uv sync outside a fence\n",
        encoding="utf-8",
    )
    copy = tmp_path / "worktrees" / "docs" / "889-x" / "setup.md"
    copy.parent.mkdir(parents=True)
    copy.write_text("```bash\nuv sync\n```\n", encoding="utf-8")

    found = _fenced_syncs(tmp_path)

    assert found == [
        ("docs/setup.md", "uv sync  # removes the dev tools"),
        ("docs/setup.md", "uv sync --all-extras --dev && doit check"),
    ]
    assert [_is_dev_sync(line) for _, line in found] == [False, True]

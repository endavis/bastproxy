"""A path named in the docs should exist, or be a declared placeholder.

`test_markdown_links.py` resolves link *targets* and `test_instruction_pointers.py`
resolves quoted section references and command names. Neither looks at a path
written in backticks in prose, which is how four stale references survived
long enough to be found by a manual sweep (#773):

- `.claude/claude.md` -- named four times, wrong case, and one of them an
  instruction to *verify* a file that does not exist under that name;
- `docs/installation.md`, `docs/usage.md`, `docs/api.md` in the migration guide,
  all three moved when the documentation was reorganised;
- `.github/workflows/tests.yml`, a workflow the reader was told to create;
- `.github/copilot/settings.json`, a settings file neither this repo nor the
  Copilot CLI has.

The allowlist below is the interesting half. A doc legitimately names paths that
do not exist -- placeholders substituted during setup, files created at runtime,
worked examples. Each entry states which, so the list stays a set of decisions
rather than a pile of suppressions.

Discovery is `doc_scan.committed_markdown_files()` -- git-tracked plus untracked-
but-not-ignored markdown -- rather than `rglob()` minus a hardcoded skip set. A
downstream project can also silence a path it deliberately did not adopt via
`.config/pyproject_template/sync-exclude.toml` (ADR-9026); upstream has no such
file, so that skip is a no-op here.
"""

from __future__ import annotations

import re
import subprocess  # nosec B404 - subprocess is required to build a test git repo
from pathlib import Path

from doc_scan import committed_markdown_files, is_excluded, load_sync_excludes

REPO_ROOT = Path(__file__).resolve().parents[1]

# A backticked path with a directory component and a known extension. Bare
# filenames ("run `configure.py`") are shorthand, not location claims, and are
# deliberately not checked.
DOCUMENTED_PATH = re.compile(r"`([A-Za-z0-9_./-]+\.(?:py|md|toml|yaml|yml|json|cfg|txt|sh))`")

# Allowlist entries that exist on a developer's machine but are never committed.
# They are exempt from the obsolescence check below: finding one on disk says
# nothing about whether a fresh checkout has it, and the whole point of listing
# them is that it does not.
NEVER_COMMITTED = frozenset({".claude/settings.local.json", "tmp/"})

# Paths that are allowed not to exist, and why.
ALLOWED: dict[str, str] = {
    # Substituted by configure.py when a project is created.
    "src/__PACKAGE_NAME__/": "package-name placeholder, substituted during setup",
    # Created at runtime, deliberately not checked in.
    ".config/pyproject_template/": "written by the management suite on first run",
    # Illustrative names in worked examples and templates.
    "path/to/": "generic example path",
    "src/generated/": "worked example in the rule-file READMEs (a downstream project)",
    "codegen/SKILL.md": "worked example in the rule-file READMEs",
    ".github/instructions/NAME.instructions.md": "a naming pattern, not a file",
    "tests/test_file.py": "generic example path",
    "tests/test_cache.py": "worked example in the AI walkthrough",
    "tests/test_farewell.py": "worked example in the add-a-feature tutorial",
    "tests/test_cli_farewell.py": "worked example in the add-a-feature tutorial",
    # Shorthand for a path under the user's home.
    "gh/hosts.yml": "shorthand for ~/.config/gh/hosts.yml",
    # Never committed, by policy. `.claude/settings.local.json` is blocked by the
    # `no-local-config` pre-commit hook; `tmp/` is generated output. Both exist on
    # a developer's machine and in no fresh checkout -- which is precisely why the
    # resolution below must not be satisfied by whatever happens to be on disk.
    ".claude/settings.local.json": "local config; the no-local-config hook blocks committing it",
    "tmp/": "generated artifacts and agent scratch space, gitignored",
    # AGENTS.md's before/after illustration of the temp-file convention.
    "/tmp/pr-body.md": "the 'wrong' half of the temp-file example",
    # Declared as future work.
    ".agents/skills.json": "Antigravity-side suppression, documented as planned",
    # Removed by #976; named in the ADR and consumer notes as what no longer exists.
    ".claude/commands/ghi-finalize.md": "historical reference to a file removed by #976",
}


def _markdown_files(root: Path = REPO_ROOT) -> list[Path]:
    return committed_markdown_files(root)


def _is_allowed(raw: str) -> bool:
    return any(raw.startswith(prefix) or raw == prefix for prefix in ALLOWED)


def _documented_paths(root: Path = REPO_ROOT) -> list[tuple[Path, str]]:
    """Return (doc, path) for every backticked path that claims a location."""
    found: list[tuple[Path, str]] = []
    for doc in _markdown_files(root):
        for match in DOCUMENTED_PATH.finditer(doc.read_text(encoding="utf-8", errors="replace")):
            raw = match.group(1)
            if "/" not in raw:
                continue  # bare filename: shorthand
            if raw.startswith(("http", "~", "{")) or "<" in raw or "*" in raw:
                continue
            found.append((doc, raw))
    return found


def _unallowed_missing(
    pairs: list[tuple[Path, str]], excludes: list[str], root: Path = REPO_ROOT
) -> set[str]:
    """Return "<doc>: <raw>" for every pair that is missing, unallowed and unexcluded."""
    return {
        f"{doc.relative_to(root)}: {raw}"
        for doc, raw in pairs
        if not _is_allowed(raw)
        and not is_excluded(raw, excludes)
        and not (root / raw).exists()
        and not (doc.parent / raw).exists()
    }


def test_documented_paths_exist() -> None:
    """A path in backticks should resolve, be a declared placeholder, or be excluded.

    A downstream project lists in `.config/pyproject_template/sync-exclude.toml`
    (ADR-9026) the upstream-only paths it did not adopt -- such a path is never
    committed there, so it would otherwise be reported as missing documentation
    forever. Upstream has no such file, so `load_sync_excludes` returns `[]` and
    this check is exactly as strict as before.
    """
    excludes = load_sync_excludes(REPO_ROOT)
    missing = sorted(_unallowed_missing(_documented_paths(), excludes))
    assert not missing, (
        "documentation names paths that do not exist:\n  "
        + "\n  ".join(missing)
        + "\nFix the path, or add it to ALLOWED with the reason it is not a real file."
    )


def test_excluded_missing_target_is_skipped(tmp_path: Path) -> None:
    """A missing target matching sync-exclude.toml must not be reported."""
    doc = tmp_path / "readme.md"
    pairs = [(doc, "docs/template/manage.md")]

    assert _unallowed_missing(pairs, ["docs/template/**"], root=tmp_path) == set()


def test_non_excluded_missing_target_still_fails(tmp_path: Path) -> None:
    """The same missing target, without a matching exclude, is still reported.

    Pins that the skip above fires *because* of the exclude pattern, not because
    the check stopped looking for missing targets altogether.
    """
    doc = tmp_path / "readme.md"
    pairs = [(doc, "docs/template/manage.md")]

    assert _unallowed_missing(pairs, [], root=tmp_path) == {"readme.md: docs/template/manage.md"}


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(  # nosec B603 B607 - fixed argv, no shell, test fixture only
        ["git", *args], cwd=cwd, check=True, capture_output=True
    )


def _init_repo(root: Path) -> None:
    _git(["init", "--quiet"], root)
    _git(["config", "user.email", "test@example.com"], root)
    _git(["config", "user.name", "Test"], root)


def test_the_scanner_skips_worktrees(tmp_path: Path) -> None:
    """Each worktree under `worktrees/` is a full copy of the repository (#854).

    Its docs name paths relative to itself, and a check run from the main
    checkout must not also judge every copy. `worktrees/` is gitignored
    (mirroring the real `.gitignore`), so the git-based scan drops it without
    a hardcoded skip list.
    """
    _init_repo(tmp_path)
    (tmp_path / ".gitignore").write_text("/worktrees/\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "kept.md").write_text("# Kept\n", encoding="utf-8")
    copy = tmp_path / "worktrees" / "feat" / "42-add-export" / "docs"
    copy.mkdir(parents=True)
    (copy / "index.md").write_text("# Copy\n", encoding="utf-8")

    assert _markdown_files(tmp_path) == [tmp_path / "docs" / "kept.md"]


def test_the_scanner_reads_something() -> None:
    """Guard against the assertion above passing on an empty scan.

    Deliberately not a threshold on the count: a downstream project has fewer
    docs than the template, and a test that fails because a project is smaller
    is the portability trap this repo warns adopters about. What matters is that
    the regex finds paths *and* that resolution works, so a scan of real files
    could report a real miss.
    """
    found = _documented_paths()
    assert found, "no documented paths found at all; the regex is not matching"
    resolved = [
        raw for doc, raw in found if (REPO_ROOT / raw).exists() or (doc.parent / raw).exists()
    ]
    assert resolved, "no documented path resolved; resolution is broken, not the docs"


def test_allowlist_entries_are_still_needed() -> None:
    """An allowlist entry for a path that now exists is a suppression to drop."""
    stale = sorted(
        prefix
        for prefix in ALLOWED
        if not prefix.endswith("/")
        and prefix not in NEVER_COMMITTED
        and (REPO_ROOT / prefix.lstrip("/")).exists()
    )
    assert not stale, (
        f"these paths exist now, so their allowlist entries are obsolete: {stale}. "
        "Remove them, so the list keeps meaning 'deliberately not a file'."
    )


def test_every_allowlist_entry_carries_a_reason() -> None:
    """The list is decisions, not suppressions."""
    for prefix, reason in ALLOWED.items():
        assert reason.strip(), f"{prefix} is allowlisted without a reason"


def test_never_committed_entries_are_allowlisted() -> None:
    """Every never-committed exemption must also carry a reason in ALLOWED.

    `NEVER_COMMITTED` only suppresses the obsolescence check. If an entry drifts
    out of `ALLOWED` it would stop being exempt from the existence check while
    still looking handled, so the two lists are held together.
    """
    for prefix in NEVER_COMMITTED:
        assert prefix in ALLOWED, f"{prefix} is exempt from staleness but not allowlisted"

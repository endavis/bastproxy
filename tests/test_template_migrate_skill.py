"""The two `template-migrate` bodies must agree, and must stay standalone.

`template-migrate` is unlike every other workflow file here: it runs in a
repository that does not have this template. No `doit`, no
`tools/pyproject_template/`, no `AGENTS.md`, no `docs/`. An instruction that
reads a template document from local disk resolves to nothing there, and the
agent either invents the content or gives up -- neither of which the user sees
as a failure. `test_no_body_reads_template_docs_from_disk` is the guard for
that, and it is the reason this module exists separately from
`test_template_sync_skill.py`.

The rest follows the same reasoning as that module: two surfaces --
`.agents/skills/` for Codex, Antigravity and Copilot, `.claude/skills/` for
Claude (generated from the former by `doit skills_sync`, byte for byte) --
and whichever agent the user drives decides which body applies, so a step
present in one and missing from the other is a control that fires for some
users and not others. The bodies are identical since #972; what is asserted
here is the contract and its ordering.

Scoped to the agents a project actually wires, per `tests/agent_roster.py`
(#690).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from agent_roster import agent_is_present

REPO_ROOT = Path(__file__).resolve().parents[1]

CLAUDE_COMMAND = REPO_ROOT / ".claude" / "skills" / "template-migrate" / "SKILL.md"
SHARED_SKILL = REPO_ROOT / ".agents" / "skills" / "template-migrate" / "SKILL.md"

# (label, substring) pairs both bodies must carry. Literal substrings rather
# than regexes, matching the convention in `test_cross_agent_contract.py`.
CONTRACT: tuple[tuple[str, str], ...] = (
    # Running this against the template itself, or against an already-migrated
    # project, is meaningless -- and the second case has a right answer to
    # redirect to, which is the only reason the user would find it.
    ("self-repo refusal", "endavis/pyproject-template"),
    ("already-migrated redirect", "template-sync"),
    ("standalone declaration", "Assume nothing from this template is installed."),
    ("found files belong to the project", "belongs to the project, not to the template"),
    ("existing agent instructions outrank this file", "read them and follow them"),
    ("version pinning", "vnd.github.sha"),
    ("http fetch of template docs", "raw.githubusercontent.com"),
    ("the authoritative checklist", "docs/template/migration.md"),
    ("consumer notes", "docs/template/consumer-notes.md"),
    ("ask-rather-than-assume discipline", "**Ask rather than assume.**"),
    ("plan file in the repo root", "TEMPLATE_MIGRATION_PLAN.md"),
    ("merge-not-overwrite backup", 'cp "$f" "$f.old"'),
    ("version comes from git tags", "hatch-vcs"),
    ("the merge-gate label trap", "ready-to-merge"),
    ("pre-commit reinstall", "doit pre_commit_install"),
    ("github-side configuration", "manage.py repo"),
    ("validation command", "doit check"),
    ("never edit a failing test", "Never edit a test to make it pass"),
    ("why this plans rather than migrates", "#783"),
)

# The identical sentence both bodies must carry, so the gate cannot be reworded
# into something weaker on one surface.
APPROVAL_GATE_SENTENCE = (
    "**Stop here.** Do not change a single file until the owner has read the plan "
    "and told you to proceed."
)

# Instructions that would read a *template* document from the local filesystem.
#
# Scoped to `docs/template/`, which is unambiguously template-owned and is not
# present in a project that has not migrated. `AGENTS.md`, `pyproject.toml` and
# `README.md` are deliberately NOT matched: the target repository may well have
# its own, reading those locally is exactly right, and an earlier version of
# this guard forbade it. The skill distinguishes them in prose instead.
_LOCAL_READ = re.compile(
    r"\b(cat|less|head|tail|open|Read)\s+[\"']?docs/template/",
)


def _normalized(text: str) -> str:
    """Collapse whitespace runs, so a sentence that wraps still matches.

    The contract is the wording, not where the lines happen to break. Matching
    the literal string would make a future reflow of the prose look like a
    weakened gate.
    """
    return re.sub(r"\s+", " ", text)


def _wired_bodies() -> list[tuple[str, Path]]:
    """Return (surface, path) for each `template-migrate` body this project wires."""
    bodies: list[tuple[str, Path]] = []
    if agent_is_present("claude"):
        bodies.append(("claude", CLAUDE_COMMAND))
    # Codex, Antigravity and Copilot all read `.agents/skills/`.
    if any(agent_is_present(a) for a in ("codex", "antigravity", "copilot")):
        bodies.append(("shared", SHARED_SKILL))
    return bodies


def _contract_violations(surface: str, text: str) -> list[str]:
    """Return the contract elements *text* is missing."""
    normalized = _normalized(text)
    return [
        f"{surface} is missing the {label} ({needle!r})"
        for label, needle in CONTRACT
        if needle not in normalized
    ]


def test_at_least_one_template_migrate_body_exists() -> None:
    """A project that wires any agent has somewhere to invoke `template-migrate`."""
    if not _wired_bodies():
        pytest.skip("no AI agent is wired in this project")

    assert CLAUDE_COMMAND.is_file() or SHARED_SKILL.is_file(), (
        "template-migrate exists on neither surface"
    )


def test_both_bodies_carry_the_contract() -> None:
    """Every wired `template-migrate` body carries every contract element."""
    missing: list[str] = []

    for surface, path in _wired_bodies():
        if not path.is_file():
            missing.append(f"{surface}: {path.relative_to(REPO_ROOT)} does not exist")
            continue
        missing += _contract_violations(surface, path.read_text(encoding="utf-8"))

    assert not missing, (
        "template-migrate contract violations:\n  "
        + "\n  ".join(missing)
        + "\n\nBoth bodies must carry these steps. Change them together or not at all."
    )


def test_the_contract_scanner_detects_a_violation() -> None:
    """The scanner must fail on a body that drops a step, not merely pass on ours."""
    assert _contract_violations("synthetic", "a body that says none of the required things")


def test_the_approval_gate_is_worded_identically() -> None:
    """The review gate must be the same sentence on every surface.

    A gate paraphrased per host drifts into a weaker version on one of them, and
    whichever agent the owner happens to be driving decides which applies. Here
    the gate stands between a plan and an irreversible rewrite of someone's
    repository, so it is the sentence least able to afford drift.
    """
    divergent = []
    for surface, path in _wired_bodies():
        if not path.is_file():
            continue
        if APPROVAL_GATE_SENTENCE not in _normalized(path.read_text(encoding="utf-8")):
            divergent.append(f"{surface} ({path.relative_to(REPO_ROOT)})")

    assert not divergent, (
        f"these bodies do not carry the exact approval-gate sentence: {divergent}. "
        "Reword all of them together or none."
    )


def test_no_body_reads_template_docs_from_disk() -> None:
    """Template documents must be fetched, never read locally.

    This skill runs in a repository that does not have the template, so
    `docs/template/*.md` is not on disk. An instruction to read one resolves to
    nothing, and an agent that finds nothing will either invent the content or
    stall -- neither of which looks like a failure to the person who ran it.

    Scoped to `docs/template/` on purpose. The target repository may have its own
    `AGENTS.md`, `pyproject.toml` or `README.md`; reading those locally is
    correct and is what Step 3 does.

    There is no exemption for lines that mention the raw host. The pattern needs
    a read command immediately before `docs/template/`, which a `curl` line does
    not have, so fetches are already excluded by shape. An earlier version
    skipped any line containing the hostname -- redundant, and it would have
    waved through a genuine violation that happened to name the host on the same
    line. CodeQL flagged the substring check
    (`py/incomplete-url-substring-sanitization`) and was right to.
    """
    offenders = []
    for surface, path in _wired_bodies():
        if not path.is_file():
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _LOCAL_READ.search(line):
                offenders.append(f"{surface}:{line_no}: {line.strip()}")

    assert not offenders, (
        "template-migrate reads template docs from local disk, which does not exist "
        "in an unmigrated project:\n  " + "\n  ".join(offenders)
    )


def test_the_local_read_scanner_detects_a_violation() -> None:
    """The standalone guard must fail on a real violation, not merely pass on ours."""
    assert _LOCAL_READ.search("cat docs/template/migration.md")
    assert _LOCAL_READ.search("Read docs/template/consumer-notes.md first")
    # Must not fire on the correct form: fetched, not read.
    assert not _LOCAL_READ.search('curl -sSL "$RAW/docs/template/migration.md"')
    # Naming the host does not launder a local read. This is what the removed
    # hostname-substring exemption used to let through.
    assert _LOCAL_READ.search("Read docs/template/migration.md (from $RAW)")
    # Must not fire on the project's own files, which Step 3 reads locally and
    # which share their names with template files (#811 review).
    assert not _LOCAL_READ.search("Read AGENTS.md and follow it")
    assert not _LOCAL_READ.search("cat pyproject.toml")


def test_the_plan_gate_precedes_the_execute_step() -> None:
    """The plan must be written and approved before anything is changed.

    An agent that migrates first and writes the plan afterwards has produced a
    record of what it already did to someone's repository. The ordering is the
    control; the presence of both steps is not.
    """
    out_of_order = []
    for surface, path in _wired_bodies():
        if not path.is_file():
            continue
        text = _normalized(path.read_text(encoding="utf-8"))
        gate = text.find(APPROVAL_GATE_SENTENCE)
        execute = text.find("### Step 8: Execute, only if asked")
        if gate == -1 or execute == -1 or gate > execute:
            out_of_order.append(f"{surface} ({path.relative_to(REPO_ROOT)})")

    assert not out_of_order, (
        f"these bodies change files before the owner has approved the plan: {out_of_order}."
    )


def test_the_inventory_precedes_the_plan() -> None:
    """A plan written before reading the repository is a generic plan.

    Step 3 is what makes the output specific to this project rather than a
    restatement of the checklist the owner could have read themselves.
    """
    out_of_order = []
    for surface, path in _wired_bodies():
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        inventory = text.find("### Step 3: Inventory this project")
        plan = text.find("### Step 6: Write the plan")
        if inventory == -1 or plan == -1 or inventory > plan:
            out_of_order.append(f"{surface} ({path.relative_to(REPO_ROOT)})")

    assert not out_of_order, f"these bodies plan before inventorying: {out_of_order}."


def test_shared_skill_declares_the_frontmatter_agents_activate_on() -> None:
    """Antigravity activates a skill by matching its `description:`; without one it never fires."""
    if not SHARED_SKILL.is_file():
        pytest.skip("the shared template-migrate skill is not wired in this project")

    text = SHARED_SKILL.read_text(encoding="utf-8")
    assert text.startswith("---\n"), "SKILL.md must open with YAML frontmatter"
    frontmatter = text.split("---", 2)[1]
    assert "name: template-migrate" in frontmatter
    assert "description:" in frontmatter
    # The description is the whole activation surface for Antigravity: it must
    # name what the user would actually say, not just the skill's own title.
    assert "migrate" in frontmatter.lower()
    assert "existing" in frontmatter.lower()

"""The two `template-sync` bodies must agree on the steps that carry the risk.

`template-sync` ships on two surfaces — `.agents/skills/template-sync/SKILL.md`
for Codex, Antigravity and Copilot, `.claude/skills/template-sync/SKILL.md` for
Claude (generated from the former by `doit skills_sync`, byte for byte).
Whichever agent the user happens to be driving decides which body applies, so
a step present in one and missing from the other is not a documentation
inconsistency; it is a control that fires for some users and not others.
`docs/development/ai/rule-files.md` makes the same argument for rule files.

Since #972 the two bodies are byte-identical, like the rule files. What is
asserted here is the contract — the ordering constraint and the guards whose
absence produces a wrong sync — which stays worth checking on its own even
though a diff would now also catch drift.

Scoped to the agents a project actually wires, per `tests/agent_roster.py`
(#690).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from agent_roster import agent_is_present

REPO_ROOT = Path(__file__).resolve().parents[1]

CLAUDE_COMMAND = REPO_ROOT / ".claude" / "skills" / "template-sync" / "SKILL.md"
SHARED_SKILL = REPO_ROOT / ".agents" / "skills" / "template-sync" / "SKILL.md"

# The path `manage.py` used to hardcode, which `check` never creates: the archive
# root is named for the resolved commit (ADR-9020). Fixed in #805; the guard
# stays because the wrong path is the one a writer reaches for from memory, and
# a body that puts it in a `diff` command hands the reader a path that is never
# there. A blockquote may still name it to explain history.
STALE_EXTRACT_PATH = "tmp/extracted/pyproject-template-main"

# (label, substring) pairs both bodies must carry. Literal substrings rather
# than regexes, matching the convention in `test_cross_agent_contract.py`: the
# contract is the literal instruction, so a literal check is the honest test.
CONTRACT: tuple[tuple[str, str], ...] = (
    # Running this against the template itself is meaningless; both bodies must
    # say so, because an agent that does not stop will "sync" the upstream to
    # itself and report success.
    ("self-repo refusal", "endavis/pyproject-template"),
    ("tracking issue", "doit issue --type=chore"),
    ("tooling refresh", "bootstrap.py | python3 - --sync"),
    ("drift check", "manage.py --yes check"),
    ("staged upgrade", "--template-version"),
    ("glob lookup for the extracted template", "tmp/extracted/pyproject-template-*"),
    ("ask-rather-than-guess discipline", "**Ask rather than guess.**"),
    ("plan comment header", "## Sync Plan for #"),
    ("plan posted to the issue", "gh issue comment"),
    ("sync-state marking", "manage.py --yes sync"),
    ("pre-commit reinstall", "doit pre_commit_install"),
    ("validation command", "doit check"),
    ("never edit a failing test", "Never edit a test to make it pass"),
    ("finalize handoff", "implement-issue"),
)

# The identical sentence both bodies must carry, so the gate cannot be reworded
# into something weaker on one surface — the same guarantee
# `test_cross_agent_contract.py` gives the read-only constraint.
APPROVAL_GATE_SENTENCE = (
    "**Stop here.** Do not apply a single file until the repo admin has approved "
    "the plan on the issue."
)


def _wired_bodies() -> list[tuple[str, Path]]:
    """Return (surface, path) for each `template-sync` body this project wires."""
    bodies: list[tuple[str, Path]] = []
    if agent_is_present("claude"):
        bodies.append(("claude", CLAUDE_COMMAND))
    # Codex, Antigravity and Copilot all read `.agents/skills/`.
    if any(agent_is_present(a) for a in ("codex", "antigravity", "copilot")):
        bodies.append(("shared", SHARED_SKILL))
    return bodies


def _contract_violations(surface: str, text: str) -> list[str]:
    """Return the contract elements *text* is missing.

    Shared by the real check and its non-vacuity companion so the companion
    exercises the logic that actually runs.
    """
    return [
        f"{surface} is missing the {label} ({needle!r})"
        for label, needle in CONTRACT
        if needle not in text
    ]


def test_at_least_one_template_sync_body_exists() -> None:
    """A project that wires any agent has somewhere to invoke `template-sync`."""
    if not _wired_bodies():
        pytest.skip("no AI agent is wired in this project")

    assert CLAUDE_COMMAND.is_file() or SHARED_SKILL.is_file(), (
        "template-sync exists on neither surface; the template upgrade has no entry point"
    )


def test_both_bodies_carry_the_contract() -> None:
    """Every wired `template-sync` body carries every contract element."""
    missing: list[str] = []

    for surface, path in _wired_bodies():
        if not path.is_file():
            missing.append(f"{surface}: {path.relative_to(REPO_ROOT)} does not exist")
            continue
        missing += _contract_violations(surface, path.read_text(encoding="utf-8"))

    assert not missing, (
        "template-sync contract violations:\n  "
        + "\n  ".join(missing)
        + "\n\nBoth bodies must carry these steps. Change them together or not at all."
    )


def test_the_contract_scanner_detects_a_violation() -> None:
    """The scanner must fail on a body that drops a step, not merely pass on ours.

    Without this, deleting an entry from CONTRACT or breaking `_contract_violations`
    would leave a green suite that checks nothing.
    """
    assert _contract_violations("synthetic", "a body that says none of the required things")


def test_the_approval_gate_is_worded_identically() -> None:
    """The review gate must be the same sentence on every surface.

    A gate paraphrased per host drifts into a weaker version on one of them, and
    whichever agent the user happens to be driving decides which version applies.
    The gate is the whole reason the plan is written down, so it is the sentence
    least able to afford drift.
    """
    divergent = []
    for surface, path in _wired_bodies():
        if not path.is_file():
            continue
        if APPROVAL_GATE_SENTENCE not in path.read_text(encoding="utf-8"):
            divergent.append(f"{surface} ({path.relative_to(REPO_ROOT)})")

    assert not divergent, (
        f"these bodies do not carry the exact approval-gate sentence: {divergent}. "
        "Reword all of them together or none."
    )


def test_the_plan_gate_precedes_the_apply_step() -> None:
    """The plan must be posted before anything is applied, in both bodies.

    An agent that applies first and posts the plan afterwards has produced a
    record of what it already did, not a decision the admin got to make. The
    ordering is the control; presence of both steps is not.
    """
    out_of_order = []
    for surface, path in _wired_bodies():
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        gate = text.find(APPROVAL_GATE_SENTENCE)
        apply_step = text.find("### Step 7: Apply the approved plan")
        if gate == -1 or apply_step == -1 or gate > apply_step:
            out_of_order.append(f"{surface} ({path.relative_to(REPO_ROOT)})")

    assert not out_of_order, (
        f"these bodies apply changes before the admin has approved the plan: {out_of_order}."
    )


def test_the_tooling_refresh_precedes_the_drift_check() -> None:
    """`bootstrap --sync` must be instructed before `manage.py check`, in both bodies.

    The drift checker compares against the template version it shipped with, so
    a checker older than the template being adopted misreports the diff. The
    ordering is the whole reason Phase 1 of `docs/template/ai-sync-checklist.md`
    exists; a body that presents the steps in the other order teaches the bug.
    """
    out_of_order = []
    for surface, path in _wired_bodies():
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        refresh = text.find("bootstrap.py | python3 - --sync")
        check = text.find("manage.py --yes check")
        if refresh == -1 or check == -1 or refresh > check:
            out_of_order.append(f"{surface} ({path.relative_to(REPO_ROOT)})")

    assert not out_of_order, (
        f"these bodies check for drift before refreshing the tooling: {out_of_order}. "
        "A stale check_template_updates.py misreports drift against a newer template."
    )


def test_no_body_teaches_the_stale_extraction_path() -> None:
    """The dead `-main` path may be named as a defect, never used as an instruction.

    `check` extracts to `tmp/extracted/pyproject-template-<sha>`; the fixed
    `-main` name that `manage.py` still looks for does not exist (#805). A body
    that puts it in a `diff` command hands the user a path that is never there.
    Blockquotes are the escape hatch, because that is where the defect note lives.
    """
    offenders = []
    for surface, path in _wired_bodies():
        if not path.is_file():
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if STALE_EXTRACT_PATH in line and not line.lstrip().startswith(">"):
                offenders.append(f"{surface}:{line_no}: {line.strip()}")

    assert not offenders, (
        "template-sync names the stale extraction path outside a defect note:\n  "
        + "\n  ".join(offenders)
        + "\n\nUse the glob form. See #805."
    )


def test_shared_skill_declares_the_frontmatter_agents_activate_on() -> None:
    """Antigravity activates a skill by matching its `description:`; without one it never fires."""
    if not SHARED_SKILL.is_file():
        pytest.skip("the shared template-sync skill is not wired in this project")

    text = SHARED_SKILL.read_text(encoding="utf-8")
    assert text.startswith("---\n"), "SKILL.md must open with YAML frontmatter"
    frontmatter = text.split("---", 2)[1]
    assert "name: template-sync" in frontmatter
    assert "description:" in frontmatter

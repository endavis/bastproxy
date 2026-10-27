"""The two `dead-code-triage` bodies must agree on how a vulture finding is triaged.

`doit check` runs `doit deadcode` as one of its `task_dep` (`tools/doit/quality.py`), so a
vulture finding blocks the check for every agent. Vulture cannot tell a genuine dead import
from one an interface, a framework, or the type checker still needs, so an agent that "fixes"
every finding by deleting or blanket-whitelisting it breaks real code or hides a real bug (#835).

Two surfaces carry the triage steps -- `.agents/skills/` for Codex, Antigravity and Copilot,
`.claude/skills/` for Claude (generated from the former by `doit skills_sync`, byte for byte) --
and whichever agent the user drives decides which body applies. A step present in one and missing
from the other is a control that fires for some users and not others. The bodies are identical
since #972; what is asserted here is the contract and its ordering.

Scoped to the agents a project actually wires, per `tests/agent_roster.py` (#690).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from agent_roster import agent_is_present

REPO_ROOT = Path(__file__).resolve().parents[1]

CLAUDE_COMMAND = REPO_ROOT / ".claude" / "skills" / "dead-code-triage" / "SKILL.md"
SHARED_SKILL = REPO_ROOT / ".agents" / "skills" / "dead-code-triage" / "SKILL.md"

# The steps both bodies take, in this order.
STEPS: tuple[str, ...] = (
    "### Step 1: Read the finding",
    "### Step 2: Triage by kind",
    "### Step 3: Record the decision",
    "### Step 4: Validate",
)

# (label, substring) pairs both bodies must carry. Literal substrings rather
# than regexes, matching the convention in `test_add_dependency_skill.py`.
CONTRACT: tuple[tuple[str, str], ...] = (
    ("the config it applies", "`[tool.vulture]`"),
    ("the threshold key", "`min_confidence`"),
    ("the scanned-paths key", "`paths`"),
    ("the exceptions table", "`ignore_names`"),
    ("the decorator-exceptions table", "`ignore_decorators`"),
    ("the unused-import message", "unused import '<name>'"),
    ("the unused-variable message", "unused variable '<name>'"),
    ("the unreachable-code message", "unreachable code after 'return'"),
    ("the TYPE_CHECKING check", "`if TYPE_CHECKING:`"),
    ("the ConsoleType precedent", "`ConsoleType`"),
    ("the __all__ re-export check", "`__all__ = [...]`"),
    ("the __init__.py re-export check", "`__init__.py`"),
    ("the side-effect import check", "side-effect import"),
    ("the underscore-prefix escape", "`_`-prefixed"),
    ("the underscore-prefix example", "`def handler(event, _context)`"),
    ("asking when unsure", "ask the user rather than guessing"),
    ("the validation command", "doit deadcode"),
    ("full validation", "doit check"),
    ("scratch files", "tmp/agents/"),
)

# Sentences both bodies carry word for word, so neither can be softened on one
# surface. The first closes Step 2's unreachable-code branch; the second opens
# Step 3.
UNREACHABLE_GATE = "Check whether the statement before it exits too early before deleting anything."
IGNORE_NAMES_GATE = (
    "A new `ignore_names` entry always carries a comment naming the reference vulture cannot see"
)


def _normalized(text: str) -> str:
    """Collapse whitespace runs, so a sentence that wraps still matches."""
    return re.sub(r"\s+", " ", text)


def _wired_bodies() -> list[tuple[str, Path]]:
    """Return (surface, path) for each `dead-code-triage` body this project wires."""
    bodies: list[tuple[str, Path]] = []
    if agent_is_present("claude"):
        bodies.append(("claude", CLAUDE_COMMAND))
    # Codex, Antigravity and Copilot all read `.agents/skills/`.
    if any(agent_is_present(a) for a in ("codex", "antigravity", "copilot")):
        bodies.append(("shared", SHARED_SKILL))
    return bodies


def _existing_bodies() -> list[tuple[str, str]]:
    """Return (surface, normalized text) for each wired body that exists."""
    return [
        (surface, _normalized(path.read_text(encoding="utf-8")))
        for surface, path in _wired_bodies()
        if path.is_file()
    ]


def _contract_violations(surface: str, text: str) -> list[str]:
    """Return the contract elements *text* is missing."""
    normalized = _normalized(text)
    return [
        f"{surface} is missing the {label} ({needle!r})"
        for label, needle in CONTRACT
        if needle not in normalized
    ]


def _step(text: str, number: int) -> str:
    """Return step *number* of normalized *text*: its heading up to the next heading."""
    start = text.find(STEPS[number - 1])
    if start == -1:
        return ""
    end = text.find(" ## ", start + 1) if number == len(STEPS) else text.find(STEPS[number])
    return text[start : end if end != -1 else len(text)]


def test_every_wired_surface_has_a_body() -> None:
    """A project that wires any agent has somewhere to invoke `dead-code-triage`."""
    if not _wired_bodies():
        pytest.skip("no AI agent is wired in this project")

    missing = [
        f"{surface}: {path.relative_to(REPO_ROOT)}"
        for surface, path in _wired_bodies()
        if not path.is_file()
    ]
    assert not missing, f"dead-code-triage is missing on wired surfaces: {missing}"


def test_both_bodies_carry_the_contract() -> None:
    """Every wired `dead-code-triage` body carries every contract element."""
    missing: list[str] = []
    for surface, text in _existing_bodies():
        missing += _contract_violations(surface, text)

    assert not missing, (
        "dead-code-triage contract violations:\n  "
        + "\n  ".join(missing)
        + "\n\nBoth bodies must carry these steps. Change them together or not at all."
    )


def test_the_contract_scanner_detects_a_violation() -> None:
    """The scanner must fail on a body that drops a step, not merely pass on ours."""
    assert _contract_violations("synthetic", "a body that says none of the required things")


def test_the_steps_run_in_the_same_order_on_every_surface() -> None:
    """Read, triage, record, validate -- on every surface, in that order.

    Triaging before reading the finding means guessing at the kind from nothing.
    Validating before recording the decision means the reason comment, when one
    is needed, never gets written down.
    """
    out_of_order = []
    for surface, text in _existing_bodies():
        positions = [text.find(step) for step in STEPS]
        if -1 in positions or positions != sorted(positions):
            out_of_order.append(f"{surface}: {dict(zip(STEPS, positions, strict=True))}")

    assert not out_of_order, "dead-code-triage steps missing or out of order:\n  " + "\n  ".join(
        out_of_order
    )


def test_the_gate_sentences_are_worded_identically_and_in_place() -> None:
    """The early-exit gate lives in Step 2; the reason-comment gate lives in Step 3.

    A gate paraphrased per host drifts into a weaker version on one of them. An
    unreachable-code check performed only after the code is already deleted
    protects nothing, and an `ignore_names` entry recorded without its reason is
    the next reader's problem to solve from scratch.
    """
    misplaced = []
    for surface, text in _existing_bodies():
        if UNREACHABLE_GATE not in _step(text, 2):
            misplaced.append(f"{surface}: the unreachable-code gate is not in Step 2")
        if IGNORE_NAMES_GATE not in _step(text, 3):
            misplaced.append(f"{surface}: the ignore_names gate is not in Step 3")

    assert not misplaced, (
        "\n  ".join(["gate sentences missing, reworded or moved:", *misplaced])
        + "\nReword every surface together or none."
    )


def test_the_gate_sentence_scanner_detects_a_violation() -> None:
    """The gate-sentence check must fail on a body that drops the gates, not merely pass on ours."""
    body_missing_both = (
        "### Step 1: Read the finding\n"
        "### Step 2: Triage by kind\nnothing here\n"
        "### Step 3: Record the decision\nnothing here either\n"
        "### Step 4: Validate\n"
    )
    assert UNREACHABLE_GATE not in _step(body_missing_both, 2)
    assert IGNORE_NAMES_GATE not in _step(body_missing_both, 3)


def test_shared_skill_declares_the_frontmatter_agents_activate_on() -> None:
    """Antigravity activates a skill by matching its `description:`; without one it never fires."""
    if not SHARED_SKILL.is_file():
        pytest.skip("the shared dead-code-triage skill is not wired in this project")

    text = SHARED_SKILL.read_text(encoding="utf-8")
    assert text.startswith("---\n"), "SKILL.md must open with YAML frontmatter"
    frontmatter = text.split("---", 2)[1]
    assert "name: dead-code-triage" in frontmatter
    assert "description:" in frontmatter
    # The description is the whole activation surface: it must name what an agent
    # would be doing when it needs this, not just the skill's title.
    for phrase in ("vulture", "doit check", "doit deadcode"):
        assert phrase in frontmatter.lower(), f"description never mentions {phrase!r}"

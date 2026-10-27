"""The two `mutation-triage` bodies must agree, and neither may pin the mutation over behavior.

Both `doit mutate` and `doit coverage` are informational about the gap this skill closes: a
surviving mutant does not fail `doit mutate`, locally or in the weekly workflow, and a line
`doit coverage` marks ``Missing`` does not fail `doit check` unless it drags the total under
`fail_under`. Nothing stops a survivor being declared equivalent with no reason, or "killed" by
a test that pins the mutated literal instead of real behavior -- both look like progress and
prove nothing (#830).

Two surfaces carry the workflow -- `.agents/skills/` for Codex, Antigravity and Copilot,
`.claude/skills/` for Claude (generated from the former by `doit skills_sync`, byte for byte) --
and whichever agent the user drives decides which body applies. A step, or a gate sentence,
present in one and missing from the other is a control that fires for some users and not others.
The bodies are identical since #972; what is asserted here is the contract and its ordering --
the same approach `test_add_dependency_skill.py` takes for `add-dependency` (#829).

Scoped to the agents a project actually wires, per `tests/agent_roster.py` (#690).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from agent_roster import agent_is_present

REPO_ROOT = Path(__file__).resolve().parents[1]

CLAUDE_COMMAND = REPO_ROOT / ".claude" / "skills" / "mutation-triage" / "SKILL.md"
SHARED_SKILL = REPO_ROOT / ".agents" / "skills" / "mutation-triage" / "SKILL.md"

# The steps both bodies take, in this order.
STEPS: tuple[str, ...] = (
    "### Step 1: Scope",
    "### Step 2: Inspect",
    "### Step 3: Classify",
    "### Step 4: Write behavior tests",
    "### Step 5: Prove the kill",
    "### Step 6: Uncovered lines",
)

# (label, substring) pairs both bodies must carry. Literal substrings rather than
# regexes, matching the convention in `test_template_migrate_skill.py`.
CONTRACT: tuple[tuple[str, str], ...] = (
    ("the policy it applies", "`docs/development/ci-cd-testing.md`"),
    ("the section holding it", '"## Mutation Testing"'),
    ("mutmut's mutate scope config", "`source_paths`"),
    ("mutmut run's only positional argument", "`MUTANT_NAMES`"),
    ("fnmatch is the matching mechanism", "`fnmatch`"),
    ("function mutant naming", "`x_<function>__mutmut_<n>`"),
    ("method mutant naming", "`xǁ<Class>ǁ<method>__mutmut_<n>`"),
    ("pattern-scoped run example", "`<package>.<module>.*`"),
    ("out-of-scope status is expected, not a failure", "`not checked`"),
    ("full unscoped run", "`doit mutate` instead when the scope is empty"),
    ("inspect command", "`uv run mutmut show <MUTANT_NAME>`"),
    ("equivalent classification", "**Equivalent.**"),
    ("missing-assertion classification", "**Missing assertion.**"),
    ("untested-branch classification", "**Untested branch.**"),
    ("real-bug classification", "**Real bug.**"),
    ("test-selection reminder", "`pytest_add_cli_args_test_selection`"),
    ("selection-enforcing test", "`tests/test_mutmut_config.py`"),
    ("which-tests-run pointer", '"### Which Tests Run"'),
    ("import scope is repo code, not third-party/stdlib", "not for third-party or"),
    ("prove-the-kill command", '`uv run mutmut run "<name-or-pattern>"`'),
    ("mutant-results section", '"Mutant results" section'),
    ("killed emoji named", "killed as 🎉"),
    ("survived emoji named", "survived as 🙁"),
    ("emoji legend pointer", "`emoji_by_status`"),
    ("status-as-words alternative", "`uv run mutmut results --all true`"),
    ("coverage missing column", "`Missing` column"),
    ("coverage run config", "`[tool.coverage.run]`"),
    ("coverage report config", "`[tool.coverage.report]`"),
    ("branch arrow marker", "`A->B`"),
    ("uncovered lines loop back", "Steps 4 and 5"),
    ("bug-locking mistake named", "the mistake AGENTS.md forbids for a failing test"),
    ("mutants cache is gitignored", "git-ignored"),
    ("hand-off gate", "passes `doit check`, hand off to"),
)

# Sentences both bodies carry word for word, keyed by the step they must appear in.
# A gate reworded on one surface is a control that only fires for some users.
GATES: tuple[tuple[int, str], ...] = (
    (
        3,
        "**An equivalent verdict must say why no input tells the two apart — never record it "
        "without one.**",
    ),
    (
        3,
        "**If the distinguishing behavior is itself wrong, stop: do not write a test that "
        "asserts the current output is correct, report the bug, and wait.**",
    ),
    (
        4,
        "**Never write a test whose assertion is keyed to the mutated literal, operator, or "
        "constant itself — assert on the function's observable output or effect for a real "
        "input, and let the mutation fail incidentally.**",
    ),
    (
        5,
        "**A classification is not finished until you re-run what it targeted and every one "
        "shows killed — paste the before and after status.**",
    ),
)

# (quoted heading, filename) pairs that must sit on the same source line, so
# `test_instruction_pointers.py` resolves them: it reads pointers per line, and a
# heading wrapped onto a different line from its filename is silently never checked.
POINTER_PAIRS: tuple[tuple[str, str], ...] = (
    ('"## Mutation Testing"', "docs/development/ci-cd-testing.md"),
    ('"### Which Tests Run"', "docs/development/ci-cd-testing.md"),
)


def _normalized(text: str) -> str:
    """Collapse whitespace runs, so a sentence that wraps still matches."""
    return re.sub(r"\s+", " ", text)


def _wired_bodies() -> list[tuple[str, Path]]:
    """Return (surface, path) for each `mutation-triage` body this project wires."""
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
    """A project that wires any agent has somewhere to invoke `mutation-triage`."""
    if not _wired_bodies():
        pytest.skip("no AI agent is wired in this project")

    missing = [
        f"{surface}: {path.relative_to(REPO_ROOT)}"
        for surface, path in _wired_bodies()
        if not path.is_file()
    ]
    assert not missing, f"mutation-triage is missing on wired surfaces: {missing}"


def test_both_bodies_carry_the_contract() -> None:
    """Every wired `mutation-triage` body carries every contract element."""
    missing: list[str] = []
    for surface, text in _existing_bodies():
        missing += _contract_violations(surface, text)

    assert not missing, (
        "mutation-triage contract violations:\n  "
        + "\n  ".join(missing)
        + "\n\nBoth bodies must carry these steps. Change them together or not at all."
    )


def test_the_contract_scanner_detects_a_violation() -> None:
    """The scanner must fail on a body that drops a step, not merely pass on ours."""
    assert _contract_violations("synthetic", "a body that says none of the required things")


def test_the_steps_run_in_the_same_order_on_every_surface() -> None:
    """Scope, inspect, classify, write, prove, uncovered -- on every surface, in that order.

    Writing before classifying risks a test that pins whatever the survivor
    currently does. Proving before writing means nothing was re-run to check the
    new test actually kills the mutant it targets.
    """
    out_of_order = []
    for surface, text in _existing_bodies():
        positions = [text.find(step) for step in STEPS]
        if -1 in positions or positions != sorted(positions):
            out_of_order.append(f"{surface}: {dict(zip(STEPS, positions, strict=True))}")

    assert not out_of_order, "mutation-triage steps missing or out of order:\n  " + "\n  ".join(
        out_of_order
    )


def test_the_gate_sentences_are_worded_identically_and_in_place() -> None:
    """Each gate closes the step named in `GATES`, word for word, on every surface.

    A gate paraphrased per host drifts into a weaker version on one of them. A
    gate that only appears after the step it should stop is a control that acts
    too late -- the write already happened.
    """
    misplaced = []
    for surface, text in _existing_bodies():
        for step_number, sentence in GATES:
            if sentence not in _step(text, step_number):
                misplaced.append(f"{surface}: step {step_number} is missing {sentence!r}")

    assert not misplaced, (
        "\n  ".join(["gate sentences missing, reworded or moved:", *misplaced])
        + "\nReword every surface together or none."
    )


def test_the_doc_pointers_share_a_line_with_their_filename() -> None:
    """The quoted heading and its filename sit on the same line the pointer checks read.

    `test_instruction_pointers.py` resolves a quoted-heading reference only when
    the heading and a `.md` filename appear on the same source line (#828, #738).
    A rewrap that separates them leaves the pointer in place and unchecked.
    """
    unseen = []
    for surface, path in _wired_bodies():
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for heading, filename in POINTER_PAIRS:
            if not any(heading in ln and filename in ln for ln in lines):
                unseen.append(f"{surface}: {heading} not paired with {filename} on one line")

    assert not unseen, f"doc pointers split across lines: {unseen}"


def test_shared_skill_declares_the_frontmatter_agents_activate_on() -> None:
    """Antigravity activates a skill by matching its `description:`; without one it never fires."""
    if not SHARED_SKILL.is_file():
        pytest.skip("the shared mutation-triage skill is not wired in this project")

    text = SHARED_SKILL.read_text(encoding="utf-8")
    assert text.startswith("---\n"), "SKILL.md must open with YAML frontmatter"
    frontmatter = text.split("---", 2)[1]
    assert "name: mutation-triage" in frontmatter
    assert "description:" in frontmatter
    # The description is the whole activation surface: it must name what an agent
    # would be doing when it needs this, not just the skill's title.
    for phrase in ("mutmut", "mutant", "coverage"):
        assert phrase in frontmatter.lower(), f"description never mentions {phrase!r}"

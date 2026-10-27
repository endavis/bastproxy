"""The two `deprecate-api` bodies must agree, and neither may skip a release boundary.

Retiring a public name safely means two things happen in the right order, releases apart: callers
are warned before anything is deleted, and a `pytest.warns` test is the one thing this project's
pytest configuration (`--strict-config --strict-markers`, no `filterwarnings`) will ever use to
catch a shim that quietly stops warning (#832).

Two surfaces carry it -- `.agents/skills/` for Codex, Antigravity and Copilot, `.claude/skills/`
for Claude (generated from the former by `doit skills_sync`, byte for byte) -- and whichever agent
the user drives decides which body applies. A step present in one and missing from the other is a
control that fires for some users and not others. The bodies are identical since #972; what is
asserted here is the contract and its ordering.

Scoped to the agents a project actually wires, per `tests/agent_roster.py` (#690).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from agent_roster import agent_is_present

REPO_ROOT = Path(__file__).resolve().parents[1]

CLAUDE_COMMAND = REPO_ROOT / ".claude" / "skills" / "deprecate-api" / "SKILL.md"
SHARED_SKILL = REPO_ROOT / ".agents" / "skills" / "deprecate-api" / "SKILL.md"

# The phases and steps both bodies take, in this order. Two phase headers (level 2) bracket their
# steps (level 3) -- Phase 1 warns, Phase 2 deletes, and nothing is allowed to jump the boundary.
STEPS: tuple[str, ...] = (
    "## Phase 1: Deprecate",
    "### Step 1: Keep it working",
    "### Step 2: Warn at the caller, not at the shim",
    "### Step 3: Test both directions",
    "### Step 4: Document the replacement",
    "## Phase 2: Remove (a later release)",
    "### Step 5: Delete it",
    "### Step 6: Follow the Breaking Changes Policy",
)

# (label, substring) pairs both bodies must carry. Literal substrings rather than regexes,
# matching the convention in `test_add_dependency_skill.py`.
CONTRACT: tuple[tuple[str, str], ...] = (
    ("the policy it applies", "`AGENTS.md`"),
    ("the section holding it", '"## Breaking Changes Policy"'),
    ("scoped to one name, not phases of the policy", "executable for retiring one public name"),
    ("keep the old name exported", "`__all__`"),
    ("one implementation, not two copies", "one implementation, not two"),
    (
        "the manual warning call",
        'warnings.warn("old_name is deprecated; use new_name", DeprecationWarning, stacklevel=2)',
    ),
    ("the decorator to avoid while unsupported", '@warnings.deprecated("...")'),
    ("no reaching for typing_extensions", "@typing_extensions.deprecated"),
    ("ask first for a new dependency", "Ask First"),
    ("stacklevel points at the caller", "stacklevel=2"),
    ("pytest's default warnings behavior", "and no `filterwarnings`"),
    ("the required assertion", "pytest.warns"),
    ("the mutmut selection rule", "pytest_add_cli_args_test_selection"),
    ("the already-selected example file", "`tests/test_core.py`"),
    ("the shippable-release check", "git tag --contains"),
    ("exit code is not the signal", "read the output, not the exit code"),
    ("no hand-edited changelog", "`CHANGELOG.md`"),
    ("no hand-edited version", "the version in `pyproject.toml`"),
    ("changelog step reconciled with policy", "that step is carried out by `doit release`"),
    ("checks the live setting instead of asserting it", "Check `major_version_zero` in"),
    (
        "true is the shipped default, bumps minor",
        "with `true`, the shipped default, that footer bumps MINOR",
    ),
    (
        "the release refuses 1.0 while it is on, cited to the tracking issue",
        "`doit release` refuses to release 1.0 or later until the setting is `false` (#881)",
    ),
    ("false bumps major", "with `false`, it bumps MAJOR"),
    ("tell the user rather than edit config", "Do not edit `pyproject.toml` to change it"),
    ("doit release generates it", "`doit release`"),
    ("breaking change footer", "`BREAKING CHANGE:`"),
    ("migration guide handoff", "carries the migration guide"),
    ("phases are separate prs", "Treat the two phases as separate PRs"),
    ("removal waits for shipping", "Step 5 must refuse to run until Phase 1 has actually shipped"),
)

# Sentences both bodies carry word for word. The first guards Step 3 -- the regression a shim can
# suffer silently; the second guards Step 5 -- the one operation this skill exists to gate.
TEST_GATE_SENTENCE = (
    "**Confirm `test_greet_warns` fails once the `warnings.warn` line is removed, "
    "then put the line back.**"
)
SHIP_GATE_SENTENCE = (
    "**Never run this step until Phase 1's warning has already shipped in a release.**"
)

# A fence whose contents are Python for the agent to write, not prose describing what to avoid.
PYTHON_FENCE = re.compile(r"```python\s*$")

# Decorators this skill must never tell an agent to actually write, only to avoid:
# `warnings.deprecated` does not exist on every version this project supports, and
# `typing_extensions.deprecated` would need a new runtime dependency (Ask First).
FORBIDDEN_DECORATORS = ("@warnings.deprecated", "@typing_extensions.deprecated")


def _normalized(text: str) -> str:
    """Collapse whitespace runs, so a sentence that wraps still matches."""
    return re.sub(r"\s+", " ", text)


def _wired_bodies() -> list[tuple[str, Path]]:
    """Return (surface, path) for each `deprecate-api` body this project wires."""
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


def _section(text: str, number: int) -> str:
    """Return heading *number* of normalized *text*: its heading up to the next heading."""
    start = text.find(STEPS[number - 1])
    if start == -1:
        return ""
    end = text.find(" ## ", start + 1) if number == len(STEPS) else text.find(STEPS[number])
    return text[start : end if end != -1 else len(text)]


def _python_lines(text: str) -> list[tuple[int, str]]:
    """Return (line_no, line) for every line inside a ```python code fence."""
    lines: list[tuple[int, str]] = []
    in_fence = in_python = False
    for line_no, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_python = not in_fence and bool(PYTHON_FENCE.match(stripped))
            in_fence = not in_fence
        elif in_python:
            lines.append((line_no, line))
    return lines


def test_every_wired_surface_has_a_body() -> None:
    """A project that wires any agent has somewhere to invoke `deprecate-api`."""
    if not _wired_bodies():
        pytest.skip("no AI agent is wired in this project")

    missing = [
        f"{surface}: {path.relative_to(REPO_ROOT)}"
        for surface, path in _wired_bodies()
        if not path.is_file()
    ]
    assert not missing, f"deprecate-api is missing on wired surfaces: {missing}"


def test_both_bodies_carry_the_contract() -> None:
    """Every wired `deprecate-api` body carries every contract element."""
    missing: list[str] = []
    for surface, text in _existing_bodies():
        missing += _contract_violations(surface, text)

    assert not missing, (
        "deprecate-api contract violations:\n  "
        + "\n  ".join(missing)
        + "\n\nBoth bodies must carry these steps. Change them together or not at all."
    )


def test_the_contract_scanner_detects_a_violation() -> None:
    """The scanner must fail on a body that drops a step, not merely pass on ours."""
    assert _contract_violations("synthetic", "a body that says none of the required things")


def test_the_phases_and_steps_run_in_the_same_order_on_every_surface() -> None:
    """Phase 1 (deprecate) precedes Phase 2 (remove), and their steps run 1 through 6, in order.

    Testing after documenting means an untested shim reaches the docs. Deleting before the
    deprecating release shipped means nobody was ever warned -- the two orderings this skill must
    never allow.
    """
    out_of_order = []
    for surface, text in _existing_bodies():
        positions = [text.find(step) for step in STEPS]
        if -1 in positions or positions != sorted(positions):
            out_of_order.append(f"{surface}: {dict(zip(STEPS, positions, strict=True))}")

    assert not out_of_order, (
        "deprecate-api phases/steps missing or out of order:\n  " + "\n  ".join(out_of_order)
    )


def test_the_gate_sentences_are_worded_identically_and_in_place() -> None:
    """The regression check closes Step 3; the ship-first check opens Step 5.

    A gate paraphrased per host drifts into a weaker version on one of them. A ship-first check
    that only appears after the delete already ran has caught nothing.
    """
    misplaced = []
    for surface, text in _existing_bodies():
        if TEST_GATE_SENTENCE not in _section(text, 4):
            misplaced.append(f"{surface}: the test-regression gate is not in Step 3")
        if SHIP_GATE_SENTENCE not in _section(text, 7):
            misplaced.append(f"{surface}: the ship-first gate is not in Step 5")

    assert not misplaced, (
        "\n  ".join(["gate sentences missing, reworded or moved:", *misplaced])
        + "\nReword every surface together or none."
    )


def test_the_policy_pointer_is_one_the_pointer_checks_can_see() -> None:
    """The file and the quoted section share a line, so `test_instruction_pointers` checks it.

    The quoted-heading check pairs a heading with a filename on the same line. A rewrap that
    splits them leaves the pointer in place and unchecked.
    """
    unseen = []
    for surface, path in _wired_bodies():
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        if not any("AGENTS.md" in ln and '"## Breaking Changes Policy"' in ln for ln in lines):
            unseen.append(surface)

    assert not unseen, f"no line pairs the file with its section in: {unseen}"


def test_no_body_tells_the_agent_to_write_the_forbidden_decorators() -> None:
    """`@warnings.deprecated` and `@typing_extensions.deprecated` are named only as what to avoid.

    `warnings.deprecated` does not exist on every version this project supports (measured: 3.12
    lacks it, 3.13 has it), and `typing_extensions` is not a runtime dependency here -- adding one
    is Ask First. A code example that actually uses either decorator would teach an agent to write
    code that fails on the floor version or reaches for an unapproved dependency.
    """
    offenders = []
    for surface, path in _wired_bodies():
        if not path.is_file():
            continue
        for line_no, line in _python_lines(path.read_text(encoding="utf-8")):
            stripped = line.strip()
            if any(stripped.startswith(dec) for dec in FORBIDDEN_DECORATORS):
                offenders.append(f"{surface}:{line_no}: {stripped}")

    assert not offenders, (
        "deprecate-api tells the agent to write a forbidden decorator:\n  " + "\n  ".join(offenders)
    )


def test_the_python_fence_scanner_detects_a_violation() -> None:
    """The fence scanner must catch a forbidden decorator in a Python block, and only there."""
    body = (
        "Do not reach for `@warnings.deprecated` in prose, but here it is in code:\n"
        "```python\n"
        '@warnings.deprecated("use new_name")\n'
        "def old_name(): ...\n"
        "```\n"
        "```text\n"
        '@warnings.deprecated("not python, not flagged")\n'
        "```\n"
    )
    offenders = [
        line.strip()
        for _, line in _python_lines(body)
        if any(line.strip().startswith(dec) for dec in FORBIDDEN_DECORATORS)
    ]

    assert offenders == ['@warnings.deprecated("use new_name")']


def test_shared_skill_declares_the_frontmatter_agents_activate_on() -> None:
    """Antigravity activates a skill by matching its `description:`; without one it never fires."""
    if not SHARED_SKILL.is_file():
        pytest.skip("the shared deprecate-api skill is not wired in this project")

    text = SHARED_SKILL.read_text(encoding="utf-8")
    assert text.startswith("---\n"), "SKILL.md must open with YAML frontmatter"
    frontmatter = text.split("---", 2)[1]
    assert "name: deprecate-api" in frontmatter
    assert "description:" in frontmatter
    # The description is the whole activation surface: it must name what an agent would be doing
    # when it needs this, not just the skill's title.
    for phrase in ("deprecat", "warn", "remove"):
        assert phrase in frontmatter.lower(), f"description never mentions {phrase!r}"

"""The two `add-dependency` bodies must agree, and neither may run `uv add`.

Adding a dependency crosses more gates than any other routine task: the Ask
First policy, a hook that blocks `uv add` for every agent, three placement
tables, mypy's missing-import rule, and the supply-chain checks (#829). Without
a skill, an agent that needs a package mid-task hits the hook and asks the user
to run `uv add x` with none of the rest done.

Two surfaces carry it -- `.agents/skills/` for Codex, Antigravity and Copilot,
`.claude/skills/` for Claude (generated from the former by `doit skills_sync`,
byte for byte) -- and whichever agent the user drives decides which body
applies. A step present in one and missing from the other is a control that
fires for some users and not others. The bodies are identical since #972; what
is asserted here is the contract and its ordering, which stays worth checking
on its own even though a diff would now also catch drift.

Scoped to the agents a project actually wires, per `tests/agent_roster.py`
(#690).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from agent_roster import agent_is_present

REPO_ROOT = Path(__file__).resolve().parents[1]

CLAUDE_COMMAND = REPO_ROOT / ".claude" / "skills" / "add-dependency" / "SKILL.md"
SHARED_SKILL = REPO_ROOT / ".agents" / "skills" / "add-dependency" / "SKILL.md"

# The steps both bodies take, in this order.
STEPS: tuple[str, ...] = (
    "### Step 1: Justify",
    "### Step 2: Place it",
    "### Step 3: Vet it",
    "### Step 4: Ask",
    "### Step 5: Finish",
    "### Step 6: Record",
)

# (label, substring) pairs both bodies must carry. Literal substrings rather
# than regexes, matching the convention in `test_template_migrate_skill.py`.
CONTRACT: tuple[tuple[str, str], ...] = (
    ("the policy it applies", "`.github/CONTRIBUTING.md`"),
    ("the section holding it", '"## Dependencies"'),
    ("runtime table", "`[project] dependencies`"),
    ("dev extra", "`[project.optional-dependencies] dev`"),
    ("security extra", "`[project.optional-dependencies] security`"),
    ("runtime placement rule", "**Runtime only if the installed package imports it.**"),
    ("PyPI lookup", "https://pypi.org/pypi/<package>/json"),
    ("license vetting", "**License.**"),
    ("python-version vetting", "`requires_python`"),
    ("maintenance vetting", "**Maintenance.**"),
    ("stub lookup", "https://pypi.org/pypi/types-<package>/json"),
    ("lower-bounded command", "`>=` lower bound"),
    ("override for an untyped package", "[[tool.mypy.overrides]]"),
    ("license task", "doit licenses"),
    ("audit task", "doit audit"),
    ("the security-extra trap", "a pass that checked nothing"),
    ("full validation", "doit check"),
    ("no other install route", "`uv pip install`"),
    ("never edit a failing test", "Never edit a test to make it pass."),
    ("justification kept in the PR", "PR description"),
)

# Sentences both bodies carry word for word, so neither can be softened on one
# surface. The first is the stop condition in the issue's success criteria; the
# second is what keeps `uv add` in the user's hands.
STOP_SENTENCE = (
    "**If the standard library or an existing dependency covers the need, stop here and use it.**"
)
HANDOFF_SENTENCE = (
    "**Stop here.** Do not run `uv add` yourself, and do not write the dependency into "
    "`pyproject.toml` by hand. Wait until the user has run the command and told you it succeeded."
)

# A fence whose contents are commands for the agent to run. `text` fences hold
# messages for the user, which is where the `uv add` command belongs.
SHELL_FENCE = re.compile(r"```(?:bash|sh|shell|zsh|console)\s*$")


def _normalized(text: str) -> str:
    """Collapse whitespace runs, so a sentence that wraps still matches."""
    return re.sub(r"\s+", " ", text)


def _wired_bodies() -> list[tuple[str, Path]]:
    """Return (surface, path) for each `add-dependency` body this project wires."""
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


def _shell_lines(text: str) -> list[tuple[int, str]]:
    """Return (line_no, line) for every line inside a shell code fence."""
    lines: list[tuple[int, str]] = []
    in_fence = in_shell = False
    for line_no, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_shell = not in_fence and bool(SHELL_FENCE.match(stripped))
            in_fence = not in_fence
        elif in_shell:
            lines.append((line_no, line))
    return lines


def test_every_wired_surface_has_a_body() -> None:
    """A project that wires any agent has somewhere to invoke `add-dependency`."""
    if not _wired_bodies():
        pytest.skip("no AI agent is wired in this project")

    missing = [
        f"{surface}: {path.relative_to(REPO_ROOT)}"
        for surface, path in _wired_bodies()
        if not path.is_file()
    ]
    assert not missing, f"add-dependency is missing on wired surfaces: {missing}"


def test_both_bodies_carry_the_contract() -> None:
    """Every wired `add-dependency` body carries every contract element."""
    missing: list[str] = []
    for surface, text in _existing_bodies():
        missing += _contract_violations(surface, text)

    assert not missing, (
        "add-dependency contract violations:\n  "
        + "\n  ".join(missing)
        + "\n\nBoth bodies must carry these steps. Change them together or not at all."
    )


def test_the_contract_scanner_detects_a_violation() -> None:
    """The scanner must fail on a body that drops a step, not merely pass on ours."""
    assert _contract_violations("synthetic", "a body that says none of the required things")


def test_the_steps_run_in_the_same_order_on_every_surface() -> None:
    """Justify, place, vet, ask, finish, record -- on every surface, in that order.

    Vetting after the ask means the user approves a package nobody has looked
    at. Finishing before the ask means the work is done before the decision is.
    """
    out_of_order = []
    for surface, text in _existing_bodies():
        positions = [text.find(step) for step in STEPS]
        if -1 in positions or positions != sorted(positions):
            out_of_order.append(f"{surface}: {dict(zip(STEPS, positions, strict=True))}")

    assert not out_of_order, "add-dependency steps missing or out of order:\n  " + "\n  ".join(
        out_of_order
    )


def test_the_gate_sentences_are_worded_identically_and_in_place() -> None:
    """The stop condition closes Step 1; the hand-off gate closes Step 4.

    A gate paraphrased per host drifts into a weaker version on one of them. And
    a stop condition that only appears after the ask has already cost the user a
    decision about a package the standard library would have covered.
    """
    misplaced = []
    for surface, text in _existing_bodies():
        if STOP_SENTENCE not in _step(text, 1):
            misplaced.append(f"{surface}: the stop sentence is not in Step 1")
        if HANDOFF_SENTENCE not in _step(text, 4):
            misplaced.append(f"{surface}: the hand-off sentence is not in Step 4")

    assert not misplaced, (
        "\n  ".join(["gate sentences missing, reworded or moved:", *misplaced])
        + "\nReword every surface together or none."
    )


def test_typing_is_settled_before_doit_check() -> None:
    """An untyped package gets its stub or override before the check runs.

    mypy has no global `ignore_missing_imports`, so the check fails on
    `[import-untyped]` otherwise -- and the quickest way to make it pass is the
    wrong one.
    """
    out_of_order = []
    for surface, text in _existing_bodies():
        finish = _step(text, 5)
        override = finish.find("[[tool.mypy.overrides]]")
        check = finish.find("doit check")
        if override == -1 or check == -1 or override > check:
            out_of_order.append(surface)

    assert not out_of_order, f"these bodies run doit check before settling typing: {out_of_order}"


def test_the_policy_pointer_is_one_the_pointer_checks_can_see() -> None:
    """The file and the quoted section share a line, so `test_instruction_pointers` checks it.

    The quoted-heading check pairs a heading with a filename on the same line. A
    rewrap that splits them leaves the pointer in place and unchecked.
    """
    unseen = []
    for surface, path in _wired_bodies():
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        if not any(".github/CONTRIBUTING.md" in ln and '"## Dependencies"' in ln for ln in lines):
            unseen.append(surface)

    assert not unseen, f"no line pairs the file with its section in: {unseen}"


def test_no_body_tells_the_agent_to_run_uv_add() -> None:
    """`uv add` belongs to the user; it never appears in a command for the agent to run.

    The hook blocks it anyway, but a skill that says to run it teaches the agent
    that the block is an obstacle -- and the next thing within reach is writing
    the entry into `pyproject.toml` by hand.
    """
    offenders = []
    for surface, path in _wired_bodies():
        if not path.is_file():
            continue
        for line_no, line in _shell_lines(path.read_text(encoding="utf-8")):
            if "uv add" in line:
                offenders.append(f"{surface}:{line_no}: {line.strip()}")

    assert not offenders, "add-dependency tells the agent to run uv add:\n  " + "\n  ".join(
        offenders
    )


def test_the_shell_fence_scanner_detects_a_violation() -> None:
    """The fence scanner must catch `uv add` in a command block, and only there."""
    body = (
        "```text\nuv add httpx\n```\n"
        "1. Then:\n   ```bash\n   uv add requests\n   ```\n"
        "```\nuv add attrs\n```\n"
    )
    shell = [line.strip() for _, line in _shell_lines(body)]

    assert shell == ["uv add requests"]


def test_shared_skill_declares_the_frontmatter_agents_activate_on() -> None:
    """Antigravity activates a skill by matching its `description:`; without one it never fires."""
    if not SHARED_SKILL.is_file():
        pytest.skip("the shared add-dependency skill is not wired in this project")

    text = SHARED_SKILL.read_text(encoding="utf-8")
    assert text.startswith("---\n"), "SKILL.md must open with YAML frontmatter"
    frontmatter = text.split("---", 2)[1]
    assert "name: add-dependency" in frontmatter
    assert "description:" in frontmatter
    # The description is the whole activation surface: it must name what an agent
    # would be doing when it needs this, not just the skill's title.
    for phrase in ("package", "dependency", "uv add"):
        assert phrase in frontmatter.lower(), f"description never mentions {phrase!r}"

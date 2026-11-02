"""The `report-template-bug` skill must keep its steps, and never file by hand (#1090).

An agent in a project made from the template that finds a bug in shipped tooling has three bad
options: patch it locally (the fix drifts and is lost on the next sync), hand it to a human, or run
`gh issue create -R`, which the command hook blocks. The skill is the fourth, and its steps are the
control: diff against the recorded commit, reproduce, check the version, look for a duplicate, stop
on a security finding, file with `doit issue --upstream`, leave the local file alone.

Scoped to the agents a project actually wires, per `tests/agent_roster.py` (#690).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from agent_roster import agent_is_present

REPO_ROOT = Path(__file__).resolve().parents[1]

CLAUDE_COPY = REPO_ROOT / ".claude" / "skills" / "report-template-bug" / "SKILL.md"
SHARED_SKILL = REPO_ROOT / ".agents" / "skills" / "report-template-bug" / "SKILL.md"

STEPS: tuple[str, ...] = (
    "### Step 0: Refuse in the template repository",
    "### Step 1: Confirm it is upstream's bug",
    "### Step 2: Reproduce it",
    "### Step 3: Check the template version",
    "### Step 4: Look for a duplicate",
    "### Step 5: Stop on a security finding",
    "### Step 6: File it",
    "### Step 7: Leave the local file alone",
)

# (step, label, substring) triples the body must carry, each inside the step it belongs to.
CONTRACT: tuple[tuple[int, str, str], ...] = (
    (0, "the template slug", "endavis/pyproject-template"),
    (1, "the recorded commit setting", "`[template].commit`"),
    (1, "the fetch at the recorded commit", "?ref=<sha>"),
    (1, "a customization stops the run", "local customization"),
    (2, "keep the command and output", "exact command and its output"),
    (3, "the sync skill", "`template-sync`"),
    (4, "the duplicate search", "gh issue list -R endavis/pyproject-template"),
    (4, "comment instead of filing", "add the reproduction as a comment"),
    (5, "nothing public", "file nothing public"),
    (5, "the security policy", "security/policy"),
    (6, "the filing command", "doit issue --upstream --type=bug"),
    (7, "no silent patch", "Do not silently patch the template file"),
    (7, "a marked stopgap links the issue", "links the upstream issue"),
)

SHELL_FENCE = re.compile(r"```(?:bash|sh|shell|zsh|console)\s*$")
# Tokens the skill must never put in a command it tells the agent to run.
FORBIDDEN_IN_SHELL: tuple[str, ...] = ("gh issue create", "security-advisories")


def _bodies() -> list[tuple[str, Path]]:
    bodies: list[tuple[str, Path]] = []
    if agent_is_present("claude"):
        bodies.append(("claude", CLAUDE_COPY))
    if any(agent_is_present(a) for a in ("codex", "antigravity", "copilot")):
        bodies.append(("shared", SHARED_SKILL))
    return bodies


def _text(path: Path) -> str:
    """Return the body with wrapped lines joined, so a sentence that wraps still matches."""
    return re.sub(r"[ \t]*\n[ \t]*", " ", path.read_text(encoding="utf-8"))


def _step(text: str, number: int) -> str:
    start = text.find(STEPS[number])
    if start == -1:
        return ""
    end = text.find(STEPS[number + 1]) if number + 1 < len(STEPS) else len(text)
    return text[start:end]


def test_a_body_exists_on_every_wired_surface() -> None:
    if not _bodies():
        pytest.skip("no AI agent is wired in this project")
    missing = [s for s, p in _bodies() if not p.is_file()]
    assert not missing, f"report-template-bug is missing on: {missing}"


def test_steps_run_in_order() -> None:
    for surface, path in _bodies():
        text = path.read_text(encoding="utf-8")
        positions = [text.find(step) for step in STEPS]
        assert -1 not in positions, f"{surface} is missing a step: {positions}"
        assert positions == sorted(positions), f"{surface} steps are out of order"


def test_each_step_carries_its_contract() -> None:
    missing = []
    for surface, path in _bodies():
        text = _text(path)
        for number, label, needle in CONTRACT:
            if needle not in _step(text, number):
                missing.append(f"{surface}: Step {number} lacks the {label} ({needle!r})")
    assert not missing, "\n".join(missing)


def test_contract_scanner_detects_a_violation() -> None:
    assert _step("a body with no steps", 1) == ""


def test_no_shell_fence_files_by_hand() -> None:
    offenders = []
    for surface, path in _bodies():
        in_fence = in_shell = False
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("```"):
                in_shell = not in_fence and bool(SHELL_FENCE.match(stripped))
                in_fence = not in_fence
            elif in_shell:
                offenders += [
                    f"{surface}:{line_no}: {line.strip()}"
                    for token in FORBIDDEN_IN_SHELL
                    if token in line
                ]
    assert not offenders, "\n".join(offenders)


def test_frontmatter_names_the_skill_and_its_triggers() -> None:
    if not SHARED_SKILL.is_file():
        pytest.skip("shared skill not present")
    text = SHARED_SKILL.read_text(encoding="utf-8")
    match = re.match(r"---\nname: (.+)\ndescription: (.+)\n---\n", text)
    assert match is not None
    assert match.group(1) == "report-template-bug"
    assert "report this upstream" in match.group(2)


def test_claude_copy_matches_the_shared_source() -> None:
    if not (CLAUDE_COPY.is_file() and SHARED_SKILL.is_file()):
        pytest.skip("both copies are not present")
    assert CLAUDE_COPY.read_bytes() == SHARED_SKILL.read_bytes()

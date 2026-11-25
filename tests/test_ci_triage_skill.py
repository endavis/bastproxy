"""The two `ci-triage` bodies must agree and carry the triage procedure (#1330).

Two surfaces carry it: `.agents/skills/` for Codex, Antigravity and Copilot, and `.claude/skills/`
for Claude, generated from the former by `doit skills_sync`. Scoped to the agents a project wires,
per `tests/agent_roster.py` (#690).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from agent_roster import agent_is_present

REPO_ROOT = Path(__file__).resolve().parents[1]

CLAUDE_COMMAND = REPO_ROOT / ".claude" / "skills" / "ci-triage" / "SKILL.md"
SHARED_SKILL = REPO_ROOT / ".agents" / "skills" / "ci-triage" / "SKILL.md"

CONTRACT: tuple[tuple[str, str], ...] = (
    ("find the failing PR checks", "gh pr checks"),
    ("read the failed log", "gh run view <run-id> --log-failed"),
    ("read one job's log", "gh run view <run-id> --log --job <job-id>"),
    ("the raw logs endpoint redirects", "returns a redirect"),
    ("reproduce on the failing Python", "UV_PYTHON=<version>"),
    ("hand the fix over", "`implement-issue`"),
    ("measure with the helper", "doit ci_timings --run=<new> --compare=<old>"),
    ("the per-test diff", "doit ci_timings --run=<new> --compare=<old> --tests"),
    ("the cache log line", "Log the uv cache result"),
    ("the cache values", "`true`, `false` or `unknown`"),
    ("package slowdowns go to perf-change", "`perf-change`"),
    ("verified claims", "`verified-claims`"),
    ("never edit a failing test", "Never edit a test to make it pass."),
    ("never re-run for green", "Never re-run CI just to get a green result."),
)

MODES: tuple[str, ...] = ("### Failure mode", "### Performance mode", "## Never")


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _wired_bodies() -> list[tuple[str, Path]]:
    bodies: list[tuple[str, Path]] = []
    if agent_is_present("claude"):
        bodies.append(("claude", CLAUDE_COMMAND))
    if any(agent_is_present(a) for a in ("codex", "antigravity", "copilot")):
        bodies.append(("shared", SHARED_SKILL))
    return bodies


def _existing_bodies() -> list[tuple[str, str]]:
    return [
        (surface, _normalized(path.read_text(encoding="utf-8")))
        for surface, path in _wired_bodies()
        if path.is_file()
    ]


def _violations(surface: str, text: str) -> list[str]:
    return [
        f"{surface} is missing {label} ({needle!r})"
        for label, needle in CONTRACT
        if needle not in text
    ]


def test_every_wired_surface_has_a_body() -> None:
    if not _wired_bodies():
        pytest.skip("no AI agent is wired in this project")
    missing = [str(p.relative_to(REPO_ROOT)) for _, p in _wired_bodies() if not p.is_file()]
    assert not missing, f"ci-triage is missing on wired surfaces: {missing}"


def test_both_bodies_carry_the_contract() -> None:
    missing: list[str] = []
    for surface, text in _existing_bodies():
        missing += _violations(surface, text)
    assert not missing, "ci-triage contract violations:\n  " + "\n  ".join(missing)


def test_the_contract_scanner_detects_a_violation() -> None:
    assert _violations("synthetic", "a body that says none of the required things")


def test_the_modes_run_in_order_on_every_surface() -> None:
    bad = []
    for surface, text in _existing_bodies():
        positions = [text.find(m) for m in MODES]
        if -1 in positions or positions != sorted(positions):
            bad.append(f"{surface}: {positions}")
    assert not bad, "ci-triage modes missing or out of order: " + "; ".join(bad)


def test_shared_skill_declares_the_frontmatter_agents_activate_on() -> None:
    if not SHARED_SKILL.is_file():
        pytest.skip("the shared ci-triage skill is not wired in this project")
    frontmatter = SHARED_SKILL.read_text(encoding="utf-8").split("---", 2)[1]
    assert "name: ci-triage" in frontmatter
    assert "description:" in frontmatter
    for phrase in ("ci run fails", "slower", "ci_timings"):
        assert phrase in frontmatter.lower(), f"description never mentions {phrase!r}"

"""The shared `implement-issue` skill carries the pieces the plan for #976 promised.

One skill replaces the old `/claude:plan` -> `/claude:implement` -> `/ghi-finalize`
chain and the 28-file per-agent plan/implement matrix: it decides whether to plan,
posts the plan without an approval wait, implements with tests, validates, commits,
pushes, opens the PR, and fixes CI for up to 3 rounds. These tests hold the skill
source to the shape the plan described, the same way `tests/test_cross_agent_contract.py`
holds its literals to the workflow contract.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = REPO_ROOT / ".agents" / "skills" / "implement-issue"
SKILL_FILE = SKILL_DIR / "SKILL.md"
IMPLEMENT_WORKER = REPO_ROOT / ".claude" / "agents" / "implement-worker.md"


def _frontmatter(text: str) -> dict[str, object]:
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match is not None, "SKILL.md must start with YAML frontmatter"
    data = yaml.safe_load(match.group(1))
    assert isinstance(data, dict)
    return data


def test_skill_source_exists() -> None:
    assert SKILL_FILE.is_file(), f"missing implement-issue skill: {SKILL_FILE}"


def test_frontmatter_name_matches_the_folder() -> None:
    data = _frontmatter(SKILL_FILE.read_text(encoding="utf-8"))
    assert data["name"] == SKILL_DIR.name


def test_description_triggers_on_implement_issue() -> None:
    data = _frontmatter(SKILL_FILE.read_text(encoding="utf-8"))
    description = str(data["description"]).lower()
    assert "implement issue" in description


def test_planning_criteria_are_present() -> None:
    """Plan only when needs-adr, file count, or more than one viable approach applies."""
    text = SKILL_FILE.read_text(encoding="utf-8")
    assert "needs-adr" in text
    assert "3 files" in text
    assert "more than one approach" in text


def test_ci_round_cap_is_stated() -> None:
    text = SKILL_FILE.read_text(encoding="utf-8")
    assert "3 rounds" in text or "At most 3 rounds" in text
    assert "require-label" in text


def test_ask_first_stop_list_is_present() -> None:
    text = SKILL_FILE.read_text(encoding="utf-8")
    assert "Ask-first triggers" in text
    for trigger in (
        "new dependency",
        "breaking change",
        "failing test",
        "blocked command",
    ):
        assert trigger in text, f"ask-first list is missing {trigger!r}"


def test_both_briefs_are_present() -> None:
    text = SKILL_FILE.read_text(encoding="utf-8")
    assert "## Planner brief" in text
    assert "## Coder brief" in text


def test_never_merges_or_closes_the_issue() -> None:
    text = SKILL_FILE.read_text(encoding="utf-8")
    assert "ready-to-merge" in text
    assert "never merge" in text or "never merges" in text
    assert "close the issue" in text or "closes the issue" in text


def test_implement_worker_points_at_the_coder_brief() -> None:
    text = IMPLEMENT_WORKER.read_text(encoding="utf-8")
    assert "Coder brief" in text
    assert "implement-issue" in text

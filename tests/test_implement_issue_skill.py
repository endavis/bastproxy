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
IMPLEMENT_PLANNER = REPO_ROOT / ".claude" / "agents" / "implement-planner.md"


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


def test_implement_planner_exists_and_runs_on_opus() -> None:
    assert IMPLEMENT_PLANNER.is_file()
    text = IMPLEMENT_PLANNER.read_text(encoding="utf-8")
    assert "Planner brief" in text
    assert _frontmatter(text)["model"] == "opus"


def test_implement_worker_declares_no_model() -> None:
    """Copilot's `task` tool reads this file; an unknown model fails `invalid_model` (#1081)."""
    text = IMPLEMENT_WORKER.read_text(encoding="utf-8")
    assert "model" not in _frontmatter(text)


def test_claude_host_note_names_both_subagents() -> None:
    text = SKILL_FILE.read_text(encoding="utf-8")
    note = text.split("## Per-host subagent notes", 1)[1].split("- **Codex CLI:**", 1)[0]
    assert "implement-planner" in note
    assert "implement-worker" in note


def _section(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


def _skill_text() -> str:
    return SKILL_FILE.read_text(encoding="utf-8")


def test_step_3_states_the_host_writes_condition_and_the_review() -> None:
    step3 = _section(_skill_text(), "### Step 3:", "### Step 4:")
    assert "findings comment" in step3
    assert "cites" in step3
    assert "Plan-review brief" in step3
    assert "second review" in step3
    assert "changed the plan's design" in step3


def test_planner_brief_treats_passed_findings_as_settled() -> None:
    planner = _section(_skill_text(), "## Planner brief", "## Plan-review brief")
    assert "settled" in planner
    assert "flag in the" in planner
    assert "contradicts" in planner or "any the code contradicts" in planner


def test_planner_brief_plan_shape_carries_code_locations() -> None:
    planner = _section(_skill_text(), "## Planner brief", "## Plan-review brief")
    for token in (
        "Base commit:",
        "Symbols:",
        "Pattern:",
        "Tests:",
        "### Test Commands",
        "## Implementation Plan for #<n>: <title>",
        "### Files to Create/Modify",
    ):
        assert token in planner


def test_planner_brief_treats_line_ranges_as_hints() -> None:
    planner = _section(_skill_text(), "## Planner brief", "## Plan-review brief")
    assert "The symbol is the pointer; line ranges are hints" in planner


def test_coder_brief_reads_from_the_plan_locations() -> None:
    coder = _section(_skill_text(), "## Coder brief", "## Per-host subagent notes")
    assert "named symbols and ranges, not whole files" in coder
    assert "base commit differs from `HEAD`" in coder
    assert "each read outside its pointers" in coder


def test_implement_worker_starts_from_the_plan_locations() -> None:
    text = IMPLEMENT_WORKER.read_text(encoding="utf-8")
    assert "named symbols" in text
    assert "deviation" in text


def test_coder_brief_summary_has_checks_run_and_reads_fields() -> None:
    coder = _section(_skill_text(), "## Coder brief", "## Per-host subagent notes")
    assert "**Checks run**" in coder
    assert "**Reads beyond the plan's pointers**" in coder
    assert "marked run or skipped with a reason" in coder
    assert "each marked as a deviation" in coder


def test_step_5_reads_the_coders_two_summary_fields() -> None:
    step5 = _section(_skill_text(), "### Step 5", "### Step 6")
    assert "**Checks run**" in step5
    assert "**Reads beyond the plan's pointers**" in step5
    assert "unmet" in step5
    assert "Step 8 reports" in step5


def test_step_8_reports_the_coders_field_deviations() -> None:
    step8 = _section(_skill_text(), "### Step 8", "## Ask-first triggers")
    assert "**Checks run**" in step8
    assert "**Reads beyond the plan's pointers**" in step8


def test_implement_worker_returns_the_two_summary_fields() -> None:
    text = IMPLEMENT_WORKER.read_text(encoding="utf-8")
    assert "**Checks run**" in text
    assert "**Reads beyond the plan's pointers**" in text


def test_plan_review_brief_reads_the_plan_pointers_within_a_budget() -> None:
    review = _section(_skill_text(), "## Plan-review brief", "## Coder brief")
    assert "Symbols:" in review
    assert "whole file only when the plan rewrites most of it" in review
    assert "about 15 tool calls" in review
    assert "direct callers" in review
    assert "do not probe" in review
    assert "NO ISSUES" in review
    assert "worktree root" in review
    assert "cd <root> &&" in review


def test_coder_brief_has_a_checking_budget_without_doit_check() -> None:
    coder = _section(_skill_text(), "## Coder brief", "## Per-host subagent notes")
    assert "revert check" in coder
    assert "`git show HEAD:<path>`" in coder
    assert "WIP commit" in coder
    assert "`uv run doit lint`" in coder
    assert "`uv run doit type_check`" in coder
    assert "no extra mutmut runs, no flakiness reruns" in coder
    assert (
        "Do not run\n   `uv run doit check`; the full `doit check` runs once, in Step 5." in coder
    )
    assert "every check command you ran" in coder


def test_step_5_owns_the_single_full_check() -> None:
    text = _skill_text()
    step5 = _section(text, "### Step 5:", "### Step 6:")
    assert "uv run doit check" in step5
    assert "once" in step5
    assert "verified-claims" in step5
    step4 = _section(text, "### Step 4:", "### Step 5:")
    assert "runs\nonce, in Step 5" in step4 or "once, in Step 5" in step4.replace("\n", " ")


def test_implement_worker_leaves_doit_check_to_step_5() -> None:
    text = IMPLEMENT_WORKER.read_text(encoding="utf-8")
    description = str(_frontmatter(text)["description"])
    assert "runs `doit check`" not in description
    assert "Step 5" in text
    assert "Do NOT run `uv run doit check`" in text


def test_implement_planner_also_runs_the_plan_review_brief() -> None:
    text = IMPLEMENT_PLANNER.read_text(encoding="utf-8")
    assert "Plan-review brief" in text
    assert _frontmatter(text)["model"] == "opus"

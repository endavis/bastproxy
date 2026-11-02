"""`implement-issue` works in a per-issue worktree (#1095, ADR-9027)."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL = REPO_ROOT / ".agents" / "skills" / "implement-issue" / "SKILL.md"
WALKTHROUGH = REPO_ROOT / "docs" / "development" / "ai" / "first-5-minutes.md"
AGENTS_DIR = REPO_ROOT / ".claude" / "agents"


def _skill() -> str:
    return SKILL.read_text(encoding="utf-8")


def _section(text: str, start: str, end: str) -> str:
    begin = text.index(start)
    return text[begin : text.index(end, begin)]


def _step1() -> str:
    return _section(_skill(), "### Step 1:", "### Step 2:")


def test_step1_creates_the_worktree_with_doit() -> None:
    assert re.search(r"uv run doit worktree --branch=<type>/<n>-", _step1())


def test_step1_resumes_an_existing_worktree() -> None:
    assert "git worktree list --porcelain" in _step1()


def test_step1_no_longer_switches_the_checkout() -> None:
    step1 = _step1()
    assert "git checkout main" not in step1
    assert "git checkout -b" not in step1


def test_step1_stops_when_a_branch_exists_without_a_worktree() -> None:
    step1 = _step1()
    assert "no worktree, stop and ask" in step1
    assert "git worktree add -b" in step1


def test_every_context_dir_is_inside_the_worktree() -> None:
    outs = re.findall(r"delegation_context[^\n]*--out=(\S+)", _skill())
    assert outs
    local = [o for o in outs if "<context-dir>" not in o]
    assert local
    assert all(o.startswith("$WORKTREE/tmp/agents/") for o in local)


def test_later_steps_run_through_uv_run_and_never_active() -> None:
    text = _skill()
    for command in ("uv run doit check", "uv run doit docs_build", "uv run doit pr "):
        assert command in text
    for line in text.splitlines():
        if "--active" in line:
            assert "never pass `--active`" in line


def test_both_briefs_take_the_worktree_root() -> None:
    text = _skill()
    planner = _section(text, "## Planner brief", "## Coder brief")
    coder = _section(text, "## Coder brief", "## Per-host subagent notes")
    for brief in (planner, coder):
        assert "worktree root" in brief
        assert "absolute path" in brief
        assert "cd <root> &&" in brief


def test_agent_definitions_name_the_worktree_root() -> None:
    for name in ("implement-worker.md", "implement-planner.md"):
        text = (AGENTS_DIR / name).read_text(encoding="utf-8")
        assert "worktree root" in text
        assert "cd <root> &&" in text


def test_step8_reports_the_worktree_and_the_merge_command() -> None:
    step8 = _section(_skill(), "### Step 8:", "## Ask-first triggers")
    assert "$WORKTREE" in step8
    assert "uv run doit pr_merge --pr=" in step8


def test_walkthrough_step3_mentions_the_worktree() -> None:
    text = WALKTHROUGH.read_text(encoding="utf-8")
    assert "worktrees/" in _section(text, '### 3. "implement issue 42"', "### 4.")


def test_skill_never_cds_to_the_main_checkout() -> None:
    text = SKILL.read_text(encoding="utf-8")
    assert "Never `cd` to the main checkout" in text
    assert "git -C <main-checkout>" in text


def test_coder_brief_forbids_bare_git_stash() -> None:
    text = SKILL.read_text(encoding="utf-8")
    brief = text[text.index("## Coder brief") : text.index("## Per-host subagent notes")]
    assert "Never use a bare `git stash`" in brief
    assert "git show HEAD:<path>" in brief
    assert "WIP commit" in brief


def test_implement_worker_carries_both_rules() -> None:
    text = (AGENTS_DIR / "implement-worker.md").read_text(encoding="utf-8")
    assert "git -C <main-checkout>" in text
    assert "Never use a bare `git stash`" in text

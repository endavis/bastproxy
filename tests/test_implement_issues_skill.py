"""The `implement-issues` skill runs several issues in parallel worktrees (#1097, ADR-9028)."""

from __future__ import annotations

import re
from pathlib import Path

from tools.doit.skills import SHARED_SKILLS

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL = REPO_ROOT / ".agents" / "skills" / "implement-issues" / "SKILL.md"
IMPLEMENT_ISSUE = REPO_ROOT / ".agents" / "skills" / "implement-issue" / "SKILL.md"
AI_DOCS = REPO_ROOT / "docs" / "development" / "ai"
AGENTS_MD = REPO_ROOT / "AGENTS.md"


def _text() -> str:
    return SKILL.read_text(encoding="utf-8")


def _frontmatter() -> dict[str, str]:
    match = re.match(r"---\n(.*?)\n---\n", _text(), re.DOTALL)
    assert match, "SKILL.md has no frontmatter"
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def _section(start: str, end: str) -> str:
    text = _text()
    begin = text.index(start)
    return text[begin : text.index(end, begin)]


def test_frontmatter_and_registration() -> None:
    fm = _frontmatter()
    assert fm["name"] == "implement-issues"
    assert "implement issues" in fm["description"]
    assert "implement-issues" in SHARED_SKILLS


def test_preflight_comes_before_worktree_creation() -> None:
    text = _text()
    create = text.index("uv run doit worktree --branch=<type>/<n>-")
    assert text.index("gh issue view") < create
    assert text.index("overlap") < create
    assert text.index("check only") < create


def test_check_only_stops_before_step_2() -> None:
    step1 = _section("### Step 1:", "### Step 2:")
    assert "`check only`" in step1
    assert "no worktree is created" in step1


def test_worktrees_are_created_in_sequence_from_the_main_checkout() -> None:
    step2 = _section("### Step 2:", "### Step 3:")
    assert "one after another" in step2
    assert "main checkout" in step2


def test_main_checkout_is_never_switched_or_inspected_except_with_git_c() -> None:
    text = _text()
    assert "git checkout" not in text
    assert "git pull" not in text
    assert "--active" not in text
    assert "git -C" in text
    for match in re.finditer(r"git stash", text):
        assert text[: match.start()].endswith("bare `"), "bare git stash rule only"


def test_one_background_agent_per_issue_with_the_absolute_worktree() -> None:
    step3 = _section("### Step 3:", "### Step 4:")
    assert "run_in_background: true" in step3
    assert "general-purpose" in step3
    assert 'cd "<WORKTREE>" &&' in step3
    assert "do no phase 1 coding" in step3
    assert "`--max` counts only these" in step3


def test_concurrency_cap() -> None:
    text = _text()
    assert "default 2" in text
    assert "--max=" in text


def test_ask_first_contract() -> None:
    step3 = _section("### Step 3:", "### Step 4:")
    assert "ASK-FIRST:" in step3
    assert "that issue only" in step3
    assert "the others continue" in step3


def test_merge_gate_stays_with_the_user() -> None:
    text = _text()
    never = text[text.index("## Never") :]
    assert "--add-label" not in text
    assert "gh pr merge" not in text
    assert re.search(r"[Nn]ever apply the `ready-to-merge` label, merge a PR, or close", never)
    assert "merge-pr" in text


def test_host_support_names_every_host() -> None:
    host = _text()[_text().index("## Host support") :]
    for name in ("Claude Code", "Codex", "Copilot", "Antigravity"):
        assert name in host
    assert "one after another" in host


def test_docs_register_the_skill() -> None:
    slash = (AI_DOCS / "slash-commands.md").read_text(encoding="utf-8")
    assert "### implement issues A, B" in slash
    assert "Twenty workflow skills" in slash
    assert "implement issues" in (AI_DOCS / "first-5-minutes.md").read_text(encoding="utf-8")
    delegation = (AI_DOCS / "cross-agent-delegation.md").read_text(encoding="utf-8")
    assert "## Parallel issues (`implement-issues`)" in delegation
    assert "slash-commands.md#implement-issues-a-b" in AGENTS_MD.read_text(encoding="utf-8")


def test_implement_issue_points_at_implement_issues() -> None:
    text = IMPLEMENT_ISSUE.read_text(encoding="utf-8")
    assert "use `implement-issues`" in text
    assert "../implement-issues/SKILL.md" in text


def test_step_3_prompt_names_the_plan_review_brief() -> None:
    step3 = _section("### Step 3:", "### Step 4:")
    assert "Plan-review brief" in step3


def test_per_issue_prompt_stops_after_push() -> None:
    """Phase 1 agents commit and push but open no PR (#1139)."""
    step3 = _section("### Step 3:", "### Step 4:")
    assert "git push -u origin" in step3
    assert "Do not run `doit pr` or Step 7" in step3
    assert "open the PR and run the CI loop" not in step3


def test_per_issue_prompt_keeps_inline_exception_off() -> None:
    step3 = _section("### Step 3:", "### Step 4:")
    assert "Step 4's inline exception does not apply" in step3


def _step4() -> str:
    return _section("### Step 4:", "### Step 5:")


def test_phase_2_opens_prs_one_at_a_time() -> None:
    step4 = _step4()
    for needle in (
        "git rebase origin/main",
        "--force-with-lease origin <branch>",
        "uv run doit pr",
        "at most 3 rounds",
        "gh pr view <pr> --json state",
    ):
        assert needle in step4, needle
    order = [
        step4.index(n)
        for n in (
            "git rebase origin/main",
            "--force-with-lease",
            "uv run doit pr",
        )
    ]
    assert order == sorted(order)


def test_phase_2_leaves_rebased_branch_to_ci() -> None:
    step4 = " ".join(_step4().split())
    assert "merge-base --is-ancestor origin/main HEAD" in step4
    assert "Do not run `uv run doit check` again" in step4
    assert "re-check" not in step4
    assert "brought changes" not in step4
    assert "CI checked the rebased branch" in step4


def test_rebase_conflict_is_ask_first() -> None:
    assert "git rebase --abort" in _step4()
    assert "ASK-FIRST: rebase conflict" in _step4()
    ask = _text()[_text().index("## Ask-first triggers") : _text().index("## Never")]
    assert "rebase conflict" in ask


def test_overlap_orders_phase_2_instead_of_blocking() -> None:
    step1 = _section("### Step 1:", "### Step 2:")
    assert "sets the phase 2 order" in step1
    assert "one after another" not in step1
    ask = _text()[_text().index("## Ask-first triggers") : _text().index("## Never")]
    assert "overlap" not in ask
    assert "empty" not in ask


def test_phase_2_has_no_agent_prompt() -> None:
    step4 = _step4()
    assert "general-purpose" not in step4
    assert "run_in_background" not in step4
    assert "\n> " not in step4


def test_orchestrator_runs_phase_2_itself() -> None:
    step4 = _step4()
    assert "You, the orchestrator, run phase 2 yourself" in step4
    assert 'git -C <WORKTREE> …` or `cd "<WORKTREE>" && …`' in step4
    assert "while other phase 1 agents may still run" in step4
    assert "`implement-worker` subagent" in step4
    assert "Addresses #<n>" in step4


def test_never_forbids_a_subagent_opening_a_pr() -> None:
    text = _text()
    never = text[text.index("## Never") :]
    assert "Never let a subagent open a PR." in never
    assert "Never rebase or push as the orchestrator" not in text
    assert "Never edit files as the orchestrator" not in text


def test_resume_rebuilds_queue_from_pushed_branches() -> None:
    step4 = _step4()
    assert "gh pr list --head" in step4
    assert "@{u}" in step4


def test_unmet_requirement_is_an_ask_first_trigger_and_findings_relay_whole() -> None:
    """Step 5 lists requirements, an unmet one asks first, relays stay whole (#1145)."""
    issue = " ".join(IMPLEMENT_ISSUE.read_text(encoding="utf-8").split())
    assert "Build a requirements list before committing" in issue
    assert "never a note in the PR body" in issue
    assert "cannot be met as written" in issue
    assert "requirement-by-requirement met/unmet table" in issue
    issues = " ".join(_text().split())
    assert "relay the finding itself, not a narrowed fix" in issues
    assert "cannot be met as written" in issues

"""`/ghi-status` must not suggest a command that refuses the state it reports (#865).

For a merged PR it suggested `doit pr_merge --auto-close`. That task refuses any
PR that is not open ("PR is not open (state: MERGED)", pinned by
`TestMergePr.test_refuses_a_pr_that_is_not_open`), so it closed nothing.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GHI_STATUS = REPO_ROOT / ".agents" / "skills" / "ghi-status" / "SKILL.md"
MERGED = "On feature branch, PR exists (merged)"


def _suggestion(state: str) -> str:
    """Return the suggestion the state table gives for *state*."""
    rows = [
        line
        for line in GHI_STATUS.read_text(encoding="utf-8").splitlines()
        if line.startswith(f"| {state} |")
    ]
    assert len(rows) == 1, f"expected one row for {state!r} in {GHI_STATUS.name}"
    return rows[0].split("|")[2]


def test_a_merged_pr_is_not_sent_to_pr_merge() -> None:
    assert "pr_merge" not in _suggestion(MERGED)


def test_a_merged_pr_closes_its_issue_with_the_standard_comment() -> None:
    """The closing comment AGENTS.md asks for: "Addressed in PR #XXX"."""
    suggestion = _suggestion(MERGED)
    assert "gh issue close <N>" in suggestion
    assert "Addressed in PR #" in suggestion

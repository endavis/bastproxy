"""The walkthrough's worktree section relies on what `implement-issue` does (#866, #976).

It tells the reader to create the issue's branch in a worktree before running
"implement issue 42", because `implement-issue` resumes on it — skipping branch
creation, and with it `git checkout main` — when the current branch already
belongs to the issue. If the skill stops doing that, the walkthrough sends
readers into a failing checkout, so these tests hold the two files together.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WALKTHROUGH = REPO_ROOT / "docs" / "development" / "ai" / "first-5-minutes.md"
IMPLEMENT_ISSUE = REPO_ROOT / ".agents" / "skills" / "implement-issue" / "SKILL.md"
HEADING = "## When your checkout holds other work"


def _section() -> str:
    """Return the walkthrough's worktree section, up to the next ``## `` heading."""
    text = WALKTHROUGH.read_text(encoding="utf-8")
    start = text.index(HEADING)
    end = text.find("\n## ", start + len(HEADING))
    return text[start:] if end == -1 else text[start:end]


def test_implement_skips_branch_creation_on_the_issue_branch() -> None:
    text = IMPLEMENT_ISSUE.read_text(encoding="utf-8")
    assert "If already on `<type>/<n>-*`, resume on it" in text
    assert "skip branch creation" in text


def test_the_walkthrough_names_the_branch_for_the_issue() -> None:
    """Otherwise "implement issue 42" does not recognize the worktree's branch."""
    assert re.search(r"doit worktree --branch=[a-z]+/42-", _section())


def test_the_walkthrough_merges_a_worktree_pr_by_number() -> None:
    """From the main checkout, `doit pr_merge` without `--pr` looks up that checkout's branch."""
    assert "doit pr_merge --pr=" in _section()

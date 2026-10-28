"""The `merge-pr` skill must keep its merge gate and be registered in the docs.

Merging a finished PR was a hand-typed request whose "fully addressed" judgment varied between
runs (#1062). The skill encodes the order: preconditions, CI, per-issue judgment, merge, report.
It must never take over the human gate: it does not add `ready-to-merge` and does not bypass a
block.
"""

from __future__ import annotations

import re
from pathlib import Path

from tools.doit.skills import SHARED_SKILLS

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL = REPO_ROOT / ".agents" / "skills" / "merge-pr" / "SKILL.md"
SLASH_COMMANDS = REPO_ROOT / "docs" / "development" / "ai" / "slash-commands.md"
AGENTS_MD = REPO_ROOT / "AGENTS.md"

NUMBER_WORDS = {17: "Seventeen", 18: "Eighteen", 19: "Nineteen", 20: "Twenty"}


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


def _never_section() -> str:
    match = re.search(r"^## Never\n(.*?)(?=^## )", _text(), re.DOTALL | re.MULTILINE)
    assert match, "SKILL.md has no '## Never' section"
    return match.group(1)


def test_frontmatter_name_is_merge_pr() -> None:
    assert _frontmatter()["name"] == "merge-pr"


def test_description_carries_the_trigger_phrases() -> None:
    description = _frontmatter()["description"]
    for phrase in ("is green", "merge N", "merge PR N", "ready-to-merge"):
        assert phrase in description, f"description lacks {phrase!r}"


def test_body_carries_the_commands() -> None:
    text = _text()
    for needle in ("gh pr view", "gh pr checks", "doit pr_merge", "--auto-close", "Addresses #"):
        assert needle in text, f"SKILL.md lacks {needle!r}"


def test_preconditions_and_checks_come_before_the_merge() -> None:
    text = _text()
    merge = text.index("uv run doit pr_merge")
    assert text.index("gh pr view") < merge
    assert text.index("gh pr checks") < merge
    assert text.index("gh issue view") < merge


def test_the_skill_never_applies_the_label() -> None:
    text = _text()
    assert "--add-label" not in text
    assert "gh pr edit" not in text
    assert re.search(r"[Nn]ever apply the `ready-to-merge` label", _never_section())


def test_block_bypass_flags_appear_only_in_the_never_section() -> None:
    text = _text()
    never = _never_section()
    for flag in ("--admin", "--force", "--no-verify"):
        assert flag in never
        assert text.count(flag) == never.count(flag), f"{flag} used outside '## Never'"


def test_it_runs_from_the_main_checkout() -> None:
    assert "worktrees/" in _text()
    assert "main checkout" in _text()


def test_unaddressed_issues_are_left_open_with_a_comment() -> None:
    text = _text()
    assert "gh issue comment" in text
    assert "not fully addressed" in text
    assert "Never close an issue that is not fully addressed" in _never_section()


def test_slash_commands_documents_the_skill_and_its_count() -> None:
    text = SLASH_COMMANDS.read_text(encoding="utf-8")
    assert "### `/merge-pr [N]`" in text
    assert "merge N" in text
    word = NUMBER_WORDS[len(SHARED_SKILLS)]
    assert f"{word} workflow skills" in text


def test_agents_md_points_at_the_skill_section() -> None:
    text = AGENTS_MD.read_text(encoding="utf-8")
    assert "merge-pr" in text
    assert "slash-commands.md#merge-pr-n" in text

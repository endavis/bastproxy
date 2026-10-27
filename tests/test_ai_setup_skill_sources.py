"""`AI_SETUP.md` must not credit `.agents/skills/` with a command it lacks (#869).

It once said, twice, that `/ghi-status` came from `.agents/skills/`, which had
no `ghi-status` skill at the time: Copilot read `/ghi-status` from
`.claude/commands/ghi-status.md` instead. #972 moved `ghi-status` into
`.agents/skills/` along with the template's other shared workflow skills, so
the credit is now true, but the check that catches the next false one stays.
These tests hold every command the doc credits to `.agents/skills/` to a skill
there.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from agent_roster import agent_is_present

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_SETUP = REPO_ROOT / "docs" / "development" / "AI_SETUP.md"
AGENTS_SKILLS = REPO_ROOT / ".agents" / "skills"

# The two phrasings the Copilot section uses: "`.agents/skills/` — ... (provides
# `/a`, `/b`)" and "(`/a`, `/b`) come from `.agents/skills/`".
_CREDITS = (
    re.compile(r"`\.agents/skills/`[^(\n]*\(provides ([^)]*)\)"),
    re.compile(r"\(([^()]*)\) come from `\.agents/skills/`"),
)

pytestmark = pytest.mark.skipif(
    not agent_is_present("copilot"), reason="the credits are in the Copilot section"
)


def _credited_commands(text: str) -> list[str]:
    """Return the commands *text* says `.agents/skills/` provides, except globs like `/multi-*`."""
    names: list[str] = []
    for pattern in _CREDITS:
        for group in pattern.findall(text):
            names += re.findall(r"`/([a-z0-9-]+)`", group)
    return names


def test_every_credited_command_has_a_skill() -> None:
    credited = _credited_commands(AI_SETUP.read_text(encoding="utf-8"))
    missing = [name for name in credited if not (AGENTS_SKILLS / name / "SKILL.md").is_file()]
    assert missing == [], f"AI_SETUP.md credits .agents/skills/ with {missing}, which it lacks"


def test_the_scan_finds_the_credits() -> None:
    """A rewording that the patterns no longer match must fail here, not pass unchecked."""
    assert "implement-issue" in _credited_commands(AI_SETUP.read_text(encoding="utf-8"))


def test_the_scan_detects_the_line_this_fixed() -> None:
    line = (
        "- `.agents/skills/` — interoperable Codex skill path, also read by Copilot "
        "(provides `/ghi-finalize`, `/ghi-status`, `/multi-*`)"
    )
    assert _credited_commands(line) == ["ghi-finalize", "ghi-status"]

"""`AGENTS.md` carries only what every agent needs at all times.

`### AI Config Directories` was 5,847 bytes — 21% of the file — describing four
agents' config layouts to all four agents (#750). Claude parsed Codex's approval
flags and Antigravity's stdout-deny hook contract every session and could act on
neither, and every distinctive fact in the section was already stated in a doc the
section itself linked.

The section is now a pointer table. These tests are the ratchet that keeps it one:

1. Per-agent config *detail* must not reappear anywhere in `AGENTS.md`. Config
   *roots* are shared navigation and stay; the flags, filenames and hook contracts
   behind them belong to one agent and go in that agent's doc.
2. The table's rows stay one line each, so prose cannot creep back into a cell.
3. The table has one row per agent the project actually wires, so a downstream
   that drops an agent is not held to a row it deleted (#690).

A byte budget was considered and rejected (ADR-9018): a size assertion is satisfied
equally by removing agent-specific content — the goal — or by deleting a shared
always-on rule, which is the opposite, so it cannot fail for the right reason.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from agent_roster import ALL_AGENTS, agent_is_present, present_agents

REPO_ROOT = Path(__file__).resolve().parents[1]
AGENTS_MD = REPO_ROOT / "AGENTS.md"

SECTION_HEADING = "### AI Config Directories"

# Literal substrings (not patterns) that only ever appear when one agent's config
# is being described in detail. Each was present in the collapsed section and is
# now carried by that agent's own doc.
FORBIDDEN_MARKERS: tuple[str, ...] = (
    "SKILL.md",  # skill-file layout — per-agent, see AI_SETUP.md
    "hooks.json",  # Copilot/Antigravity hook wiring — see command-blocking.md
    "config.toml",  # Codex approval policy — see command-blocking.md
    "applyTo:",  # Copilot instruction-file scoping
    ".instructions.md",  # Copilot instruction-file naming
    '"decision"',  # Antigravity's stdout block contract
    "--dangerously-",  # per-CLI approval bypass flags
    "--add-dir",  # Antigravity workspace flag
    "--allow-all",  # Copilot headless flag
    "-a never",  # Codex headless flag
)

# Where the detail lives now, named in the failure message so the fix is obvious.
_DESTINATIONS = (
    "docs/development/AI_SETUP.md (per-agent config), "
    "docs/development/ai/slash-commands.md (command discovery), "
    "docs/development/ai/cross-agent-delegation.md (naming, invocation flags), "
    "docs/development/ai/command-blocking.md (hook wiring)"
)

# Each agent's row is identified by the CLI name in its first cell.
_ROW_LABELS: dict[str, str] = {
    "claude": "Claude Code",
    "copilot": "GitHub Copilot CLI",
    "codex": "Codex CLI",
    "antigravity": "Antigravity CLI",
}

# A pointer row is a config root plus a link. Anything longer is prose.
MAX_ROW_CHARS = 200


def _agents_md() -> str:
    return AGENTS_MD.read_text(encoding="utf-8")


def _config_table_rows(text: str | None = None) -> list[str]:
    """Return the body rows of the table under :data:`SECTION_HEADING`."""
    lines = (text if text is not None else _agents_md()).splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.startswith(SECTION_HEADING))
    except StopIteration:  # pragma: no cover - guarded by its own test
        return []

    rows: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("#"):
            break
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        if set(stripped) <= set("|: -"):  # the `| :--- |` separator
            continue
        if stripped.startswith("| CLI |"):  # the header
            continue
        rows.append(stripped)
    return rows


def _violations(text: str) -> list[tuple[int, str, str]]:
    """Return ``(line number, marker, line)`` for every forbidden marker found."""
    return [
        (number, marker, line.strip())
        for number, line in enumerate(text.splitlines(), start=1)
        for marker in FORBIDDEN_MARKERS
        if marker in line
    ]


def test_agents_md_carries_no_per_agent_config_detail() -> None:
    """One agent's config detail is noise in the file every agent always reads."""
    found = _violations(_agents_md())
    assert not found, (
        "AGENTS.md names per-agent config detail:\n"
        + "\n".join(f"  line {n}: {marker!r} in {line}" for n, marker, line in found)
        + f"\nMove it to the agent's own doc — {_DESTINATIONS}. "
        "AGENTS.md keeps the config root and a pointer (ADR-9018)."
    )


def test_the_config_section_exists() -> None:
    """The other tests here are vacuous if the heading is renamed away."""
    assert SECTION_HEADING in _agents_md(), (
        f"{SECTION_HEADING!r} is gone from AGENTS.md. If it moved, update this module — "
        "silently passing on a missing section is how a ratchet stops ratcheting."
    )


def test_config_table_has_a_row_per_wired_agent() -> None:
    """A project that drops an agent drops its row; the rest must stay."""
    rows = _config_table_rows()
    for agent in present_agents():
        label = _ROW_LABELS[agent]
        assert any(row.startswith(f"| {label}") for row in rows), (
            f"{label} is wired in this project but has no row in {SECTION_HEADING}."
        )


@pytest.mark.parametrize("agent", ALL_AGENTS)
def test_absent_agents_have_no_row(agent: str) -> None:
    """The converse: a row for an agent this project does not wire is stale."""
    if agent_is_present(agent):
        pytest.skip(f"{agent} is wired in this project")
    label = _ROW_LABELS[agent]
    rows = _config_table_rows()
    assert not any(row.startswith(f"| {label}") for row in rows), (
        f"{label} has a row in {SECTION_HEADING} but is not wired in this project."
    )


def test_config_table_rows_stay_one_line() -> None:
    """A cell long enough to hold prose is a cell that will."""
    for row in _config_table_rows():
        assert len(row) <= MAX_ROW_CHARS, (
            f"Row exceeds {MAX_ROW_CHARS} chars, so it is carrying detail rather than "
            f"pointing at it:\n  {row}\nPut the detail in the linked doc (ADR-9018)."
        )


def test_config_table_rows_link_to_a_doc_that_exists() -> None:
    """A pointer table is only worth the reads it resolves to (#738)."""
    for row in _config_table_rows():
        target = row.rsplit("](", 1)[-1].split(")")[0].split("#")[0]
        assert target, f"Row names no destination doc:\n  {row}"
        assert (REPO_ROOT / target).is_file(), f"Row points at a missing file {target!r}:\n  {row}"


def test_the_marker_scan_detects_a_planted_violation() -> None:
    """Guard against the scan passing because it looks at nothing."""
    planted = "Codex approval policy lives in `.codex/config.toml`.\n"
    found = _violations(planted)
    assert found, "the marker scan missed a planted per-agent config detail"
    assert found[0][1] == "config.toml"


def test_the_row_parser_finds_the_shipped_rows() -> None:
    """Guard against the row assertions passing on an empty parse."""
    rows = _config_table_rows()
    assert len(rows) == len(present_agents()), (
        f"parsed {len(rows)} config rows for {len(present_agents())} wired agents"
    )


# --- Relocated procedure must stay reachable (#751) ------------------------
#
# `### 5. Pre-Action Checks` is the index for content AGENTS.md delegates rather
# than carries. `test_instruction_pointers.py` (#739) checks that a pointer
# *resolves*; nothing checked that relocated content *has* one. A section moved
# out of the always-on file and not indexed is unreachable in practice — the
# agent has no moment at which it learns to go and read it.

PRE_ACTION_HEADING = "### 5. Pre-Action Checks (Dynamic Context)"

# Docs that AGENTS.md delegates procedure to instead of restating it. Adding a
# row here is the second half of moving something out of AGENTS.md.
RELOCATION_TARGETS = (
    "docs/development/AI_SETUP.md",  # per-agent config (#750)
    ".github/CONTRIBUTING.md",  # issue / PR / ADR commands (#751)
    "docs/development/dependabot-automerge.md",  # rebase procedure (#751)
)

_BACKTICKED_PATH = re.compile(r"`([\w./-]+\.(?:md|yml|yaml))`")


def _pre_action_rows() -> list[str]:
    """Return the body rows of the Pre-Action Checks table."""
    lines = _agents_md().splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.startswith(PRE_ACTION_HEADING))
    except StopIteration:  # pragma: no cover - guarded by its own test
        return []

    rows: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("#"):
            break
        stripped = line.strip()
        if not stripped.startswith("|") or set(stripped) <= set("|: -"):
            continue
        if stripped.startswith("| Intent"):
            continue
        rows.append(stripped)
    return rows


def _indexed_paths() -> set[str]:
    return {path for row in _pre_action_rows() for path in _BACKTICKED_PATH.findall(row)}


@pytest.mark.parametrize("target", RELOCATION_TARGETS)
def test_relocation_targets_are_indexed(target: str) -> None:
    """Content moved out of AGENTS.md must be reachable from Pre-Action Checks."""
    assert target in _indexed_paths(), (
        f"{target} carries procedure moved out of AGENTS.md but has no row in "
        f"{PRE_ACTION_HEADING}. Without one, nothing tells an agent when to read it — "
        "the content is out of the always-on file and out of reach (#751)."
    )


def test_indexed_files_exist() -> None:
    """A row naming a file that is not there is the #738 failure in a new place."""
    missing = sorted(p for p in _indexed_paths() if not (REPO_ROOT / p).is_file())
    assert not missing, f"{PRE_ACTION_HEADING} names files that do not exist: {missing}"


def test_the_pre_action_parser_finds_the_shipped_rows() -> None:
    """Guard against the two assertions above passing on an empty parse."""
    rows = _pre_action_rows()
    assert len(rows) >= len(RELOCATION_TARGETS), f"parsed only {len(rows)} Pre-Action rows"
    assert _indexed_paths(), "parsed no file paths out of the Pre-Action Checks table"

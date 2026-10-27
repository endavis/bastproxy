"""The two `perf-change` bodies must agree, and neither may report a speedup unmeasured.

`.claude/rules/verified-claims.md` exists because an agent will otherwise report a speedup it
read off the code rather than measured. This project already ships the tools to measure one --
`tests/benchmarks/`, `doit benchmark`, `doit benchmark_save`, `doit benchmark_compare`, and a CI
workflow that tracks results over time -- but shipped no procedure that drives them in the order
that keeps a claimed speedup honest (#836).

The local loop also had a trap: `doit benchmark_compare` used to be pinned to the first save
(`0001_baseline`), so a second baseline in the same scratch storage directory compared against
the oldest run instead of the one just taken. #840 (merged as `c9f664f`) made
`--benchmark-compare` use the latest saved run instead, which is what makes running the loop
as-is (rather than working around the pin) trustworthy.

Two surfaces carry it -- `.agents/skills/` for Codex, Antigravity and Copilot, `.claude/skills/`
for Claude (generated from the former by `doit skills_sync`, byte for byte) -- and whichever agent
the user drives decides which body applies. A step present in one and missing from the other is a
control that fires for some users and not others. The bodies are identical since #972; what is
asserted here is the contract and its ordering.

Scoped to the agents a project actually wires, per `tests/agent_roster.py` (#690).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from agent_roster import agent_is_present

REPO_ROOT = Path(__file__).resolve().parents[1]

CLAUDE_COMMAND = REPO_ROOT / ".claude" / "skills" / "perf-change" / "SKILL.md"
SHARED_SKILL = REPO_ROOT / ".agents" / "skills" / "perf-change" / "SKILL.md"

# The steps both bodies take, in this order. Baseline precedes Change, which precedes Compare, so
# a body cannot satisfy "baseline before the change" and "benchmark before optimizing" out of
# order without also failing this.
STEPS: tuple[str, ...] = (
    "### Step 1: Confirm a benchmark covers the change",
    "### Step 2: Baseline",
    "### Step 3: Profile",
    "### Step 4: Change",
    "### Step 5: Compare",
    "### Step 6: Validate and record",
)

# (label, substring) pairs both bodies must carry. Literal substrings rather than regexes,
# matching the convention in `test_add_dependency_skill.py`.
CONTRACT: tuple[tuple[str, str], ...] = (
    ("the benchmark directory", "`tests/benchmarks/`"),
    ("the benchmark pattern to follow", "`tests/benchmarks/test_bench_core.py`"),
    ("benchmarks disabled by default", "`--benchmark-disable`"),
    ("the mutmut exemption reasoning", "assert nothing"),
    ("the baseline command", "doit benchmark_save"),
    ("where baselines are stored", "`tmp/benchmarks/`"),
    ("compare uses the latest save", "most recently saved run"),
    ("the profiler", "cProfile"),
    ("the profile reader", "pstats"),
    ("the sort key that surfaces real code", "`tottime`"),
    ("why not cumulative", "cumulative is dominated by pytest's own call stack"),
    ("the compare command", "doit benchmark_compare"),
    ("the compare confirmation line", "Comparing against benchmarks from"),
    ("no unmeasured speedup claims", "No speedup figure without it."),
    ("no reaching for a better number", "rerun until the number looks better"),
    ("the validation command", "doit check"),
    ("the correctness gate", "a faster wrong answer is a regression"),
    ("never edit a failing test", "Never edit a test to make it pass."),
    ("comparison kept in the PR", "PR description"),
    ("noisy-run defaults pointer", "check the current `--benchmark-min-rounds`"),
    ("where the benchmark settings live", "`addopts` under `[tool.pytest.ini_options]`"),
    ("the settings issue reference", "(#879)"),
    ("CI's separate tracking", "ci-cd-testing.md"),
    ("CI gates history on pushes to main", "github.event_name == 'push'"),
    ("no CI comparison on a PR", "no benchmark comparison from CI"),
    ("the scratch dir is created before use", "mkdir -p tmp/agents/"),
    ("scratch cleanup", "delete them when"),
)

# Sentences both bodies carry word for word, so neither can be softened on one surface. The first
# closes Step 1 (the issue's "write one before optimizing it" criterion); the second closes Step
# 5 (the issue's "no speedup figure without it"); the third closes Step 6 (the issue's own framing
# of why validation is not optional).
BENCHMARK_GATE = (
    "**If `tests/benchmarks/` has no benchmark for the path being changed, write one before "
    "optimizing it.**"
)
COMPARE_GATE = "**No speedup figure without it.**"
CHECK_GATE = "**`doit check` must pass; a faster wrong answer is a regression.**"

# A fence whose contents are commands for the agent to run.
SHELL_FENCE = re.compile(r"```(?:bash|sh|shell|zsh|console)\s*$")

# A `--benchmark-compare` pinned to a specific saved run, the defect #840 fixed. The current flow
# must call it bare (comparing against the latest save), never with `=<id>`.
PINNED_COMPARE = re.compile(r"--benchmark-compare=\S")


def _normalized(text: str) -> str:
    """Collapse whitespace runs, so a sentence that wraps still matches."""
    return re.sub(r"\s+", " ", text)


def _wired_bodies() -> list[tuple[str, Path]]:
    """Return (surface, path) for each `perf-change` body this project wires."""
    bodies: list[tuple[str, Path]] = []
    if agent_is_present("claude"):
        bodies.append(("claude", CLAUDE_COMMAND))
    # Codex, Antigravity and Copilot all read `.agents/skills/`.
    if any(agent_is_present(a) for a in ("codex", "antigravity", "copilot")):
        bodies.append(("shared", SHARED_SKILL))
    return bodies


def _existing_bodies() -> list[tuple[str, str]]:
    """Return (surface, normalized text) for each wired body that exists."""
    return [
        (surface, _normalized(path.read_text(encoding="utf-8")))
        for surface, path in _wired_bodies()
        if path.is_file()
    ]


def _contract_violations(surface: str, text: str) -> list[str]:
    """Return the contract elements *text* is missing."""
    normalized = _normalized(text)
    return [
        f"{surface} is missing {label} ({needle!r})"
        for label, needle in CONTRACT
        if needle not in normalized
    ]


def _step(text: str, number: int) -> str:
    """Return step *number* of normalized *text*: its heading up to the next heading."""
    start = text.find(STEPS[number - 1])
    if start == -1:
        return ""
    end = text.find(" ## ", start + 1) if number == len(STEPS) else text.find(STEPS[number])
    return text[start : end if end != -1 else len(text)]


def _shell_lines(text: str) -> list[tuple[int, str]]:
    """Return (line_no, line) for every line inside a shell code fence."""
    lines: list[tuple[int, str]] = []
    in_fence = in_shell = False
    for line_no, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_shell = not in_fence and bool(SHELL_FENCE.match(stripped))
            in_fence = not in_fence
        elif in_shell:
            lines.append((line_no, line))
    return lines


def test_every_wired_surface_has_a_body() -> None:
    """A project that wires any agent has somewhere to invoke `perf-change`."""
    if not _wired_bodies():
        pytest.skip("no AI agent is wired in this project")

    missing = [
        f"{surface}: {path.relative_to(REPO_ROOT)}"
        for surface, path in _wired_bodies()
        if not path.is_file()
    ]
    assert not missing, f"perf-change is missing on wired surfaces: {missing}"


def test_both_bodies_carry_the_contract() -> None:
    """Every wired `perf-change` body carries every contract element."""
    missing: list[str] = []
    for surface, text in _existing_bodies():
        missing += _contract_violations(surface, text)

    assert not missing, (
        "perf-change contract violations:\n  "
        + "\n  ".join(missing)
        + "\n\nBoth bodies must carry these steps. Change them together or not at all."
    )


def test_the_contract_scanner_detects_a_violation() -> None:
    """The scanner must fail on a body that drops a step, not merely pass on ours."""
    assert _contract_violations("synthetic", "a body that says none of the required things")


def test_the_steps_run_in_the_same_order_on_every_surface() -> None:
    """Confirm the benchmark, baseline, profile, change, compare, then validate -- in that order.

    Comparing before changing would compare the baseline against itself. Validating before
    comparing would let a broken change's number stand unexamined until after it was already
    reported.
    """
    out_of_order = []
    for surface, text in _existing_bodies():
        positions = [text.find(step) for step in STEPS]
        if -1 in positions or positions != sorted(positions):
            out_of_order.append(f"{surface}: {dict(zip(STEPS, positions, strict=True))}")

    assert not out_of_order, "perf-change steps missing or out of order:\n  " + "\n  ".join(
        out_of_order
    )


def test_the_gate_sentences_are_worded_identically_and_in_place() -> None:
    """The benchmark gate closes Step 1; the compare gate closes Step 5; the check gate Step 6.

    A gate paraphrased per host drifts into a weaker version on one of them, and a gate that
    lands in the wrong step stops closing the step it is meant to guard.
    """
    misplaced = []
    for surface, text in _existing_bodies():
        if BENCHMARK_GATE not in _step(text, 1):
            misplaced.append(f"{surface}: the benchmark gate is not in Step 1")
        if COMPARE_GATE not in _step(text, 5):
            misplaced.append(f"{surface}: the compare gate is not in Step 5")
        if CHECK_GATE not in _step(text, 6):
            misplaced.append(f"{surface}: the check gate is not in Step 6")

    assert not misplaced, (
        "\n  ".join(["gate sentences missing, reworded or moved:", *misplaced])
        + "\nReword every surface together or none."
    )


def test_no_body_pins_the_comparison_to_a_specific_saved_run() -> None:
    """`--benchmark-compare` must run bare (latest save), never `=<id>` (the #838/#840 defect).

    `doit benchmark_compare` itself was fixed to drop the pin; a skill that tells an agent to
    pass a specific run id would reintroduce the exact trap the issue describes, one layer up.
    """
    offenders = []
    for surface, path in _wired_bodies():
        if not path.is_file():
            continue
        for line_no, line in _shell_lines(path.read_text(encoding="utf-8")):
            if PINNED_COMPARE.search(line):
                offenders.append(f"{surface}:{line_no}: {line.strip()}")

    assert not offenders, "perf-change pins the comparison to one saved run:\n  " + "\n  ".join(
        offenders
    )


def test_the_pin_scanner_detects_a_violation() -> None:
    """The scanner must catch a pinned comparison in a command block, and only there."""
    body = (
        "```bash\n--benchmark-compare --benchmark-storage=tmp/benchmarks\n```\n"
        "1. Then:\n   ```bash\n   --benchmark-compare=0001_baseline\n   ```\n"
    )
    offenders = [line for _, line in _shell_lines(body) if PINNED_COMPARE.search(line)]

    assert [line.strip() for line in offenders] == ["--benchmark-compare=0001_baseline"]


def test_shared_skill_declares_the_frontmatter_agents_activate_on() -> None:
    """Antigravity activates a skill by matching its `description:`; without one it never fires."""
    if not SHARED_SKILL.is_file():
        pytest.skip("the shared perf-change skill is not wired in this project")

    text = SHARED_SKILL.read_text(encoding="utf-8")
    assert text.startswith("---\n"), "SKILL.md must open with YAML frontmatter"
    frontmatter = text.split("---", 2)[1]
    assert "name: perf-change" in frontmatter
    assert "description:" in frontmatter
    # The description is the whole activation surface: it must name what an agent would be doing
    # when it needs this, not just the skill's title.
    for phrase in ("performance", "benchmark", "cprofile"):
        assert phrase in frontmatter.lower(), f"description never mentions {phrase!r}"

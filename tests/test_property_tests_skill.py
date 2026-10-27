"""The two `property-tests` bodies must agree on when and how to write one.

Hypothesis is already installed and configured -- the `ci` and `default` profiles in
`tests/conftest.py`, and the `property` marker in `pyproject.toml` -- but nothing guided
the judgment call that makes a property test worth having: which property, built from
what strategy, proven able to fail, with its counterexample pinned (#831). A property
that only checks a call does not raise, or that restates the implementation under a
different name, passes forever and finds nothing.

Two surfaces carry it -- `.agents/skills/` for Codex, Antigravity and Copilot,
`.claude/skills/` for Claude (generated from the former by `doit skills_sync`,
byte for byte) -- and whichever agent the user drives decides which body
applies. A step present in one and missing from the other is a control that
fires for some users and not others. The bodies are identical since #972;
what is asserted here is the contract and its ordering.

Scoped to the agents a project actually wires, per `tests/agent_roster.py`
(#690).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from agent_roster import agent_is_present

REPO_ROOT = Path(__file__).resolve().parents[1]

CLAUDE_COMMAND = REPO_ROOT / ".claude" / "skills" / "property-tests" / "SKILL.md"
SHARED_SKILL = REPO_ROOT / ".agents" / "skills" / "property-tests" / "SKILL.md"

# The steps both bodies take, in this order.
STEPS: tuple[str, ...] = (
    "### Step 1: Pick the property",
    "### Step 2: Build the strategy",
    "### Step 3: Write the test",
    "### Step 4: Prove it can fail",
    "### Step 5: Pin the counterexample",
    "### Step 6: Validate",
)

# (label, substring) pairs both bodies must carry. Literal substrings rather
# than regexes, matching the convention in `test_add_dependency_skill.py`.
CONTRACT: tuple[tuple[str, str], ...] = (
    ("round-trip kind", "`decode(encode(x)) == x`"),
    ("idempotence kind", "`f(f(x)) == f(x)`"),
    ("invariant kind", "a relationship every output must satisfy"),
    ("oracle kind", "a simpler reference implementation"),
    ("build from types first", "`st.builds`"),
    ("from_type strategy", "`st.from_type`"),
    ("composite strategy", "`@st.composite`"),
    ("assume discards examples", "`assume()`"),
    ("filter discards examples", "`.filter()`"),
    ("the health check this trips", "`HealthCheck.filter_too_much`"),
    ("the marker", "`@pytest.mark.property`"),
    ("deference to the profiles", "the `ci` and `default` profiles in `tests/conftest.py`"),
    ("no per-test override", "Do not add a per-test `@settings(...)`"),
    ("why the deadline is off", "#736"),
    ("mutation.yml also loads the ci profile", "`mutation.yml` both set `HYPOTHESIS_PROFILE=ci`"),
    ("the mutmut selection key", "`pytest_add_cli_args_test_selection`"),
    ("the mutmut selection test", "test_every_test_of_the_package_is_selected"),
    ("what hypothesis reports", "`Failing test case:`"),
    (
        "check the installed version, don't assume",
        "read what the installed version actually prints",
    ),
    ("undo just the deliberate edit", "Reverse the specific edit that broke the code"),
    ("verify nothing else was lost", "confirm only the intended work remains"),
    ("checkout only if the file was already clean", "only when the file had no other uncommitted"),
    ("checkout fallback", "`git checkout -- <file>`"),
    ("fix the bug before pinning it", "Fix the code first."),
    ("self is not a pin argument", "skip `self`"),
    ("pin syntax", "`@example(...)`"),
    ("the database location", "`.hypothesis/examples/`"),
    ("the database is per machine", "only on the machine and checkout that found it"),
    ("scoped validation", "uv run pytest -m property"),
    ("full validation", "doit check"),
    ("never edit a failing test", "Never edit a test to make it pass."),
)

# Sentences both bodies carry word for word, so neither can be softened on one
# surface. The first is the stop condition that closes Step 1; the second is
# the gate that closes Step 4, requiring proof the test can fail -- and that
# only the deliberate break gets undone, not the task's other work.
STOP_SENTENCE = "**If none of these fit, stop: an example-based test is the better tool.**"
PROVE_SENTENCE = (
    "**Confirm the property fails, read what Hypothesis reports, then undo the deliberate "
    "break, not the file's other changes.**"
)


def _normalized(text: str) -> str:
    """Collapse whitespace runs, so a sentence that wraps still matches."""
    return re.sub(r"\s+", " ", text)


def _wired_bodies() -> list[tuple[str, Path]]:
    """Return (surface, path) for each `property-tests` body this project wires."""
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
        f"{surface} is missing the {label} ({needle!r})"
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


def test_every_wired_surface_has_a_body() -> None:
    """A project that wires any agent has somewhere to invoke `property-tests`."""
    if not _wired_bodies():
        pytest.skip("no AI agent is wired in this project")

    missing = [
        f"{surface}: {path.relative_to(REPO_ROOT)}"
        for surface, path in _wired_bodies()
        if not path.is_file()
    ]
    assert not missing, f"property-tests is missing on wired surfaces: {missing}"


def test_both_bodies_carry_the_contract() -> None:
    """Every wired `property-tests` body carries every contract element."""
    missing: list[str] = []
    for surface, text in _existing_bodies():
        missing += _contract_violations(surface, text)

    assert not missing, (
        "property-tests contract violations:\n  "
        + "\n  ".join(missing)
        + "\n\nBoth bodies must carry these steps. Change them together or not at all."
    )


def test_the_contract_scanner_detects_a_violation() -> None:
    """The scanner must fail on a body that drops a step, not merely pass on ours."""
    assert _contract_violations("synthetic", "a body that says none of the required things")


def test_the_steps_run_in_the_same_order_on_every_surface() -> None:
    """Pick, build, write, prove, pin, validate -- on every surface, in that order.

    Pinning before proving the test can fail would pin a value nobody watched
    catch anything. Validating before restoring the deliberately broken code
    would let the check run pass by accident.
    """
    out_of_order = []
    for surface, text in _existing_bodies():
        positions = [text.find(step) for step in STEPS]
        if -1 in positions or positions != sorted(positions):
            out_of_order.append(f"{surface}: {dict(zip(STEPS, positions, strict=True))}")

    assert not out_of_order, "property-tests steps missing or out of order:\n  " + "\n  ".join(
        out_of_order
    )


def test_the_gate_sentences_are_worded_identically_and_in_place() -> None:
    """The stop condition closes Step 1; the prove-it-can-fail gate closes Step 4.

    A gate paraphrased per host drifts into a weaker version on one of them, and
    a stop condition or fail-proof gate that has drifted out of its step no
    longer guards the step it was written for.
    """
    misplaced = []
    for surface, text in _existing_bodies():
        if STOP_SENTENCE not in _step(text, 1):
            misplaced.append(f"{surface}: the stop sentence is not in Step 1")
        if PROVE_SENTENCE not in _step(text, 4):
            misplaced.append(f"{surface}: the prove-it-can-fail sentence is not in Step 4")

    assert not misplaced, (
        "\n  ".join(["gate sentences missing, reworded or moved:", *misplaced])
        + "\nReword every surface together or none."
    )


def test_the_real_bug_is_fixed_before_it_is_pinned() -> None:
    """Step 5 pins a real counterexample only after the code itself is fixed.

    Pinning first would commit `@example(...)` for an input the code still
    fails on, encoding the bug as expected behavior instead of catching it.
    Step 4's drill is against code broken on purpose and never gets pinned;
    only a genuine failure against the real code does, and only once fixed.
    """
    out_of_order = []
    for surface, text in _existing_bodies():
        step5 = _step(text, 5)
        fix = step5.find("Fix the code first.")
        pin = step5.find("@example(...)")
        if fix == -1 or pin == -1 or fix > pin:
            out_of_order.append(surface)

    assert not out_of_order, f"these bodies pin before fixing the real bug: {out_of_order}"


def test_no_body_shows_a_per_test_settings_override() -> None:
    """`@settings(max_examples=...)` or `@settings(deadline=...)` fights Step 3's profiles.

    Showing either as an example would teach the opposite of what Step 3 requires:
    CI's `ci` profile already picks these values, and a per-test override fights
    it instead of relying on it.
    """
    offenders = [
        surface
        for surface, text in _existing_bodies()
        if "@settings(max_examples" in text or "@settings(deadline" in text
    ]

    assert not offenders, (
        f"property-tests shows a per-test @settings override that fights the profiles: {offenders}"
    )


def test_the_mutmut_selection_pointer_is_one_the_pointer_checks_can_see() -> None:
    """The file and the quoted heading share a line, so `test_instruction_pointers` checks it.

    The quoted-heading check pairs a heading with a filename on the same line. A
    rewrap that splits them leaves the pointer in place and unchecked.
    """
    unseen = []
    for surface, path in _wired_bodies():
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        if not any("ci-cd-testing.md" in ln and '"### Which Tests Run"' in ln for ln in lines):
            unseen.append(surface)

    assert not unseen, f"no line pairs the file with its section in: {unseen}"


def test_shared_skill_declares_the_frontmatter_agents_activate_on() -> None:
    """Antigravity activates a skill by matching its `description:`; without one it never fires."""
    if not SHARED_SKILL.is_file():
        pytest.skip("the shared property-tests skill is not wired in this project")

    text = SHARED_SKILL.read_text(encoding="utf-8")
    assert text.startswith("---\n"), "SKILL.md must open with YAML frontmatter"
    frontmatter = text.split("---", 2)[1]
    assert "name: property-tests" in frontmatter
    assert "description:" in frontmatter
    # The description is the whole activation surface: it must name what an agent
    # would be doing when it needs this, not just the skill's title.
    for phrase in ("hypothesis", "property", "given"):
        assert phrase in frontmatter.lower(), f"description never mentions {phrase!r}"

"""The two `python-version-bump` bodies must agree, and both must gate the floor raise (#833).

The supported Python range is declared in seven places (`tests/test_python_versions_agree.py`
is the check that they agree). Bumping the newest version is safe to automate; raising the floor
drops users on the old version, which only the user may decide. A skill that changes the seven
settings without asking, or that a user drives on one host but not another, makes that call for
them silently on whichever surface skipped the gate.

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

CLAUDE_COMMAND = REPO_ROOT / ".claude" / "skills" / "python-version-bump" / "SKILL.md"
SHARED_SKILL = REPO_ROOT / ".agents" / "skills" / "python-version-bump" / "SKILL.md"

# The steps both bodies take, in this order. Steps 2 and 3-6 are alternatives (add a newest
# version vs. raise the floor), but both bodies must document them in the same order regardless.
STEPS: tuple[str, ...] = (
    "### Step 1: Read the seven settings",
    "### Step 2: Add a newest version",
    "### Step 3: Raise the floor — ask first",
    "### Step 4: Change all seven settings in one commit",
    "### Step 5: Sync derived state",
    "### Step 6: Validate and commit",
)

# (label, substring) pairs both bodies must carry. Literal substrings rather than regexes,
# matching the convention in `test_add_dependency_skill.py`.
CONTRACT: tuple[tuple[str, str], ...] = (
    ("the policy source", "`docs/development/ci-cd-testing.md`"),
    ("the policy section", '"## Python Version Support Policy"'),
    ("requires-python setting", "`requires-python`"),
    ("ruff target-version setting", "`target-version`"),
    ("mypy setting", "`python_version`"),
    ("pyright setting", "`pythonVersion`"),
    ("python-version file setting", "`.python-version`"),
    ("versions json setting", "`.github/python-versions.json`"),
    ("classifier format", "Programming Language :: Python :: 3.X"),
    ("ci action source", "`.github/actions/python-versions/action.yml`"),
    ("ci workflow consumer", "`.github/workflows/ci.yml`"),
    ("no workflow changes needed", "no workflow file changes"),
    ("the version-agreement test", "`tests/test_python_versions_agree.py`"),
    ("full-matrix label", "`full-matrix`"),
    ("breaking change policy", "AGENTS.md's Breaking Changes Policy"),
    ("breaking change is not a foregone conclusion", "not a foregone conclusion"),
    ("breaking change footer", "`BREAKING CHANGE:`"),
    (
        "bump semantics depend on major_version_zero (#881)",
        "MAJOR only once that setting is false (#881)",
    ),
    ("changelog is generated, not hand-edited", "`doit release` generates it from commit history"),
    ("last-compatible tag example", "`v1.2.3-py310-final`"),
    ("tag names an existing release", "not one this commit creates"),
    ("lock regeneration", "`uv lock`"),
    # Changing `.python-version` makes the next `uv run` rebuild `.venv` without the extras, so
    # `doit` itself is gone until this runs (a pre-commit hook failed on it in #833's worktree).
    ("dev environment rebuilt after the interpreter changes", "Run `uv sync --all-extras --dev`."),
    ("lock hook name", "Validate uv.lock matches pyproject.toml"),
    ("lint reports, format fixes", "`doit lint` only"),
    ("dead branch removal", "`sys.version_info`"),
    (
        "prose-consistency grep command",
        "git grep -n -F -e '3.<n>' -e 'py3<n>' -- ':!uv.lock' ':!CHANGELOG.md'",
    ),
    ("prose sort: update bucket", "A statement of this project's supported floor or range."),
    ("prose sort: leave bucket", "sample output and test data"),
    ("no lock needed for a newest bump", "leaves `uv lock --check` at exit 0"),
    ("full validation", "`doit check`"),
)

# Sentences both bodies carry word for word, so neither can be softened on one surface. The first
# gates Step 3; the second gates Step 4 -- the issue's two "ask first" / "one commit" criteria.
ASK_SENTENCE = (
    "**Ask before changing a single file.** Raising the floor drops users still on the old "
    "version — that decision belongs to the user, not to you. Wait for an explicit yes before "
    "Step 4."
)
COMMIT_SENTENCE = (
    "**Change all seven settings in one commit.** A partial bump is worse than no bump: it "
    "leaves the tools checking against different Pythons until someone notices."
)


def _normalized(text: str) -> str:
    """Collapse whitespace runs, so a sentence that wraps still matches."""
    return re.sub(r"\s+", " ", text)


def _wired_bodies() -> list[tuple[str, Path]]:
    """Return (surface, path) for each `python-version-bump` body this project wires."""
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
    """A project that wires any agent has somewhere to invoke `python-version-bump`."""
    if not _wired_bodies():
        pytest.skip("no AI agent is wired in this project")

    missing = [
        f"{surface}: {path.relative_to(REPO_ROOT)}"
        for surface, path in _wired_bodies()
        if not path.is_file()
    ]
    assert not missing, f"python-version-bump is missing on wired surfaces: {missing}"


def test_both_bodies_carry_the_contract() -> None:
    """Every wired `python-version-bump` body carries every contract element."""
    missing: list[str] = []
    for surface, text in _existing_bodies():
        missing += _contract_violations(surface, text)

    assert not missing, (
        "python-version-bump contract violations:\n  "
        + "\n  ".join(missing)
        + "\n\nBoth bodies must carry these steps. Change them together or not at all."
    )


def test_the_contract_scanner_detects_a_violation() -> None:
    """The scanner must fail on a body that drops a step, not merely pass on ours."""
    assert _contract_violations("synthetic", "a body that says none of the required things")


def test_the_steps_run_in_the_same_order_on_every_surface() -> None:
    """Read, add-or-raise, gate, change, sync, validate -- on every surface, in that order.

    A body that documents the gate (Step 3) after the change (Step 4) has already told the
    reader how to raise the floor before telling them to ask permission.
    """
    out_of_order = []
    for surface, text in _existing_bodies():
        positions = [text.find(step) for step in STEPS]
        if -1 in positions or positions != sorted(positions):
            out_of_order.append(f"{surface}: {dict(zip(STEPS, positions, strict=True))}")

    assert not out_of_order, "python-version-bump steps missing or out of order:\n  " + "\n  ".join(
        out_of_order
    )


def test_the_gate_sentences_are_worded_identically_and_in_place() -> None:
    """The ask-first gate closes Step 3; the one-commit gate closes Step 4.

    A gate paraphrased per host drifts into a weaker version on one of them. The issue's two
    success criteria -- "ask first" and "one commit" -- are exactly these two sentences.
    """
    misplaced = []
    for surface, text in _existing_bodies():
        if ASK_SENTENCE not in _step(text, 3):
            misplaced.append(f"{surface}: the ask-first sentence is not in Step 3")
        if COMMIT_SENTENCE not in _step(text, 4):
            misplaced.append(f"{surface}: the one-commit sentence is not in Step 4")

    assert not misplaced, (
        "\n  ".join(["gate sentences missing, reworded or moved:", *misplaced])
        + "\nReword every surface together or none."
    )


def test_the_gate_sentence_checker_detects_a_violation() -> None:
    """The gate check must fail when a sentence is absent, not merely pass on our own bodies."""
    text = _normalized("### Step 3: Raise the floor — ask first\n\nNothing here.\n\n### Step 4: x")

    assert ASK_SENTENCE not in _step(text, 3)


def test_uv_lock_and_doit_lint_are_synced_before_the_final_validation() -> None:
    """Step 5 (sync derived state) must precede Step 6 (validate and commit) on every surface.

    Running `doit check` before `uv lock` leaves a lockfile the pre-commit hook rejects; the
    steps must stay in this order, which `test_the_steps_run_in_the_same_order_on_every_surface`
    already enforces structurally. This adds the semantic check: the sync actions themselves
    appear inside Step 5, not folded into Step 6.
    """
    out_of_order = []
    for surface, text in _existing_bodies():
        sync_step = _step(text, 5)
        if "uv lock" not in sync_step or "doit lint" not in sync_step:
            out_of_order.append(surface)

    assert not out_of_order, f"these bodies do not sync derived state in Step 5: {out_of_order}"


def test_the_prose_grep_is_defined_once_and_reused_by_steps_2_and_5() -> None:
    """The `git grep` form lives in Step 1; Steps 2 and 5 reference it rather than repeat it.

    Two independent copies of a shell command drift the way the old per-step versions did
    (#833 review): one searched only `*.md` files and missed `.devcontainer/devcontainer.json`,
    `.github/CONTRIBUTING.md` and `tools/pyproject_template/setup_repo.py`, and Step 2 had no
    equivalent at all. A single definition, referenced by name, cannot drift between the steps
    that use it.
    """
    missing = []
    for surface, text in _existing_bodies():
        step1 = _step(text, 1)
        if "git grep -n -F" not in step1:
            missing.append(f"{surface}: Step 1 does not define the prose grep")
        if "Step 1 grep" not in _step(text, 2):
            missing.append(f"{surface}: Step 2 does not reference the Step 1 grep")
        if "Step 1 grep" not in _step(text, 5):
            missing.append(f"{surface}: Step 5 does not reference the Step 1 grep")

    assert not missing, "\n  ".join(["prose-grep reuse is broken:", *missing])


def test_the_policy_pointer_is_one_the_pointer_checks_can_see() -> None:
    """The file and the quoted section share a line, so `test_instruction_pointers` checks it.

    The quoted-heading check pairs a heading with a filename on the same line. A rewrap that
    splits them leaves the pointer in place and unchecked.
    """
    unseen = []
    for surface, path in _wired_bodies():
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        if not any(
            "docs/development/ci-cd-testing.md" in ln and '"## Python Version Support Policy"' in ln
            for ln in lines
        ):
            unseen.append(surface)

    assert not unseen, f"no line pairs the file with its section in: {unseen}"


def test_shared_skill_declares_the_frontmatter_agents_activate_on() -> None:
    """Antigravity activates a skill by matching its `description:`; without one it never fires."""
    if not SHARED_SKILL.is_file():
        pytest.skip("the shared python-version-bump skill is not wired in this project")

    text = SHARED_SKILL.read_text(encoding="utf-8")
    assert text.startswith("---\n"), "SKILL.md must open with YAML frontmatter"
    frontmatter = text.split("---", 2)[1]
    assert "name: python-version-bump" in frontmatter
    assert "description:" in frontmatter
    # The description is the whole activation surface: it must name what an agent would be
    # doing when it needs this, not just the skill's title.
    for phrase in ("python version", "requires-python", "floor"):
        assert phrase in frontmatter.lower(), f"description never mentions {phrase!r}"

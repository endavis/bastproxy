"""The two `security-triage` bodies must agree, and neither may silence a finding for free.

`doit check` runs both scanners unconditionally (`task_check` in `tools/doit/quality.py`), so a
bandit or pip-audit finding blocks an agent mid-task. The shortest way past one is a suppression:
bandit takes a bare `# nosec` that silences every test on the line, or a `[tool.bandit] skips` entry
that disables a test repository-wide; pip-audit findings have no sanctioned way through `doit audit`
at all. Without a skill, the fastest path for an agent under pressure to get to green is exactly the
one that checks nothing (#834).

Two surfaces carry it -- `.agents/skills/` for Codex, Antigravity and Copilot, `.claude/skills/`
for Claude (generated from the former by `doit skills_sync`, byte for byte) -- and whichever agent
the user drives decides which body applies. A step present in one and missing from the other is a
control that fires for some users and not others. The bodies are identical since #972; what is
asserted here is the contract and its ordering.

Scoped to the agents a project actually wires, per `tests/agent_roster.py` (#690).
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest
from agent_roster import agent_is_present

REPO_ROOT = Path(__file__).resolve().parents[1]

CLAUDE_COMMAND = REPO_ROOT / ".claude" / "skills" / "security-triage" / "SKILL.md"
SHARED_SKILL = REPO_ROOT / ".agents" / "skills" / "security-triage" / "SKILL.md"

# The steps both bodies take, in this order.
STEPS: tuple[str, ...] = (
    "### Step 1: Run both scanners",
    "### Step 2: Triage a bandit finding",
    "### Step 3: Triage a pip-audit finding",
    "### Step 4: Validate",
    "### Step 5: Record",
)

# (label, substring) pairs both bodies must carry. Literal substrings rather than regexes,
# matching the convention in `test_add_dependency_skill.py`.
CONTRACT: tuple[tuple[str, str], ...] = (
    ("the bandit task", "`doit security`"),
    ("the pip-audit task", "`doit audit`"),
    ("doit check runs both", "`doit check`"),
    ("the security-extra trap", "a pass that checked nothing"),
    ("the install fix", "`doit install_dev`"),
    ("never extra-security alone", "never `uv sync --extra security` alone"),
    ("the tmp exclusion trap", "`[tool.bandit] exclude_dirs` in `pyproject.toml` excludes `tmp`"),
    ("bandit fix: subprocess", "`shell=True`"),
    ("bandit fix: yaml", "`yaml.safe_load`"),
    ("bandit justify pattern", "`# nosec <ID> # <reason>`"),
    ("per-ID precision", "`# nosec B602` clears only"),
    ("bandit config pointer", "`[tool.bandit] skips` in `pyproject.toml`"),
    ("pip-audit locate: reverse-deps", "`uv tree --invert --package <package>`"),
    (
        "pip-audit direct: runtime table",
        '`uv add "<package>>=<fixed version>"` for `[project] dependencies`',
    ),
    ("pip-audit direct: dev table", "`uv add --optional dev"),
    ("pip-audit direct: security table", "`uv add --optional security"),
    ("pip-audit direct: wrong-table risk", "lands the package in the wrong table"),
    ("pip-audit transitive fix", "`uv lock --upgrade-package <package>`"),
    ("pip-audit transitive: hook scope", "the hook does not block `uv lock`"),
    ("pip-audit transitive confirm", "`git diff uv.lock`"),
    ("pip-audit never-promote", "Never add the transitive package as a new direct dependency"),
    ("pip-audit reachability", "**assess reachability**"),
    ("pip-audit ignore flag", "`--ignore-vuln`"),
    ("pip-audit task pointer", "`tools/doit/security.py`"),
    ("never edit a failing test", "Never edit a test to make it pass"),
    ("justification kept in the PR", "PR description"),
    ("record the upgrade route", "whether Step 3 upgraded a direct or a transitive package"),
    ("the hook blocks uv add", "the dangerous-command hook blocks `uv add` for every agent"),
)

# Sentences both bodies carry word for word, so neither can be softened on one surface. The first
# two close Step 2 (bandit); the third closes Step 3 (pip-audit). Each is checked both for exact
# wording and for appearing inside the step it gates, not merely somewhere in the document.
BARE_NOSEC_SENTENCE = (
    "**Never a bare `# nosec`.** It silences every finding on the line, not only the "
    "one you meant to justify."
)
SKIPS_GATE_SENTENCE = "**Stop and ask before adding a new `skips` entry.**"
IGNORE_VULN_GATE_SENTENCE = "**Stop and ask before ignoring a pip-audit advisory.**"

# Tokens that must never appear inside a fence the agent would run as a command: both represent an
# action Step 2/3 require asking the user about first, never one the agent takes unprompted.
FORBIDDEN_COMMAND_TOKENS: tuple[str, ...] = ("uv add", "--ignore-vuln")

# A fence whose contents are commands for the agent to run. `text` fences and inline backticks in
# prose hold examples and messages for the user, which is where `uv add` and `--ignore-vuln` belong.
SHELL_FENCE = re.compile(r"```(?:bash|sh|shell|zsh|console)\s*$")


def _normalized(text: str) -> str:
    """Collapse whitespace runs, so a sentence that wraps still matches."""
    return re.sub(r"\s+", " ", text)


def _wired_bodies() -> list[tuple[str, Path]]:
    """Return (surface, path) for each `security-triage` body this project wires."""
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
    """A project that wires any agent has somewhere to invoke `security-triage`."""
    if not _wired_bodies():
        pytest.skip("no AI agent is wired in this project")

    missing = [
        f"{surface}: {path.relative_to(REPO_ROOT)}"
        for surface, path in _wired_bodies()
        if not path.is_file()
    ]
    assert not missing, f"security-triage is missing on wired surfaces: {missing}"


def test_both_bodies_carry_the_contract() -> None:
    """Every wired `security-triage` body carries every contract element."""
    missing: list[str] = []
    for surface, text in _existing_bodies():
        missing += _contract_violations(surface, text)

    assert not missing, (
        "security-triage contract violations:\n  "
        + "\n  ".join(missing)
        + "\n\nBoth bodies must carry these steps. Change them together or not at all."
    )


def test_the_contract_scanner_detects_a_violation() -> None:
    """The scanner must fail on a body that drops a step, not merely pass on ours."""
    assert _contract_violations("synthetic", "a body that says none of the required things")


def test_the_steps_run_in_the_same_order_on_every_surface() -> None:
    """Run, triage bandit, triage pip-audit, validate, record -- in that order, on every surface.

    Validating before triage means `doit check` is judged against findings nobody has looked at yet.
    Recording after hand-off means the justification never makes it into the PR.
    """
    out_of_order = []
    for surface, text in _existing_bodies():
        positions = [text.find(step) for step in STEPS]
        if -1 in positions or positions != sorted(positions):
            out_of_order.append(f"{surface}: {dict(zip(STEPS, positions, strict=True))}")

    assert not out_of_order, "security-triage steps missing or out of order:\n  " + "\n  ".join(
        out_of_order
    )


def test_the_gate_sentences_are_worded_identically_and_in_place() -> None:
    """The bare-nosec and skips gates close Step 2; the ignore-vuln gate closes Step 3.

    A gate paraphrased per host drifts into a weaker version on one of them, and the issue's own
    Success Criteria name both stop-and-ask points explicitly (#834).
    """
    misplaced = []
    for surface, text in _existing_bodies():
        step_2 = _step(text, 2)
        step_3 = _step(text, 3)
        if BARE_NOSEC_SENTENCE not in step_2:
            misplaced.append(f"{surface}: the bare-nosec sentence is not in Step 2")
        if SKIPS_GATE_SENTENCE not in step_2:
            misplaced.append(f"{surface}: the skips gate is not in Step 2")
        if IGNORE_VULN_GATE_SENTENCE not in step_3:
            misplaced.append(f"{surface}: the ignore-vuln gate is not in Step 3")

    assert not misplaced, (
        "\n  ".join(["gate sentences missing, reworded or moved:", *misplaced])
        + "\nReword every surface together or none."
    )


def test_the_policy_pointer_is_one_the_pointer_checks_can_see() -> None:
    """The file and the quoted section share a line, so `test_instruction_pointers` checks it.

    The quoted-heading check pairs a heading with a filename on the same line. A rewrap that splits
    them leaves the pointer in place and unchecked (#828).
    """
    unseen = []
    for surface, path in _wired_bodies():
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        if not any(".github/CONTRIBUTING.md" in ln and '"### Checks"' in ln for ln in lines):
            unseen.append(surface)

    assert not unseen, f"no line pairs the file with its section in: {unseen}"


def test_no_body_tells_the_agent_to_run_a_blocked_command() -> None:
    """`uv add` and `--ignore-vuln` are the user's call; neither appears in a runnable fence.

    The dangerous-command hook blocks `uv add` anyway, but a skill that puts either in a command
    block teaches the agent that asking first is an obstacle rather than the point.
    """
    offenders = []
    for surface, path in _wired_bodies():
        if not path.is_file():
            continue
        for line_no, line in _shell_lines(path.read_text(encoding="utf-8")):
            for token in FORBIDDEN_COMMAND_TOKENS:
                if token in line:
                    offenders.append(f"{surface}:{line_no}: {line.strip()}")

    assert not offenders, (
        "security-triage tells the agent to run a blocked command:\n  " + "\n  ".join(offenders)
    )


def test_the_shell_fence_scanner_detects_a_violation() -> None:
    """The fence scanner must catch a forbidden token in a command block, and only there."""
    body = (
        "```text\nuv add httpx\n```\n"
        "1. Then:\n   ```bash\n   uv add requests\n   ```\n"
        "```\nuv add attrs\n```\n"
    )
    shell = [line.strip() for _, line in _shell_lines(body)]

    assert shell == ["uv add requests"]


def test_shared_skill_declares_the_frontmatter_agents_activate_on() -> None:
    """Antigravity activates a skill by matching its `description:`; without one it never fires."""
    if not SHARED_SKILL.is_file():
        pytest.skip("the shared security-triage skill is not wired in this project")

    text = SHARED_SKILL.read_text(encoding="utf-8")
    assert text.startswith("---\n"), "SKILL.md must open with YAML frontmatter"
    frontmatter = text.split("---", 2)[1]
    assert "name: security-triage" in frontmatter
    assert "description:" in frontmatter
    # The description is the whole activation surface: it must name what an agent would be doing
    # when it needs this, not just the skill's title.
    for phrase in ("bandit", "pip-audit", "nosec"):
        assert phrase in frontmatter.lower(), f"description never mentions {phrase!r}"


# Bandit reads everything between `nosec` and the next `#` as a list of test IDs, so a reason
# written inside that list prints a `Test in comment` warning per word (#1079).
_NOSEC_COMMENT = re.compile(r"#\s*nosec\b([^#\n]*)")
_NOSEC_ID_LIST = re.compile(r"(?:\s+B\d+)*\s*")


def _noisy_nosec(line: str) -> bool:
    """True when a `# nosec` comment carries anything but test IDs before its closing `#`."""
    match = _NOSEC_COMMENT.search(line)
    return match is not None and _NOSEC_ID_LIST.fullmatch(match.group(1)) is None


def test_the_noisy_nosec_scanner_detects_a_violation() -> None:
    noisy = "import os  # nosec B404 - " + "reason words"
    quiet = "import os  # nosec B404  # " + "reason words"
    assert _noisy_nosec(noisy)
    assert not _noisy_nosec(quiet)
    assert not _noisy_nosec("import os  # nosec B404 B603")
    assert not _noisy_nosec("x = 1  # no suppression here")


def test_no_nosec_comment_puts_its_reason_inside_the_id_list() -> None:
    """Write `# nosec <ID>  # <reason>`; a reason before the second `#` is read as test IDs."""
    this_file = Path(__file__).resolve()
    offenders: list[str] = []
    roots = [REPO_ROOT / name for name in ("src", "tools", "tests", "examples")]
    paths = [REPO_ROOT / "bootstrap.py"]
    for root in roots:
        if root.is_dir():
            paths.extend(root.rglob("*.py"))
    for path in paths:
        if not path.is_file() or path.resolve() == this_file:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if _noisy_nosec(line):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{number}")
    assert not offenders, (
        "put the reason after a second `#`, not inside the nosec ID list: " + ", ".join(offenders)
    )


# A `# nosec` on a line where bandit finds nothing prints `nosec encountered ... but no failed
# test` on every run and hides which suppressions still matter (#1084). Bandit has no setting that
# makes it fatal, so scan its output.
_STALE_NOSEC = "nosec encountered"
requires_bandit = pytest.mark.skipif(
    importlib.util.find_spec("bandit") is None,
    reason="bandit is in the `security` extra and is not installed",
)


def _bandit_stale_nosec(*targets: Path, config: bool = True) -> list[str]:
    """Run bandit over `targets` and return the stale-`nosec` warnings it printed.

    `config=False` skips `pyproject.toml`, whose `exclude_dirs` lists `tmp` and so skips the
    pytest temp directory the detector test writes to.
    """
    args = ["-c", "pyproject.toml"] if config else []
    result = subprocess.run(  # nosec B603  # fixed argv, no shell
        [sys.executable, "-m", "bandit", *args, "-r", *map(str, targets)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return [line for line in (result.stdout + result.stderr).splitlines() if _STALE_NOSEC in line]


@requires_bandit
def test_the_stale_nosec_guard_detects_a_violation(tmp_path: Path) -> None:
    # Bandit only tests code inside a function, so both fixtures wrap the handler in one.
    stale = tmp_path / "stale.py"
    stale.write_text(
        "def f() -> int:\n    try:\n        return 1\n"
        "    except Exception:  # nosec B110\n        return 0\n",
        encoding="utf-8",
    )
    assert _bandit_stale_nosec(stale, config=False), "bandit printed no warning for a stale nosec"
    live = tmp_path / "live.py"
    live.write_text(
        "def f() -> None:\n    try:\n        return None\n"
        "    except Exception:  # nosec B110\n        pass\n",
        encoding="utf-8",
    )
    assert not _bandit_stale_nosec(live, config=False)


@requires_bandit
def test_no_nosec_comment_is_stale() -> None:
    """Remove a `# nosec` that suppresses nothing, or move it to the line bandit reports."""
    targets = [
        REPO_ROOT / name for name in ("src", "tools", "bootstrap.py") if (REPO_ROOT / name).exists()
    ]
    stale = _bandit_stale_nosec(*targets)
    assert not stale, "stale nosec comments:\n" + "\n".join(stale)

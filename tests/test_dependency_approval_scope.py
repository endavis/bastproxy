"""The architectural conventions put every new dependency under Ask First (#842).

`.github/CONTRIBUTING.md` requires approval before adding any dependency: a
runtime dependency, an entry in the `dev` or `security` extra, or a type stub.
`architectural-conventions.md` once scoped that rule to runtime dependencies in
three places, which read as permission to add a dev library without asking.
These tests hold the two files to the same scope.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRIBUTING = REPO_ROOT / ".github" / "CONTRIBUTING.md"
CONVENTIONS = REPO_ROOT / "docs" / "development" / "ai" / "architectural-conventions.md"
APPROVAL = re.compile(r"\bask(?:ing)? the user\b|\bapproval\b", re.IGNORECASE)


def _normalized(path: Path) -> str:
    """Return the file's text with every run of whitespace collapsed to one space."""
    return " ".join(path.read_text(encoding="utf-8").split())


def _policy_scope() -> str:
    """Return what CONTRIBUTING's Ask First policy says needs approval."""
    match = re.search(
        r"Get approval before you add any dependency: ([^.]+)\.", _normalized(CONTRIBUTING)
    )
    assert match, "CONTRIBUTING.md no longer states what needs approval"
    return match.group(1)


def test_conventions_name_the_same_scope_as_contributing() -> None:
    assert _policy_scope() in _normalized(CONVENTIONS)


def test_no_approval_rule_is_scoped_to_runtime_dependencies() -> None:
    """A sentence that asks for approval and names runtime deps must name the dev extra too."""
    sentences = re.split(r"(?<=[.!?])\s+", _normalized(CONVENTIONS))
    narrowed = [
        sentence
        for sentence in sentences
        if APPROVAL.search(sentence) and "runtime" in sentence.lower() and "`dev`" not in sentence
    ]
    assert not narrowed

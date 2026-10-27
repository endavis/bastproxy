"""The docs list the checks `doit release` makes before it pulls, in the order it makes them (#921).

Three docs carry the list. #918 moved the `--increment` check and updated one of them. The other two
left `--increment` out and put the clean-tree check first, although the task checks the tree only
after it has validated both flag values.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Each doc's `doit release` step list: the section it is in, then the line just before the list.
_LISTS = {
    ".github/CONTRIBUTING.md": ("## Release Process", "**What `doit release` does:**"),
    "docs/development/doit-tasks-reference.md": ("### `release`", "**What it does:**"),
    "docs/development/release-and-automation.md": (
        "### Step 1: Create the release PR (`doit release`)",
        "**What it does:**",
    ),
}

# What create_release_pr checks before it pulls, in its order (tools/doit/release.py).
_BEFORE_THE_PULL = (
    r"`main`",
    r"`--prerelease`",
    r"`--increment`",
    r"uncommitted|clean working tree",
    r"\bPulls\b",
)

_ITEM = re.compile(r"^\d+\. ")


def _steps(doc: str) -> str:
    """The numbered items of a doc's `doit release` step list."""
    section, marker = _LISTS[doc]
    text = (ROOT / doc).read_text(encoding="utf-8")
    after = text.split(f"\n{section}\n", 1)[1].split(f"\n{marker}\n", 1)[1]
    items = []
    for line in after.lstrip("\n").splitlines():
        if not _ITEM.match(line):
            break
        items.append(line)
    return "\n".join(items)


@pytest.mark.parametrize("doc", sorted(_LISTS))
def test_the_list_names_the_checks_before_the_pull_in_code_order(doc: str) -> None:
    steps = _steps(doc)
    positions = {}
    for check in _BEFORE_THE_PULL:
        match = re.search(check, steps)
        if match:
            positions[check] = match.start()

    missing = [check for check in _BEFORE_THE_PULL if check not in positions]
    assert not missing, f"The doit release steps in {doc} do not mention {missing}:\n{steps}"

    order = sorted(_BEFORE_THE_PULL, key=positions.__getitem__)
    assert order == list(_BEFORE_THE_PULL), (
        f"The doit release steps in {doc} name these checks in the order {order}, "
        f"but the task makes them in the order {list(_BEFORE_THE_PULL)}:\n{steps}"
    )

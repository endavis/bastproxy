"""The workflow table in github-repository-settings.md matches each workflow's permissions (#880).

After #695 cut `benchmark.yml` to `contents: read`, with `contents: write` on its `store` job alone,
the table's Benchmark row still listed `contents: write` and `pull-requests: write`. This compares
every row with the permissions its workflow file grants, at workflow scope and job scope.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SETTINGS_DOC = ROOT / "docs" / "development" / "github-repository-settings.md"
WORKFLOWS = ROOT / ".github" / "workflows"

# | **Name** | `file.yml` | Trigger | Permissions |
_ROW = re.compile(
    r"^\| \*\*(?P<name>.+?)\*\* \| `(?P<file>[^`]+\.ya?ml)` \| .*? \| (?P<perms>.+) \|$"
)
_GRANT = re.compile(r"`([a-z-]+: [a-z]+|read-all|write-all)`")


def _rows() -> list[tuple[str, str, frozenset[str]]]:
    rows = []
    for line in SETTINGS_DOC.read_text(encoding="utf-8").splitlines():
        match = _ROW.match(line)
        if match:
            grants = frozenset(_GRANT.findall(match["perms"]))
            rows.append((match["name"], match["file"], grants))
    return rows


def _granted(workflow: Path) -> frozenset[str]:
    """Every permission the workflow grants, at workflow scope or in any job."""
    data = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    scopes = [data.get("permissions")]
    scopes += [job.get("permissions") for job in (data.get("jobs") or {}).values()]
    granted: set[str] = set()
    for scope in scopes:
        if isinstance(scope, str):
            granted.add(scope)  # read-all / write-all
        elif scope:
            granted.update(f"{name}: {access}" for name, access in scope.items())
    return frozenset(granted)


ROWS = _rows()


def test_the_table_has_rows() -> None:
    assert ROWS, f"no workflow rows parsed from {SETTINGS_DOC}"


@pytest.mark.parametrize(("name", "file", "documented"), ROWS, ids=[row[0] for row in ROWS])
def test_row_matches_its_workflow(name: str, file: str, documented: frozenset[str]) -> None:
    granted = _granted(WORKFLOWS / file)

    assert documented == granted, (
        f"The {name} row in {SETTINGS_DOC.name} lists {sorted(documented)}, "
        f"but {file} grants {sorted(granted)}"
    )

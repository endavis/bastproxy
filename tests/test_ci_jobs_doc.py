"""ci-cd-testing.md describes the CI that ci.yml runs (#906, #922).

The Pipeline Jobs section showed samples of a `code-quality` job and a `security` job, which
`ci.yml` does not have, and marked type checking `continue-on-error`, which no step in `ci.yml`
sets. This compares the table's jobs with `ci.yml`'s, and the `doit` tasks each row names with the
ones its job runs.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CI_DOC = ROOT / "docs" / "development" / "ci-cd-testing.md"
CI_YML = ROOT / ".github" / "workflows" / "ci.yml"

# | `job` | What it runs |
_ROW = re.compile(r"^\| `(?P<job>[a-z-]+)` \| (?P<runs>.+) \|$")
_DOC_TASK = re.compile(r"`doit (\w+)`")
_RUN_TASK = re.compile(r"\bdoit (\w+)")


def _rows() -> dict[str, frozenset[str]]:
    """Each job in the table, with the `doit` tasks its row names."""
    text = CI_DOC.read_text(encoding="utf-8")
    section = text.split("\n### Pipeline Jobs\n", 1)[-1].split("\n### ", 1)[0]
    rows = {}
    for line in section.splitlines():
        match = _ROW.match(line)
        if match:
            rows[match["job"]] = frozenset(_DOC_TASK.findall(match["runs"]))
    return rows


def _jobs() -> dict[str, frozenset[str]]:
    """Each job in ci.yml, with the `doit` tasks its steps run."""
    jobs = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))["jobs"]
    return {
        name: frozenset(
            task for step in job.get("steps", []) for task in _RUN_TASK.findall(step.get("run", ""))
        )
        for name, job in jobs.items()
    }


ROWS = _rows()
JOBS = _jobs()


def test_the_table_has_rows() -> None:
    assert ROWS, f"no job rows parsed from the Pipeline Jobs section of {CI_DOC.name}"


def test_the_table_lists_the_jobs_in_ci_yml() -> None:
    assert sorted(ROWS) == sorted(JOBS), (
        f"Pipeline Jobs in {CI_DOC.name} lists {sorted(ROWS)}, but ci.yml has {sorted(JOBS)}"
    )


@pytest.mark.parametrize("job", sorted(ROWS))
def test_row_names_the_doit_tasks_its_job_runs(job: str) -> None:
    runs = JOBS.get(job, frozenset())

    assert ROWS[job] == runs, (
        f"The {job} row in {CI_DOC.name} names {sorted(ROWS[job])}, "
        f"but that job in ci.yml runs {sorted(runs)}"
    )


def test_the_doc_does_not_suggest_making_a_check_non_blocking() -> None:
    """The Mypy Type Errors entry suggested `continue-on-error: true` (#922).

    It did not say whether the key went on the step or on the `lint` job, which also runs the
    security scan and the dependency audit. No job or step in ci.yml sets it.
    """
    assert "continue-on-error" not in CI_DOC.read_text(encoding="utf-8")

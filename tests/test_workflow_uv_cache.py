"""Workflows cache uv through setup-uv's built-in cache, not a separate step (#1266).

`astral-sh/setup-uv` with `enable-cache: true` restores and saves uv's cache keyed on
`uv.lock`. A second `actions/cache` step on the uv cache duplicates it, and measured
slower (about 40s against 15s on the Windows test job). Each job that sets up uv enables the
built-in cache, and none keeps the manual step or its `UV_CACHE_DIR`. The release and
TestPyPI build jobs stay uncached: they build the artifact that is published, and never
used a cache.

Reads only `.github/`, so it ships downstream without depending on shed code.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
UNCACHED = {"release.yml", "testpypi.yml"}


def _jobs() -> list[tuple[str, str, dict[str, Any]]]:
    """Return (workflow file, job id, job) for each job with an astral-sh/setup-uv step."""
    found = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job_id, job in (data.get("jobs") or {}).items():
            steps = job.get("steps") or []
            if any(str(s.get("uses", "")).startswith("astral-sh/setup-uv@") for s in steps):
                found.append((path.name, job_id, job))
    return found


JOBS = _jobs()
IDS = [f"{f}:{j}" for f, j, _ in JOBS]


def test_jobs_found() -> None:
    assert JOBS, "no workflow job uses astral-sh/setup-uv"


@pytest.mark.parametrize(("workflow", "job_id", "job"), JOBS, ids=IDS)
def test_setup_uv_enables_cache(workflow: str, job_id: str, job: dict[str, Any]) -> None:
    if workflow in UNCACHED:
        pytest.skip("publishing build jobs stay uncached")
    steps = [s for s in job["steps"] if str(s.get("uses", "")).startswith("astral-sh/setup-uv@")]
    for step in steps:
        assert step.get("with", {}).get("enable-cache") is True, (
            f"{workflow}:{job_id} must set `enable-cache: true` on setup-uv"
        )


@pytest.mark.parametrize(("workflow", "job_id", "job"), JOBS, ids=IDS)
def test_no_separate_uv_cache(workflow: str, job_id: str, job: dict[str, Any]) -> None:
    for step in job["steps"]:
        assert not str(step.get("uses", "")).startswith("actions/cache@"), (
            f"{workflow}:{job_id} keeps an actions/cache step beside setup-uv's cache"
        )
    assert "UV_CACHE_DIR" not in (job.get("env") or {}), (
        f"{workflow}:{job_id} sets UV_CACHE_DIR, which setup-uv manages itself"
    )

"""Every workflow job that sets up Python makes uv use that Python (#1261).

uv builds `.venv` from `.python-version` whatever `actions/setup-python` installed,
so a job that asks for 3.14 can run its tests on 3.12. Each job that has both a
setup-python step and a uv step sets `UV_PYTHON` to the version it requested, and
a `Check the Python version` step fails the job if uv runs another one.

Reads only `.github/`, so it ships downstream without depending on shed code.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
CHECK_NAME = "Check the Python version"
PIN_RUN = re.compile(r"UV_PYTHON=\$\{?PYTHON_VERSION\}?.*\$\"?GITHUB_ENV")
UV_USE = re.compile(r"\buv (sync|run)\b")


def _jobs() -> list[tuple[str, str, dict[str, Any]]]:
    """Return (workflow file, job id, job) for each job with setup-python and a uv step."""
    found = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job_id, job in (data.get("jobs") or {}).items():
            steps = job.get("steps") or []
            has_python = any(
                str(s.get("uses", "")).startswith("actions/setup-python@") for s in steps
            )
            has_uv = any(UV_USE.search(str(s.get("run", ""))) for s in steps)
            if has_python and has_uv:
                found.append((path.name, job_id, job))
    return found


JOBS = _jobs()
IDS = [f"{f}:{j}" for f, j, _ in JOBS]


def _setup_index(steps: list[dict[str, Any]]) -> int:
    return next(
        i for i, s in enumerate(steps) if str(s.get("uses", "")).startswith("actions/setup-python@")
    )


def _first_uv_index(steps: list[dict[str, Any]], pattern: re.Pattern[str]) -> int:
    return next(i for i, s in enumerate(steps) if pattern.search(str(s.get("run", ""))))


def _pin_step_index(steps: list[dict[str, Any]]) -> int | None:
    for i, s in enumerate(steps):
        if PIN_RUN.search(str(s.get("run", ""))):
            return i
    return None


def test_discovery_finds_the_jobs() -> None:
    assert ("ci.yml", "test") in {(f, j) for f, j, _ in JOBS}
    assert len(JOBS) >= 8


@pytest.mark.parametrize(("name", "job_id", "job"), JOBS, ids=IDS)
def test_uv_python_matches_the_requested_version(
    name: str, job_id: str, job: dict[str, Any]
) -> None:
    steps = job["steps"]
    requested = steps[_setup_index(steps)]["with"]["python-version"]
    job_env = (job.get("env") or {}).get("UV_PYTHON")
    if job_env is not None:
        assert job_env == requested
        return
    pin = _pin_step_index(steps)
    assert pin is not None, f"{name}:{job_id} never sets UV_PYTHON"
    assert steps[pin]["env"]["PYTHON_VERSION"] == requested


@pytest.mark.parametrize(("name", "job_id", "job"), JOBS, ids=IDS)
def test_uv_python_is_set_before_uv_runs(name: str, job_id: str, job: dict[str, Any]) -> None:
    steps = job["steps"]
    if (job.get("env") or {}).get("UV_PYTHON") is not None:
        return
    pin = _pin_step_index(steps)
    assert pin is not None
    assert pin > _setup_index(steps)
    assert pin < _first_uv_index(steps, UV_USE)


@pytest.mark.parametrize(("name", "job_id", "job"), JOBS, ids=IDS)
def test_pin_step_has_the_condition_of_setup_python(
    name: str, job_id: str, job: dict[str, Any]
) -> None:
    steps = job["steps"]
    pin = _pin_step_index(steps)
    if pin is None:
        return
    assert steps[pin].get("if") == steps[_setup_index(steps)].get("if")


@pytest.mark.parametrize(("name", "job_id", "job"), JOBS, ids=IDS)
def test_check_step_runs_after_sync_and_before_other_uv_runs(
    name: str, job_id: str, job: dict[str, Any]
) -> None:
    steps = job["steps"]
    named = [i for i, s in enumerate(steps) if s.get("name") == CHECK_NAME]
    assert len(named) == 1, f"{name}:{job_id} needs one {CHECK_NAME!r} step"
    check = named[0]
    step = steps[check]
    assert check > _first_uv_index(steps, re.compile(r"\buv sync\b"))
    assert check < _first_uv_index(steps, re.compile(r"\buv run\b(?!.*\bpython -c\b)"))
    assert "sys.version_info[:2]" in step["run"]
    assert "UV_PYTHON" in step["run"]
    assert step.get("shell") == "bash"


def _check_code() -> str:
    ci = yaml.safe_load((WORKFLOWS / "ci.yml").read_text(encoding="utf-8"))
    step = next(s for s in ci["jobs"]["test"]["steps"] if s.get("name") == CHECK_NAME)
    match = re.search(r"python -c '(.*)'\s*$", step["run"], re.DOTALL)
    assert match is not None
    return match.group(1)


def _run_check(uv_python: str) -> int:
    env = {**os.environ, "UV_PYTHON": uv_python}
    return subprocess.run([sys.executable, "-c", _check_code()], env=env, check=False).returncode


def test_check_code_passes_on_a_match_and_fails_on_a_mismatch() -> None:
    running = f"{sys.version_info[0]}.{sys.version_info[1]}"
    assert _run_check(running) == 0
    assert _run_check("0.0") != 0

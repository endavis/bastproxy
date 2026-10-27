"""The Hypothesis CI profile must exist, be loaded, and impose no deadline.

Property tests were failing on `windows-latest` because a runner took 1506ms on an
example's first call and 0.01ms on the retry — warmup, not the code under test.
The `ci` profile looked protected against that (it suppressed
`HealthCheck.too_slow`) while still failing on it, because the health check and
the per-example deadline are separate mechanisms (#736).

The load check matters as much as the value check: a profile that is registered
but never loaded is configuration that reports success while doing nothing.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from hypothesis import settings

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFTEST = REPO_ROOT / "tests" / "conftest.py"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

CI_PROFILE = "ci"


def test_ci_profile_is_registered() -> None:
    """`settings.get_profile` must find it — guards the checks below from vacuity."""
    assert settings.get_profile(CI_PROFILE) is not None


def test_ci_profile_imposes_no_deadline() -> None:
    """A wall-clock budget on a shared runner fails for reasons unrelated to the property.

    These tests assert what a generated value *is*, never how long producing it
    took; `benchmark.yml` covers timing. Any finite deadline is a threshold a slow
    runner can cross, which is how the earlier 200ms -> 500ms relaxation still
    flaked (#736).
    """
    assert settings.get_profile(CI_PROFILE).deadline is None, (
        "the ci Hypothesis profile must set deadline=None; a finite deadline "
        "makes property tests fail on runner warmup (#736)"
    )


def test_ci_workflow_actually_loads_the_ci_profile() -> None:
    """CI must set `HYPOTHESIS_PROFILE=ci`, or the profile above is dead config.

    `conftest.py` loads whatever `HYPOTHESIS_PROFILE` names, defaulting to
    `default`. Without this the ci profile could be tuned indefinitely while CI
    quietly ran the local one.
    """
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    test_job = workflow["jobs"]["test"]
    env = test_job.get("env", {})

    assert env.get("HYPOTHESIS_PROFILE") == CI_PROFILE, (
        f"ci.yml's test job must set HYPOTHESIS_PROFILE: {CI_PROFILE}; "
        f"found {env.get('HYPOTHESIS_PROFILE')!r}"
    )


def test_conftest_reads_the_profile_from_the_environment() -> None:
    """The wiring between the workflow env var and the profile must stay intact."""
    source = CONFTEST.read_text(encoding="utf-8")
    assert re.search(r"load_profile\(\s*os\.environ\.get\(\s*[\"']HYPOTHESIS_PROFILE", source), (
        "conftest.py must load the profile named by HYPOTHESIS_PROFILE, or the "
        "workflow's env var has nothing to act on"
    )


@pytest.mark.parametrize("profile", [CI_PROFILE, "default"])
def test_profiles_keep_a_bounded_example_budget(profile: str) -> None:
    """Dropping the deadline must not turn into an unbounded run.

    `max_examples` is what keeps the suite finite now that nothing times it out.
    """
    max_examples = settings.get_profile(profile).max_examples
    assert 0 < max_examples <= 500, (
        f"{profile} profile has max_examples={max_examples}; keep it bounded so the "
        "suite stays finite without a deadline"
    )

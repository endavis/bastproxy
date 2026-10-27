"""Tests for the production Release publish workflow (issues #665, #837).

Structural asserts on `.github/workflows/release.yml`. The central regression
guard is the artifact split: SBOM files (`sbom.json`, `sbom.xml`) must live
in a separate `sbom` artifact from the wheels/sdist `dist` artifact, because
twine (called by the publish jobs) inspects every file in `packages-dir` and
rejects anything that isn't a `.whl` or `.tar.gz` with `InvalidDistribution`.

A second guard (#837) checks the `build` job runs `doit wheel_check` against
the built artifacts — after `uv build`, before the `dist` artifact uploads —
so a packaging regression (missing module, broken entry point, missing
`py.typed`) fails the release before it ships.

These tests do not execute the workflow — they only verify its shape. Sibling
file: `tests/test_testpypi_workflow.py`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

WORKFLOW_PATH = Path(__file__).parent.parent / ".github" / "workflows" / "release.yml"


def _load_workflow() -> dict[Any, Any]:
    """Load and parse the Release workflow YAML.

    The explicit ``encoding="utf-8"`` is required for Windows, where the
    default ``locale.getpreferredencoding()`` is ``cp1252``.
    """
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    data: dict[Any, Any] = yaml.safe_load(content)
    return data


def _steps_for_job(job_name: str) -> list[dict[Any, Any]]:
    """Return the ordered ``steps`` list for the named job."""
    wf = _load_workflow()
    jobs = wf.get("jobs")
    assert isinstance(jobs, dict), "workflow must have a 'jobs' mapping"
    job = jobs.get(job_name)
    assert isinstance(job, dict), f"workflow must define job '{job_name}'"
    steps = job.get("steps")
    assert isinstance(steps, list), f"'{job_name}' must have a 'steps' list"
    return steps


def _upload_steps_for_job(job_name: str) -> list[dict[Any, Any]]:
    """Return all upload-artifact steps for the named job."""
    return [
        s
        for s in _steps_for_job(job_name)
        if isinstance(s, dict) and "upload-artifact" in str(s.get("uses", ""))
    ]


class TestBuildArtifactsSeparation:
    """SBOMs must not be in the dist artifact (issue #665)."""

    def test_dist_and_sbom_are_separate_uploads(self) -> None:
        """build job must have two upload-artifact steps: 'dist' and 'sbom'."""
        uploads = _upload_steps_for_job("build")
        names = sorted(str(s.get("with", {}).get("name", "")) for s in uploads)
        assert names == ["dist", "sbom"], (
            f"build job must upload exactly 'dist' and 'sbom' artifacts; got {names}"
        )

    def test_dist_artifact_excludes_sbom(self) -> None:
        """The 'dist' artifact's path must not include 'sbom' patterns.

        Twine reads every file in dist/ and rejects sbom.json / sbom.xml
        with InvalidDistribution, breaking publish-testpypi and publish.
        """
        uploads = _upload_steps_for_job("build")
        dist_step = next(s for s in uploads if s.get("with", {}).get("name") == "dist")
        path_value = str(dist_step["with"].get("path", ""))
        assert "sbom" not in path_value.lower(), (
            f"'dist' artifact path must not include sbom files; got {path_value!r}"
        )

    def test_sbom_artifact_includes_sbom_files(self) -> None:
        """The 'sbom' artifact path must include sbom.json and sbom.xml."""
        uploads = _upload_steps_for_job("build")
        sbom_step = next(s for s in uploads if s.get("with", {}).get("name") == "sbom")
        path_value = str(sbom_step["with"].get("path", ""))
        assert "sbom.json" in path_value
        assert "sbom.xml" in path_value


class TestWheelCheckOrdering:
    """`doit wheel_check` must run on the real artifact, before it uploads (issue #837)."""

    def _wheel_check_index(self, steps: list[dict[Any, Any]]) -> int:
        for index, step in enumerate(steps):
            if "doit wheel_check" in str(step.get("run", "")):
                return index
        raise AssertionError("build job has no step running `doit wheel_check`")

    def test_build_job_runs_wheel_check(self) -> None:
        """The step exists at all, and targets the already-built dist/ wheel."""
        steps = _steps_for_job("build")
        index = self._wheel_check_index(steps)
        assert "--dist=dist" in str(steps[index].get("run", "")), (
            "wheel_check must check the dist/ wheel that actually gets uploaded, "
            "not rebuild a fresh one"
        )

    def test_wheel_check_runs_after_build_artifacts(self) -> None:
        steps = _steps_for_job("build")
        wheel_check_index = self._wheel_check_index(steps)
        build_index = next(i for i, s in enumerate(steps) if "uv build" in str(s.get("run", "")))
        assert build_index < wheel_check_index, (
            "wheel_check must run after the wheel it checks has been built"
        )

    def test_wheel_check_runs_before_dist_upload(self) -> None:
        steps = _steps_for_job("build")
        wheel_check_index = self._wheel_check_index(steps)
        dist_upload_index = next(
            i
            for i, s in enumerate(steps)
            if "upload-artifact" in str(s.get("uses", ""))
            and s.get("with", {}).get("name") == "dist"
        )
        assert wheel_check_index < dist_upload_index, (
            "wheel_check must run before the dist artifact — built from the same "
            "dist/ directory — is uploaded"
        )

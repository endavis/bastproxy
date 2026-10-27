"""Tests for the TestPyPI publish workflow (issues #659, #837).

Structural asserts on `.github/workflows/testpypi.yml`. The central regression
guard is the `on.push.tags` glob list: it must cover the four PEP440
pre-release shapes that `commitizen` (used by `doit release --prerelease=...`)
actually emits, and it must NOT use the old semver-only pattern that missed
every PEP440 tag this project produces.

A second guard (#837) checks the `build` job runs `doit wheel_check` against
the built artifacts — after `uv build`, before the `dist` artifact upload —
so a packaging regression fails the pre-release before it ships.

These tests do not execute the workflow — they only verify its shape. See
`tests/test_codeql_workflow.py` for the sibling pattern.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

WORKFLOW_PATH = Path(__file__).parent.parent / ".github" / "workflows" / "testpypi.yml"


def _load_workflow() -> dict[Any, Any]:
    """Load and parse the TestPyPI workflow YAML.

    Return type is ``dict[Any, Any]`` (not ``dict[str, Any]``) because PyYAML
    parses the ``on`` key as the boolean ``True`` (YAML 1.1 alias).

    The explicit ``encoding="utf-8"`` is required for Windows, where the
    default ``locale.getpreferredencoding()`` is ``cp1252`` and chokes on any
    non-ASCII content — see the sibling test file for #430 context.
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


class TestPushTagTriggers:
    """The PEP440 pre-release tag patterns must be present; semver-only absent."""

    def _tag_patterns(self) -> list[str]:
        wf = _load_workflow()
        # PyYAML parses bare 'on' as the boolean True.
        on_section = wf.get("on") or wf.get(True)
        assert isinstance(on_section, dict), "workflow must have an 'on' mapping"
        push_section = on_section.get("push")
        assert isinstance(push_section, dict), "workflow must have an 'on.push' mapping"
        tags = push_section.get("tags")
        assert isinstance(tags, list), "workflow must have an 'on.push.tags' list"
        return [str(t) for t in tags]

    def test_alpha_pattern_present(self) -> None:
        """PEP440 alpha tags (e.g. v0.1.0a0) must trigger the workflow."""
        assert "v*a[0-9]*" in self._tag_patterns()

    def test_beta_pattern_present(self) -> None:
        """PEP440 beta tags (e.g. v0.1.0b1) must trigger the workflow."""
        assert "v*b[0-9]*" in self._tag_patterns()

    def test_rc_pattern_present(self) -> None:
        """PEP440 rc tags (e.g. v0.1.0rc0) must trigger the workflow."""
        assert "v*rc[0-9]*" in self._tag_patterns()

    def test_dev_pattern_present(self) -> None:
        """PEP440 dev tags (e.g. v0.1.0.dev2) must trigger the workflow."""
        assert "v*.dev[0-9]*" in self._tag_patterns()

    def test_semver_only_pattern_absent(self) -> None:
        """The old semver-style glob that missed all PEP440 tags must be gone."""
        assert "v*-[a-zA-Z]*" not in self._tag_patterns(), (
            "The old semver-only glob did not match commitizen's PEP440 pre-release "
            "tags (e.g. v0.1.0a0) and must stay out to avoid regressing #659."
        )


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
            "wheel_check must run before the dist artifact is uploaded"
        )

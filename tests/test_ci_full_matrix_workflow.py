"""Tests for the CI (full matrix) dispatch workflow configuration.

These tests are structural asserts on the parsed YAML. They do not execute the
workflow -- they only verify its shape.

This workflow exists to preserve the ``full-matrix`` label UX (adding the
label on a PR triggers a run across the middle Python versions) while keeping
the ``labeled`` event off the main ``ci.yml`` trigger list (see issue #424).
The dispatch job is a thin wrapper: a single ``if:`` guard checks the label
name, then delegates to ``ci.yml`` via ``workflow_call`` with
``full_matrix: true``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

WORKFLOW_PATH = Path(__file__).parent.parent / ".github" / "workflows" / "ci-full-matrix.yml"


def _load_workflow() -> dict[Any, Any]:
    """Load and parse the CI full-matrix workflow YAML.

    Return type is ``dict[Any, Any]`` (not ``dict[str, Any]``) because
    PyYAML parses the ``on`` key as the boolean ``True`` (YAML 1.1 alias).

    The explicit ``encoding="utf-8"`` is required for Windows, where the
    default ``locale.getpreferredencoding()`` is cp1252 and chokes on any
    non-ASCII content in the workflow file (lesson from issue #430).
    """
    # Bind to an annotated local first: yaml.safe_load returns Any,
    # and returning Any from a typed function trips warn_return_any.
    data: dict[Any, Any] = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    return data


class TestWorkflowFile:
    """The workflow file exists and parses as YAML."""

    def test_workflow_file_exists(self) -> None:
        """The CI full-matrix workflow YAML file should exist."""
        assert WORKFLOW_PATH.exists(), f"Workflow not found: {WORKFLOW_PATH}"

    def test_workflow_parses_as_yaml(self) -> None:
        """The workflow file should be valid YAML with a jobs dict."""
        workflow = _load_workflow()
        assert isinstance(workflow, dict)
        assert "jobs" in workflow
        assert isinstance(workflow["jobs"], dict)

    def test_workflow_name(self) -> None:
        """The workflow name is the user-facing check-run label."""
        workflow = _load_workflow()
        assert workflow.get("name") == "CI (full matrix)"


class TestTriggers:
    """Trigger configuration: pull_request ``labeled`` only."""

    def test_only_trigger_is_pull_request(self) -> None:
        """The workflow should have exactly one trigger: ``pull_request``.

        Adding other triggers would break the isolation that issue #424
        establishes between label-driven runs and push-driven runs.
        """
        workflow = _load_workflow()
        triggers = workflow.get("on") or workflow.get(True)
        assert triggers is not None, "workflow has no triggers block"
        assert list(triggers.keys()) == ["pull_request"], (
            "workflow should trigger on pull_request only so label-driven "
            "full-matrix runs stay isolated (issue #424)"
        )

    def test_pull_request_types_is_labeled_only(self) -> None:
        """The only event type should be ``labeled``.

        This is the core regression guard for issue #424: the whole point
        of this workflow is to absorb the ``labeled`` trigger so the main
        ``ci.yml`` no longer fires on every label event.
        """
        workflow = _load_workflow()
        triggers = workflow.get("on") or workflow.get(True)
        assert triggers is not None
        types = triggers["pull_request"]["types"]
        assert types == ["labeled"], f"expected types: [labeled], got {types}"

    def test_pull_request_branches_is_main(self) -> None:
        """The workflow targets PRs to ``main``, matching ``ci.yml``'s scope."""
        workflow = _load_workflow()
        triggers = workflow.get("on") or workflow.get(True)
        assert triggers is not None
        branches = triggers["pull_request"]["branches"]
        assert branches == ["main"]


class TestDispatchJob:
    """The ``dispatch`` job delegates to ``ci.yml`` via ``workflow_call``."""

    def test_dispatch_job_exists(self) -> None:
        """Workflow should define the ``dispatch`` job."""
        workflow = _load_workflow()
        assert "dispatch" in workflow["jobs"]

    def test_dispatch_if_filters_on_full_matrix_label(self) -> None:
        """The job's ``if:`` must filter on the ``full-matrix`` label.

        Without this guard, *any* label applied to a PR would dispatch a
        full-matrix CI run -- a massive waste of minutes.
        """
        workflow = _load_workflow()
        job = workflow["jobs"]["dispatch"]
        assert job["if"] == "github.event.label.name == 'full-matrix'"

    def test_dispatch_uses_local_ci_workflow(self) -> None:
        """The job must call ``./.github/workflows/ci.yml`` via ``workflow_call``.

        The local path (``./...``) is important: using a remote reference
        would run a possibly-different version of the reusable workflow.
        """
        workflow = _load_workflow()
        job = workflow["jobs"]["dispatch"]
        assert job["uses"] == "./.github/workflows/ci.yml"

    def test_dispatch_passes_full_matrix_true(self) -> None:
        """The job must pass ``full_matrix: true`` to the reusable workflow.

        This is what actually flips the matrix from bookend versions to
        middle versions. If the input is omitted or passed as ``false``,
        the full-matrix label will silently not do anything.
        """
        workflow = _load_workflow()
        job = workflow["jobs"]["dispatch"]
        assert job["with"]["full_matrix"] is True

    def test_dispatch_inherits_secrets(self) -> None:
        """``secrets: inherit`` so the reusable workflow can reach secrets
        like ``CODECOV_TOKEN``."""
        workflow = _load_workflow()
        job = workflow["jobs"]["dispatch"]
        assert job.get("secrets") == "inherit"

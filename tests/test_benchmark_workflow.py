"""Tests for the benchmark GitHub Actions workflow configuration.

Rewritten for #695. The previous version asserted the design this issue set out
to remove: `contents: write` and `pull-requests: write` at *workflow* scope, so
they applied to the `pull_request` trigger, plus a store step that ran on PRs and
handed a write-capable `GITHUB_TOKEN` to a third-party action.

The workflow is now split. `benchmark` runs everywhere read-only; `store` holds
the only write grant and runs for pushes to main alone. benchmark-action's own
README makes the same point: "Do not run this workflow on pull request since this
workflow has permission to modify contents."

These tests assert the *property* — no write permission is reachable from a pull
request — rather than the shape of any particular step, so a future restructure
that preserves the property does not have to rewrite them again.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

WORKFLOW_PATH = Path(__file__).parent.parent / ".github" / "workflows" / "benchmark.yml"

# Permissions that let a job change the repository or its pull requests.
WRITE_SCOPES = {"write", "write-all"}


def _load_workflow() -> dict:
    """Load and parse the benchmark workflow YAML."""
    # Windows read_text() defaults to cp1252 which can't decode non-ASCII
    # characters like ✅ in workflow files — always specify utf-8.
    # Bind to an annotated local first: yaml.safe_load returns Any,
    # and returning Any from a typed function trips warn_return_any.
    data: dict = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    return data


def _jobs() -> dict[str, Any]:
    jobs: dict[str, Any] = _load_workflow()["jobs"]
    return jobs


def _write_permissions(perms: str | dict[str, str] | None) -> set[str]:
    """Return the permission names granted at write level in *perms*.

    Accepts the three shapes GitHub allows: absent, a blanket string such as
    ``write-all``, or a per-scope mapping.
    """
    if perms is None:
        return set()
    if isinstance(perms, str):
        return {"<all>"} if perms in WRITE_SCOPES else set()
    return {name for name, level in perms.items() if level in WRITE_SCOPES}


class TestBenchmarkWorkflowExists:
    """Test that the benchmark workflow file exists."""

    def test_workflow_file_exists(self) -> None:
        """The benchmark workflow YAML file should exist."""
        assert WORKFLOW_PATH.exists(), f"Benchmark workflow not found: {WORKFLOW_PATH}"


class TestBenchmarkWorkflowTriggers:
    """Triggers are unchanged by #695 — only what each one may do changed."""

    def test_has_push_trigger(self) -> None:
        triggers = _load_workflow()[True]  # YAML 'on' parses as boolean True
        assert "push" in triggers
        assert "main" in triggers["push"]["branches"]

    def test_has_pull_request_trigger(self) -> None:
        triggers = _load_workflow()[True]
        assert "pull_request" in triggers
        assert "main" in triggers["pull_request"]["branches"]

    def test_has_workflow_dispatch_trigger(self) -> None:
        assert "workflow_dispatch" in _load_workflow()[True]


class TestLeastPrivilege:
    """The security property #695 exists to establish."""

    def test_workflow_scope_grants_no_write(self) -> None:
        """Workflow-level permissions apply to every trigger, including PRs."""
        granted = _write_permissions(_load_workflow().get("permissions"))
        assert not granted, (
            f"benchmark.yml grants {sorted(granted)} at workflow scope, so the "
            "pull_request trigger gets it too. Move it to the job that needs it."
        )

    def test_no_write_permission_is_reachable_from_a_pull_request(self) -> None:
        """Any job with write access must be gated off the pull_request path.

        This is the assertion that matters. A same-repo PR branch runs its own
        code; if a write-capable token is in scope, that code can use it.
        """
        offenders = []
        for name, job in _jobs().items():
            granted = _write_permissions(job.get("permissions"))
            if not granted:
                continue
            condition = str(job.get("if", ""))
            if "github.event_name == 'push'" not in condition:
                offenders.append(f"{name} grants {sorted(granted)} but is not gated on push")

        assert not offenders, "write permission reachable from a pull request:\n  " + "\n  ".join(
            offenders
        )

    def test_benchmark_job_is_explicitly_read_only(self) -> None:
        """The job that runs on PRs states its permissions rather than inheriting."""
        benchmark = _jobs()["benchmark"]
        assert benchmark.get("permissions") == {"contents": "read"}

    def test_store_job_is_gated_on_push_to_main(self) -> None:
        condition = str(_jobs()["store"].get("if", ""))
        assert "github.event_name == 'push'" in condition
        assert "github.ref == 'refs/heads/main'" in condition

    def test_only_the_store_job_holds_the_write_grant(self) -> None:
        writers = {
            name for name, job in _jobs().items() if _write_permissions(job.get("permissions"))
        }
        assert writers == {"store"}, f"unexpected write-capable jobs: {sorted(writers - {'store'})}"

    def test_pull_requests_write_is_not_granted_anywhere(self) -> None:
        """It was never needed: benchmark-action posts *commit* comments."""
        scopes = _write_permissions(_load_workflow().get("permissions"))
        for job in _jobs().values():
            scopes |= _write_permissions(job.get("permissions"))
        assert "pull-requests" not in scopes


class TestBenchmarkJob:
    """The read-only half: run the benchmarks, publish the numbers as an artifact."""

    @staticmethod
    def _steps() -> list[dict]:
        steps: list[dict] = _jobs()["benchmark"]["steps"]
        return steps

    def test_runs_benchmarks(self) -> None:
        assert any("--benchmark-only" in str(s.get("run", "")) for s in self._steps())

    def test_uploads_results_artifact(self) -> None:
        uploads = [s for s in self._steps() if "upload-artifact" in str(s.get("uses", ""))]
        assert uploads, "benchmark results must still be published as an artifact"
        assert uploads[0]["with"]["name"] == "benchmark-results"

    def test_exposes_whether_benchmarks_exist(self) -> None:
        """`store` skips when there is nothing to store, so it needs the output."""
        assert "has-benchmarks" in _jobs()["benchmark"]["outputs"]

    def test_does_not_run_the_third_party_benchmark_action(self) -> None:
        """The action takes a token and writes; it belongs in the gated job.

        Trade-off recorded deliberately: PRs no longer get an automated
        regression comment. The benchmark still runs and its JSON is uploaded,
        and `fail-on-alert` was rejected as a replacement because a wall-clock
        threshold on a shared runner is a flake source — the same lesson as the
        Hypothesis deadline in #736.
        """
        assert not any("github-action-benchmark" in str(s.get("uses", "")) for s in self._steps())


class TestStoreJob:
    """The write half: rewrite the gh-benchmarks branch, on main only."""

    @staticmethod
    def _steps() -> list[dict]:
        steps: list[dict] = _jobs()["store"]["steps"]
        return steps

    def test_depends_on_the_benchmark_job(self) -> None:
        assert _jobs()["store"]["needs"] == "benchmark"

    def test_skips_when_there_are_no_benchmarks(self) -> None:
        assert "needs.benchmark.outputs.has-benchmarks" in str(_jobs()["store"].get("if", ""))

    def test_downloads_the_results_artifact(self) -> None:
        downloads = [s for s in self._steps() if "download-artifact" in str(s.get("uses", ""))]
        assert downloads, "store must consume the artifact rather than re-running benchmarks"
        assert downloads[0]["with"]["name"] == "benchmark-results"

    def test_creates_the_data_branch_when_missing(self) -> None:
        creates = [s for s in self._steps() if s.get("name") == "Create benchmark data branch"]
        assert creates
        assert "gh-benchmarks" in creates[0]["run"]

    def test_branch_check_precedes_branch_creation(self) -> None:
        names = [s.get("name") for s in self._steps()]
        assert names.index("Check for benchmark data branch") < names.index(
            "Create benchmark data branch"
        )

    @pytest.mark.parametrize(
        ("key", "expected"),
        [
            ("tool", "pytest"),
            ("output-file-path", "tmp/benchmark-results.json"),
            ("gh-pages-branch", "gh-benchmarks"),
            ("benchmark-data-dir-path", "dev/bench"),
            ("alert-threshold", "110%"),
            ("auto-push", True),
            ("comment-on-alert", True),
        ],
    )
    def test_store_step_configuration(self, key: str, expected: object) -> None:
        store = next(
            s for s in self._steps() if "github-action-benchmark" in str(s.get("uses", ""))
        )
        assert store["with"][key] == expected

    def test_store_step_uses_github_token(self) -> None:
        store = next(
            s for s in self._steps() if "github-action-benchmark" in str(s.get("uses", ""))
        )
        assert "secrets.GITHUB_TOKEN" in str(store["with"]["github-token"])

    def test_auto_push_is_unconditional_here(self) -> None:
        """The job only runs on push to main, so the step needs no second guard.

        A leftover `${{ github.event_name == 'push' }}` expression would imply
        this job can run otherwise, which is exactly the confusion #695 fixed.
        """
        store = next(
            s for s in self._steps() if "github-action-benchmark" in str(s.get("uses", ""))
        )
        assert store["with"]["auto-push"] is True

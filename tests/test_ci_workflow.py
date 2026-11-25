"""Tests for the CI GitHub Actions workflow configuration.

These tests are structural asserts on the parsed YAML. They do not execute the
workflow -- they only verify its shape.

Scope is intentionally minimal: we guard the three invariants that matter for
issue #424:

1. ``labeled`` is NOT in the ``pull_request`` event type list. Keeping it
   there would cause every auto-applied label on a dependabot PR to spawn a
   duplicate CI run (the motivation for the split introduced in #424).
2. A workflow-level ``concurrency`` block exists with ``cancel-in-progress:
   true`` and a key that includes ``github.head_ref || github.ref``. This
   ensures a new push to a PR cancels the in-flight run on the prior commit.
3. The ``workflow_call`` trigger exposes a ``full_matrix`` boolean input
   (default ``false``) so the sibling ``ci-full-matrix.yml`` workflow can
   dispatch the full-matrix run via ``uses: ./.github/workflows/ci.yml``.

A fourth was added for issue #952: the ``lint`` job runs every check
``doit check`` runs (``test`` aside), and each runs even when one before it
failed, so a PR shows every failing check at once.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

WORKFLOW_PATH = Path(__file__).parent.parent / ".github" / "workflows" / "ci.yml"


def _load_workflow() -> dict[Any, Any]:
    """Load and parse the CI workflow YAML.

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
        """The CI workflow YAML file should exist."""
        assert WORKFLOW_PATH.exists(), f"Workflow not found: {WORKFLOW_PATH}"

    def test_workflow_parses_as_yaml(self) -> None:
        """The workflow file should be valid YAML with a jobs dict."""
        workflow = _load_workflow()
        assert isinstance(workflow, dict)
        assert "jobs" in workflow
        assert isinstance(workflow["jobs"], dict)

    def test_workflow_name(self) -> None:
        """The workflow name is ``CI`` -- the required check-run in branch
        protection and the name referenced by ``ci-full-matrix.yml``."""
        workflow = _load_workflow()
        assert workflow.get("name") == "CI"


class TestPullRequestTriggerHasNoLabeledType:
    """The main CI workflow should no longer fire on label events (issue #424).

    Label-driven full-matrix runs are handled by ``ci-full-matrix.yml``, which
    calls this workflow via ``workflow_call``. Leaving ``labeled`` in the
    trigger list here would re-introduce the duplicate-run problem.
    """

    def test_labeled_not_in_pull_request_types(self) -> None:
        """The ``labeled`` event type must NOT appear in ``pull_request.types``."""
        workflow = _load_workflow()
        triggers = workflow.get("on") or workflow.get(True)
        assert triggers is not None, "workflow has no triggers block"
        pr = triggers["pull_request"]
        types = pr["types"]
        assert "labeled" not in types, (
            f"'labeled' must not be in pull_request.types; got {types}. "
            "Label-driven runs are handled by ci-full-matrix.yml (issue #424)."
        )

    def test_pull_request_types_cover_core_lifecycle(self) -> None:
        """The PR trigger must still cover the core lifecycle events.

        We keep ``opened``, ``synchronize``, and ``reopened`` so that CI runs
        on every push and on reopened PRs. Removing any of these would leave
        a PR without CI coverage.
        """
        workflow = _load_workflow()
        triggers = workflow.get("on") or workflow.get(True)
        assert triggers is not None
        types = triggers["pull_request"]["types"]
        for required in ("opened", "synchronize", "reopened"):
            assert required in types, f"pull_request.types missing '{required}': {types}"


class TestConcurrency:
    """Workflow-level concurrency block cancels stale runs on new pushes."""

    def test_concurrency_block_exists(self) -> None:
        """The workflow must declare a top-level ``concurrency`` block."""
        workflow = _load_workflow()
        assert "concurrency" in workflow, "workflow must declare a concurrency block"

    def test_concurrency_group_keyed_on_ref(self) -> None:
        """The group key must reference ``head_ref || ref``.

        ``head_ref`` is only set for PR events and points at the PR's source
        branch; ``ref`` is the fallback for push/schedule/dispatch events.
        Using the pair gives each PR its own concurrency lane while still
        scoping main-branch runs to ``refs/heads/main``.
        """
        workflow = _load_workflow()
        group: str = workflow["concurrency"]["group"]
        assert "github.head_ref" in group
        assert "github.ref" in group

    def test_concurrency_cancel_in_progress(self) -> None:
        """``cancel-in-progress: true`` supersedes stale runs on a new push."""
        workflow = _load_workflow()
        assert workflow["concurrency"]["cancel-in-progress"] is True


class TestWorkflowCallInputs:
    """``workflow_call`` exposes a ``full_matrix`` boolean input."""

    def test_workflow_call_present(self) -> None:
        """The workflow must be callable as a reusable workflow.

        ``ci-full-matrix.yml`` invokes this workflow via
        ``uses: ./.github/workflows/ci.yml``; removing ``workflow_call``
        here breaks the full-matrix dispatch path.
        """
        workflow = _load_workflow()
        triggers = workflow.get("on") or workflow.get(True)
        assert triggers is not None
        assert "workflow_call" in triggers

    def test_workflow_call_has_full_matrix_input(self) -> None:
        """``workflow_call.inputs.full_matrix`` must be declared."""
        workflow = _load_workflow()
        triggers = workflow.get("on") or workflow.get(True)
        assert triggers is not None
        wc = triggers["workflow_call"]
        assert wc is not None, "workflow_call must declare an inputs block"
        assert "inputs" in wc
        assert "full_matrix" in wc["inputs"]

    def test_full_matrix_input_is_boolean(self) -> None:
        """The ``full_matrix`` input must be declared as a boolean."""
        workflow = _load_workflow()
        triggers = workflow.get("on") or workflow.get(True)
        assert triggers is not None
        fm = triggers["workflow_call"]["inputs"]["full_matrix"]
        assert fm["type"] == "boolean"

    def test_full_matrix_input_defaults_false(self) -> None:
        """The default must be ``false`` so plain ``workflow_call`` runs
        the bookend matrix, matching the pre-#424 behavior."""
        workflow = _load_workflow()
        triggers = workflow.get("on") or workflow.get(True)
        assert triggers is not None
        fm = triggers["workflow_call"]["inputs"]["full_matrix"]
        assert fm["default"] is False


def _lint_steps() -> list[dict[str, Any]]:
    """Return the steps of the ``lint`` job."""
    steps: list[dict[str, Any]] = _load_workflow()["jobs"]["lint"]["steps"]
    return steps


def _lint_check_steps() -> list[dict[str, Any]]:
    """Return the ``lint`` job's steps that run a ``doit`` task."""
    return [step for step in _lint_steps() if "doit " in step.get("run", "")]


class TestLintJob:
    """The lint job runs each check and reports every failing one (#952)."""

    def test_lint_runs_every_check_but_test(self) -> None:
        """Every ``doit check`` task runs in CI; ``test`` and ``docs_build`` have own jobs.

        ``deadcode`` was in ``task_check`` but in no CI job, so a PR could add
        dead code that only the daily check caught.
        """
        from tools.doit.quality import task_check

        expected = set(task_check()["task_dep"]) - {"test", "docs_build"}
        run = {step["run"].split("doit ", 1)[1].split()[0] for step in _lint_check_steps()}
        assert run == expected

    def test_docs_job_runs_docs_build(self) -> None:
        """``docs_build`` is left out of the lint job only because the docs job runs it (#974)."""
        steps: list[dict[str, Any]] = _load_workflow()["jobs"]["docs"]["steps"]
        assert any("doit docs_build" in step.get("run", "") for step in steps)

    def test_each_check_runs_after_an_earlier_failure(self) -> None:
        """A failing check must not skip the checks after it."""
        for step in _lint_check_steps():
            condition = step.get("if", "")
            assert "!cancelled()" in condition, f"{step['name']!r} is skipped after a failure"

    def test_no_check_runs_without_dependencies(self) -> None:
        """When the install fails, the checks are skipped, not each failed on its own."""
        install = next(s for s in _lint_steps() if s.get("name") == "Install dependencies")
        assert install.get("id") == "install"
        for step in _lint_check_steps():
            assert "steps.install.outcome == 'success'" in step.get("if", ""), step["name"]


def _set_matrix_script() -> str:
    """Return the shell script of the ``Set matrix`` step."""
    steps: list[dict[str, Any]] = _load_workflow()["jobs"]["setup"]["steps"]
    return str(next(s for s in steps if s.get("id") == "set-matrix")["run"])


# GitHub runs the step as `bash -e {0}` on the ubuntu-latest setup job. The
# Windows runner's `bash` resolves to wsl.exe with no distribution installed
# (see tests/test_daily_check_workflow.py).
_needs_bash = pytest.mark.skipif(
    sys.platform == "win32",
    reason="the Set matrix step runs under bash on Linux; the Windows runner has no usable bash",
)


def _run_matrix(tmp_path: Path, *, full_matrix: str, all_os: str) -> list[tuple[str, str]]:
    """Run the Set matrix script and return its (os, python-version) pairs."""
    output = tmp_path / "out"
    env = {
        **os.environ,
        "OLDEST": "3.11",
        "NEWEST": "3.14",
        "FULL_MATRIX": full_matrix,
        "ALL_OS": all_os,
        "GITHUB_OUTPUT": str(output),
    }
    subprocess.run(["bash", "-e", "-c", _set_matrix_script()], env=env, check=True)
    line = next(ln for ln in output.read_text().splitlines() if ln.startswith("matrix="))
    include = json.loads(line.removeprefix("matrix="))["include"]
    return [(e["os"], e["python-version"]) for e in include]


class TestOsMatrix:
    """Pull requests skip macOS and old-Python Windows; other callers run all (#1190)."""

    def test_all_os_input_defaults_false_on_both_triggers(self) -> None:
        workflow = _load_workflow()
        triggers = workflow.get("on") or workflow.get(True)
        assert triggers is not None
        for trigger in ("workflow_call", "workflow_dispatch"):
            all_os = triggers[trigger]["inputs"]["all_os"]
            assert all_os["type"] == "boolean"
            assert all_os["default"] is False

    @_needs_bash
    def test_default_is_linux_bookends_only(self, tmp_path: Path) -> None:
        # bastproxy: pull requests stay ubuntu-only (kept from the #9 sync); upstream
        # also runs Windows on the newest version here (#148).
        pairs = _run_matrix(tmp_path, full_matrix="false", all_os="false")
        assert sorted(pairs) == [
            ("ubuntu-latest", "3.11"),
            ("ubuntu-latest", "3.14"),
        ]

    @_needs_bash
    def test_all_os_runs_bookends_everywhere(self, tmp_path: Path) -> None:
        pairs = _run_matrix(tmp_path, full_matrix="false", all_os="true")
        assert len(pairs) == 6
        assert {os_name for os_name, _ in pairs} == {
            "ubuntu-latest",
            "windows-latest",
            "macos-latest",
        }

    @_needs_bash
    def test_full_matrix_runs_middle_versions_only(self, tmp_path: Path) -> None:
        pairs = _run_matrix(tmp_path, full_matrix="true", all_os="true")
        assert {v for _, v in pairs} == {"3.12", "3.13"}
        assert len(pairs) == 6

    def test_callers_pass_all_os(self) -> None:
        workflows = Path(__file__).parent.parent / ".github" / "workflows"
        for name, job in (
            ("release.yml", "test"),
            ("testpypi.yml", "test"),
            ("ci-full-matrix.yml", "dispatch"),
            ("nightly-matrix.yml", "test"),
        ):
            data = yaml.safe_load((workflows / name).read_text(encoding="utf-8"))
            assert data["jobs"][job]["with"]["all_os"] is True, name


def _test_job_steps() -> list[dict[str, Any]]:
    """Return the steps of the ``test`` job."""
    steps: list[dict[str, Any]] = _load_workflow()["jobs"]["test"]["steps"]
    return steps


# The doit tasks the test job runs for Windows only. A project's own doit steps
# (e.g. an install step for its tools) are not in this set and are not checked.
_WINDOWS_TASKS = {"format_check", "security", "cleanup"}


def _doit_task(step: dict[str, Any]) -> str | None:
    """Return the doit task a step runs, or None when it runs no doit task."""
    run = step.get("run", "")
    if "doit " not in run:
        return None
    rest = run.split("doit ", 1)[1].split()
    return rest[0] if rest else None


def _windows_task_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [s for s in steps if _doit_task(s) in _WINDOWS_TASKS]


def _assert_windows_only(steps: list[dict[str, Any]]) -> None:
    selected = _windows_task_steps(steps)
    assert selected
    for step in selected:
        assert "runner.os == 'Windows'" in step.get("if", ""), step["name"]


def _assert_runs_after_failure(steps: list[dict[str, Any]]) -> None:
    for step in _windows_task_steps(steps):
        assert "!cancelled()" in step.get("if", ""), step["name"]


class TestWindowsDoitTasks:
    """The Windows test job runs doit tasks on Git's default checkout (#1293)."""

    def test_windows_job_does_not_configure_autocrlf(self) -> None:
        """Turning autocrlf off hid #1288; the checkout must use Git's defaults."""
        for step in _test_job_steps():
            assert "autocrlf" not in step.get("run", ""), step.get("name")

    def test_windows_job_runs_each_doit_task(self) -> None:
        """format_check (#1288), security (cmd.exe guard, #1291) and cleanup (Rich panel, #1287)."""
        run = {_doit_task(step) for step in _test_job_steps()}
        assert run >= _WINDOWS_TASKS

    def test_doit_steps_run_on_windows_only(self) -> None:
        """Linux runs these tasks in the lint job; the test job adds them for Windows."""
        _assert_windows_only(_test_job_steps())

    def test_doit_steps_run_after_an_earlier_failure(self) -> None:
        """A failing test run must not hide a failing doit task."""
        _assert_runs_after_failure(_test_job_steps())

    def test_projects_own_doit_step_is_not_checked(self) -> None:
        """A project's Linux-only doit step must not trip the Windows checks (#1306)."""
        extra = {
            "name": "Install project tools (Linux)",
            "if": "runner.os == 'Linux'",
            "run": "uv run doit install_tools",
        }
        steps = [*_test_job_steps(), extra]
        _assert_windows_only(steps)
        _assert_runs_after_failure(steps)

    def test_windows_task_missing_cancelled_guard_fails(self) -> None:
        broken = {"name": "x", "if": "runner.os == 'Windows'", "run": "uv run doit security"}
        with pytest.raises(AssertionError):
            _assert_runs_after_failure([broken])

    def test_windows_task_missing_windows_guard_fails(self) -> None:
        broken = {"name": "x", "if": "!cancelled()", "run": "uv run doit security"}
        with pytest.raises(AssertionError):
            _assert_windows_only([broken])


class TestCodecovOptIn:
    """The Codecov upload is opt-in, OIDC-authenticated and uploads one file (#1218).

    It lives in the separate ``coverage`` job, not the ``test`` matrix (#1260).
    """

    @staticmethod
    def _step() -> dict[str, Any]:
        steps: list[dict[str, Any]] = _load_workflow()["jobs"]["coverage"]["steps"]
        return next(s for s in steps if s.get("name") == "Upload coverage to Codecov")

    def test_gated_on_repository_variable(self) -> None:
        condition = self._step()["if"]
        assert "vars.CODECOV_ENABLED == 'true'" in condition

    def test_authenticates_with_oidc_not_a_token(self) -> None:
        step = self._step()
        assert step["with"]["use_oidc"] is True
        assert "CODECOV_TOKEN" not in yaml.safe_dump(step)

    def test_uploads_only_the_produced_report(self) -> None:
        with_ = self._step()["with"]
        assert with_["disable_search"] is True
        assert with_["files"] == "./tmp/coverage.xml"

    def test_job_can_request_an_oidc_token(self) -> None:
        perms = _load_workflow()["jobs"]["coverage"]["permissions"]
        assert perms == {"contents": "read", "id-token": "write"}

    def test_callers_grant_id_token(self) -> None:
        """A called job cannot hold more than its caller grants."""
        workflows = Path(__file__).parent.parent / ".github" / "workflows"
        for name, job in (
            ("release.yml", "test"),
            ("testpypi.yml", "test"),
            ("ci-full-matrix.yml", "dispatch"),
            ("nightly-matrix.yml", "test"),
        ):
            data = yaml.safe_load((workflows / name).read_text(encoding="utf-8"))
            granted = [data.get("permissions"), data["jobs"][job].get("permissions")]
            assert any(p and p.get("id-token") == "write" for p in granted), name


class TestCoverageJob:
    """Coverage runs in its own job, not in the test matrix (#1260)."""

    @staticmethod
    def _jobs() -> dict[str, Any]:
        jobs: dict[str, Any] = _load_workflow()["jobs"]
        return jobs

    def test_test_matrix_has_no_coverage_or_oidc(self) -> None:
        test = self._jobs()["test"]
        text = yaml.safe_dump(test)
        for forbidden in ("--cov", "codecov", "id-token", "permissions"):
            assert forbidden not in text, forbidden

    def test_test_matrix_runs_plain_tests_unconditionally(self) -> None:
        runs = [s for s in self._jobs()["test"]["steps"] if s.get("name") == "Run tests"]
        assert len(runs) == 1
        assert "if" not in runs[0]
        assert runs[0]["run"].startswith("uv run pytest")

    def test_coverage_job_runs_on_newest_linux(self) -> None:
        job = self._jobs()["coverage"]
        assert job["runs-on"] == "ubuntu-latest"
        assert job["needs"] == "setup"
        assert job["env"]["UV_PYTHON"] == "${{ needs.setup.outputs.newest }}"
        setup_py = next(s for s in job["steps"] if "setup-python" in str(s.get("uses")))
        assert setup_py["with"]["python-version"] == "${{ needs.setup.outputs.newest }}"

    def test_coverage_job_measures_coverage_and_reports_core(self) -> None:
        job = self._jobs()["coverage"]
        measured = next(s for s in job["steps"] if s.get("name") == "Run tests with coverage")
        assert "--cov" in measured["run"]
        assert measured["env"]["COVERAGE_DEBUG"] == "core"
        assert measured["env"]["COVERAGE_DEBUG_FILE"].startswith("tmp/")
        show = next(s for s in job["steps"] if s.get("name") == "Show the coverage core")
        assert show["if"] == "always()"
        assert "Using core=" in show["run"]

    def test_both_pytest_steps_print_durations(self) -> None:
        jobs = self._jobs()
        coverage_name = "Run tests with coverage"
        steps = [
            next(s for s in jobs["test"]["steps"] if s.get("name") == "Run tests"),
            next(s for s in jobs["coverage"]["steps"] if s.get("name") == coverage_name),
        ]
        for step in steps:
            assert "--durations=0" in step["run"], step["name"]
            assert "--durations-min=0.05" in step["run"], step["name"]

    def test_coverage_job_skipped_on_full_matrix(self) -> None:
        assert "inputs.full_matrix" in self._jobs()["coverage"]["if"]

    def test_ci_complete_needs_coverage_and_accepts_skipped(self) -> None:
        job = self._jobs()["ci-complete"]
        assert "coverage" in job["needs"]
        script = job["steps"][0]["run"]
        assert 'coverage_result="${{ needs.coverage.result }}"' in script
        assert '"$coverage_result" != "skipped"' in script


class TestRunDiagnostics:
    """Timeouts, JUnit artifacts, a run summary and cache logging (#1329)."""

    @staticmethod
    def _jobs() -> dict[str, Any]:
        jobs: dict[str, Any] = _load_workflow()["jobs"]
        return jobs

    @staticmethod
    def _index(steps: list[dict[str, Any]], needle: str) -> int:
        return next(
            i
            for i, s in enumerate(steps)
            if needle in s.get("run", "") or needle in s.get("uses", "")
        )

    def test_every_job_has_a_timeout(self) -> None:
        for name, job in self._jobs().items():
            assert 1 <= job["timeout-minutes"] <= 60, name

    def test_junit_path_matches_across_steps(self) -> None:
        for name in ("test", "coverage"):
            steps = self._jobs()[name]["steps"]
            pytest_step = steps[self._index(steps, "uv run pytest")]
            summary = steps[self._index(steps, "junit_summary.py")]
            upload = steps[self._index(steps, "upload-artifact")]
            assert "--junitxml=tmp/junit.xml" in pytest_step["run"], name
            assert "tmp/junit.xml" in summary["run"], name
            assert upload["with"]["path"] == "tmp/junit.xml", name

    def test_upload_runs_after_failure_and_expires(self) -> None:
        for name in ("test", "coverage"):
            steps = self._jobs()[name]["steps"]
            upload = steps[self._index(steps, "upload-artifact")]
            assert upload["if"] == "always()", name
            assert "retention-days" in upload["with"], name
            assert upload["with"]["if-no-files-found"] == "warn", name

    def test_artifact_names_are_unique(self) -> None:
        names = []
        for name in ("test", "coverage"):
            steps = self._jobs()[name]["steps"]
            names.append(steps[self._index(steps, "upload-artifact")]["with"]["name"])
        assert len(set(names)) == len(names)
        assert "matrix.os" in names[0]
        assert "matrix.python-version" in names[0]

    def test_summary_and_upload_precede_windows_doit_steps(self) -> None:
        steps = _test_job_steps()
        summary = self._index(steps, "junit_summary.py")
        upload = self._index(steps, "upload-artifact")
        for step in _windows_task_steps(steps):
            at = steps.index(step)
            assert summary < at, step["name"]
            assert upload < at, step["name"]

    def test_every_setup_uv_step_logs_its_cache_result(self) -> None:
        for name, job in self._jobs().items():
            steps = job["steps"]
            for i, step in enumerate(steps):
                if "setup-uv" not in step.get("uses", ""):
                    continue
                assert step["id"] == "setup-uv", name
                log = steps[i + 1]
                assert "steps.setup-uv.outputs.cache-hit" in log["env"]["CACHE_HIT"], name
                assert "uv cache hit:" in log["run"], name
                assert "uv run" not in log["run"], name

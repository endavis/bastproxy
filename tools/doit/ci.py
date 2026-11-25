"""Doit task that turns a CI run's job data and JUnit artifacts into timing tables (#1330).

``doit ci_timings --run=<id>`` prints how long each job and step of a workflow run took, read
from the GitHub jobs API. ``--compare=<id>`` adds a baseline run and a delta column, and
``--tests`` (with ``--compare``) diffs per-test durations from the ``junit-*`` artifacts CI
uploads (#1329). The ``ci-triage`` skill drives it to measure a slowdown instead of guessing.
"""

from __future__ import annotations

import json
import shutil
import subprocess  # nosec B404  # subprocess is required for doit tasks
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from doit.tools import title_with_actions
from rich.console import Console

from tools.doit.base import verbatim
from tools.doit.github import _run_gh_with_retry
from tools.junit_summary import parse_junit

REPO_ROOT = Path(__file__).resolve().parents[2]

JOBS_PER_PAGE = 100
TOP_TESTS = 25


class GhUnavailableError(RuntimeError):
    """``gh`` is missing or not authenticated."""


@dataclass(frozen=True)
class StepTiming:
    """The duration of one job (``step == ""``) or one step of a job."""

    job: str
    step: str
    seconds: float | None


@dataclass(frozen=True)
class TimingRow:
    """A job, step or test with its current duration, its baseline and the difference."""

    job: str
    step: str
    current: float | None
    baseline: float | None
    delta: float | None


def ensure_gh() -> None:
    """Raise :class:`GhUnavailableError` unless ``gh`` is installed and authenticated."""
    if shutil.which("gh") is None:
        raise GhUnavailableError("gh is not installed")
    result = _run_gh_with_retry(["gh", "auth", "status"], check=False)
    if result.returncode != 0:
        raise GhUnavailableError("gh is not authenticated; run `gh auth login`")


def validate_run_id(run_id: str) -> str:
    """Return *run_id* when it is all digits; it goes into an API path, so nothing else passes.

    Raises:
        ValueError: *run_id* is empty or not made of digits only.
    """
    if not run_id or not run_id.isascii() or not run_id.isdigit():
        raise ValueError(f"run id must be digits only, got {run_id!r}")
    return run_id


def _seconds(started: str | None, completed: str | None) -> float | None:
    """Return the seconds between two ISO 8601 timestamps, or ``None`` when either is missing."""
    if not started or not completed:
        return None
    start = datetime.fromisoformat(started.replace("Z", "+00:00"))
    end = datetime.fromisoformat(completed.replace("Z", "+00:00"))
    return (end - start).total_seconds()


def fetch_jobs(run_id: str, console: Console | None = None) -> list[dict[str, Any]]:
    """Return the jobs of run *run_id* from the GitHub API.

    Prints a warning when the run has more jobs than one page holds.

    Raises:
        subprocess.CalledProcessError: the API call failed.
    """
    result = _run_gh_with_retry(
        [
            "gh",
            "api",
            f"repos/{{owner}}/{{repo}}/actions/runs/{validate_run_id(run_id)}/jobs"
            f"?per_page={JOBS_PER_PAGE}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout)
    jobs: list[dict[str, Any]] = data.get("jobs", [])
    total = data.get("total_count", len(jobs))
    if total > len(jobs) and console is not None:
        console.print(
            verbatim(f"Warning: run {run_id} has {total} jobs; showing {len(jobs)}.", "yellow")
        )
    return jobs


def parse_jobs(jobs: list[dict[str, Any]]) -> list[StepTiming]:
    """Return one :class:`StepTiming` per job and per step, in API order."""
    timings: list[StepTiming] = []
    for job in jobs:
        name = str(job.get("name", ""))
        timings.append(
            StepTiming(name, "", _seconds(job.get("started_at"), job.get("completed_at")))
        )
        for step in job.get("steps") or []:
            timings.append(
                StepTiming(
                    name,
                    str(step.get("name", "")),
                    _seconds(step.get("started_at"), step.get("completed_at")),
                )
            )
    return timings


def _sort_key(row: TimingRow) -> tuple[bool, float]:
    return (row.delta is None, -(row.delta or 0.0))


def compare_timings(current: list[StepTiming], baseline: list[StepTiming]) -> list[TimingRow]:
    """Join two runs on ``(job, step)``, sorted by delta, largest increase first.

    A key present on one side keeps ``None`` for the other, and so for the delta, which sorts last.
    """
    cur = {(t.job, t.step): t.seconds for t in current}
    base = {(t.job, t.step): t.seconds for t in baseline}
    rows = []
    for key in [*cur, *(k for k in base if k not in cur)]:
        c, b = cur.get(key), base.get(key)
        rows.append(TimingRow(key[0], key[1], c, b, None if c is None or b is None else c - b))
    return sorted(rows, key=_sort_key)


def list_junit_artifacts(run_id: str) -> list[str]:
    """Return the names of the non-expired ``junit-*`` artifacts of run *run_id*.

    Raises:
        subprocess.CalledProcessError: the API call failed.
    """
    result = _run_gh_with_retry(
        [
            "gh",
            "api",
            f"repos/{{owner}}/{{repo}}/actions/runs/{validate_run_id(run_id)}/artifacts"
            f"?per_page={JOBS_PER_PAGE}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    artifacts = json.loads(result.stdout).get("artifacts", [])
    return sorted(
        str(a["name"])
        for a in artifacts
        if str(a.get("name", "")).startswith("junit-") and not a.get("expired", False)
    )


def download_junit(run_id: str, names: list[str], dest: Path) -> dict[str, dict[str, float]]:
    """Download artifacts *names* of run *run_id* under *dest*; return ``{name: {test: seconds}}``.

    Raises:
        subprocess.CalledProcessError: a download failed.
    """
    out: dict[str, dict[str, float]] = {}
    for name in names:
        target = dest / name
        _run_gh_with_retry(
            ["gh", "run", "download", validate_run_id(run_id), "-n", name, "-D", str(target)],
            capture_output=True,
            text=True,
            check=True,
        )
        tests: dict[str, float] = {}
        for report in sorted(target.rglob("*.xml")):
            for result in parse_junit(report):
                tests[result.node_id] = result.seconds
        out[name] = tests
    return out


def compare_tests(
    current: dict[str, dict[str, float]],
    baseline: dict[str, dict[str, float]],
    top: int = TOP_TESTS,
) -> list[TimingRow]:
    """Diff per-test durations of artifacts present in both runs; keep the *top* largest deltas.

    The row's ``job`` is the artifact name and its ``step`` the test node id.
    """
    rows: list[TimingRow] = []
    for artifact, tests in current.items():
        base = baseline.get(artifact)
        if base is None:
            continue
        for node_id, seconds in tests.items():
            before = base.get(node_id)
            rows.append(
                TimingRow(
                    artifact,
                    node_id,
                    seconds,
                    before,
                    None if before is None else seconds - before,
                )
            )
    return sorted(rows, key=_sort_key)[:top]


def _fmt(value: float | None, signed: bool = False) -> str:
    if value is None:
        return "-"
    return f"{value:+.1f}s" if signed else f"{value:.1f}s"


def render_table(rows: list[TimingRow], with_baseline: bool) -> str:
    """Render *rows* as fixed-width text; baseline and delta columns only when comparing."""
    header = ["Job", "Step", "Current"]
    if with_baseline:
        header += ["Baseline", "Delta"]
    body = []
    for row in rows:
        cells = [row.job, row.step or "(job)", _fmt(row.current)]
        if with_baseline:
            cells += [_fmt(row.baseline), _fmt(row.delta, signed=True)]
        body.append(cells)
    widths = [max(len(r[i]) for r in [header, *body]) for i in range(len(header))]
    lines = [
        "  ".join(c.ljust(w) for c, w in zip(r, widths, strict=True)).rstrip()
        for r in [header, *body]
    ]
    return "\n".join(lines)


def _fail(console: Console, message: str) -> None:
    console.print(verbatim(message, "red"))
    sys.exit(1)


def _timing_rows(current: list[StepTiming], baseline: list[StepTiming] | None) -> list[TimingRow]:
    if baseline is None:
        return [TimingRow(t.job, t.step, t.seconds, None, None) for t in current]
    return compare_timings(current, baseline)


def _run_tests(run: str, compare: str, console: Console) -> None:
    names_cur = list_junit_artifacts(run)
    names_base = list_junit_artifacts(compare)
    for run_id, names in ((run, names_cur), (compare, names_base)):
        if not names:
            _fail(
                console,
                f"run {run_id} has no junit-* artifacts "
                "(expired after 14 days, or the run predates #1329)",
            )
    tmp_root = REPO_ROOT / "tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=tmp_root, prefix="ci-timings-") as tmp:
        cur = download_junit(run, names_cur, Path(tmp) / "current")
        base = download_junit(compare, names_base, Path(tmp) / "baseline")
    console.print()
    console.print(verbatim(f"Slowest test changes, run {run} against run {compare}:"))
    console.print(
        verbatim(render_table(compare_tests(cur, base), with_baseline=True)), soft_wrap=True
    )


def task_ci_timings() -> dict[str, Any]:
    """Print step durations of a CI run, optionally against a baseline run and per test.

    Options:
        --run: The workflow run ID to measure (required).
        --compare: A baseline run ID; adds Baseline and Delta columns.
        --tests: With --compare, also diff per-test durations from the junit-* artifacts.

    Examples:
        doit ci_timings --run=45602796691
        doit ci_timings --run=45602796691 --compare=45600000000 --tests
    """

    def run_task(run: str = "", compare: str = "", tests: bool = False) -> None:
        console = Console()
        try:
            validate_run_id(run)
            if compare:
                validate_run_id(compare)
        except ValueError as e:
            _fail(console, f"--run (and --compare) must be a run ID of digits only: {e}")
        if tests and not compare:
            _fail(console, "--tests requires --compare: it diffs two runs")
        try:
            ensure_gh()
            current = parse_jobs(fetch_jobs(run, console))
            baseline = parse_jobs(fetch_jobs(compare, console)) if compare else None
            console.print(
                verbatim(render_table(_timing_rows(current, baseline), bool(compare))),
                soft_wrap=True,
            )
            if tests:
                _run_tests(run, compare, console)
        except GhUnavailableError as e:
            _fail(console, str(e))
        except subprocess.CalledProcessError as e:
            _fail(console, f"gh failed: {e.stderr or e}")

    return {
        "actions": [run_task],
        "params": [
            {"name": "run", "long": "run", "type": str, "default": "", "help": "Run ID to measure"},
            {
                "name": "compare",
                "long": "compare",
                "type": str,
                "default": "",
                "help": "Baseline run ID",
            },
            {
                "name": "tests",
                "long": "tests",
                "type": bool,
                "default": False,
                "help": "Also diff per-test durations (requires --compare)",
            },
        ],
        "title": title_with_actions,
    }

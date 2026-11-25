"""Tests for `tools/doit/ci.py` and `doit ci_timings` (#1330). Every `gh` call is mocked."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from tools.doit import ci
from tools.doit.ci import (
    GhUnavailableError,
    StepTiming,
    TimingRow,
    compare_tests,
    compare_timings,
    download_junit,
    ensure_gh,
    fetch_jobs,
    list_junit_artifacts,
    parse_jobs,
    render_table,
    task_ci_timings,
    validate_run_id,
)

RUN_GH = "tools.doit.ci._run_gh_with_retry"
WHICH = "tools.doit.ci.shutil.which"


def _proc(stdout: str = "", returncode: int = 0) -> MagicMock:
    proc = MagicMock()
    proc.stdout = stdout
    proc.returncode = returncode
    return proc


def _job(
    name: str, start: str | None, end: str | None, steps: list[dict[str, Any]]
) -> dict[str, Any]:
    return {"name": name, "started_at": start, "completed_at": end, "steps": steps}


def _step(name: str, start: str | None, end: str | None) -> dict[str, Any]:
    return {"name": name, "started_at": start, "completed_at": end}


T0 = "2026-01-01T00:00:00Z"
T10 = "2026-01-01T00:00:10Z"
T30 = "2026-01-01T00:00:30Z"


def test_parse_jobs_durations_and_nulls() -> None:
    jobs = [_job("test", T0, T30, [_step("Install", T0, T10), _step("Skipped", None, None)])]
    assert parse_jobs(jobs) == [
        StepTiming("test", "", 30.0),
        StepTiming("test", "Install", 10.0),
        StepTiming("test", "Skipped", None),
    ]


def test_parse_jobs_empty_and_missing_steps() -> None:
    assert parse_jobs([]) == []
    assert parse_jobs([{"name": "x", "started_at": T0, "completed_at": T10}]) == [
        StepTiming("x", "", 10.0)
    ]


def test_compare_timings_orders_by_delta_and_keeps_one_sided_keys() -> None:
    cur = [StepTiming("a", "s", 20.0), StepTiming("b", "s", 5.0), StepTiming("c", "new", 1.0)]
    base = [StepTiming("a", "s", 10.0), StepTiming("b", "s", 9.0), StepTiming("d", "gone", 2.0)]
    rows = compare_timings(cur, base)
    assert [(r.job, r.delta) for r in rows[:2]] == [("a", 10.0), ("b", -4.0)]
    assert {(r.job, r.current, r.baseline) for r in rows[2:]} == {
        ("c", 1.0, None),
        ("d", None, 2.0),
    }
    assert all(r.delta is None for r in rows[2:])


def test_compare_timings_same_step_name_in_different_jobs() -> None:
    cur = [StepTiming("a", "Install", 5.0), StepTiming("b", "Install", 9.0)]
    base = [StepTiming("a", "Install", 4.0), StepTiming("b", "Install", 3.0)]
    rows = compare_timings(cur, base)
    assert [(r.job, r.delta) for r in rows] == [("b", 6.0), ("a", 1.0)]


def test_render_table_without_baseline_has_no_delta_columns() -> None:
    text = render_table([TimingRow("test", "", 12.34, None, None)], with_baseline=False)
    assert "Baseline" not in text
    assert "Delta" not in text
    assert "(job)" in text
    assert "12.3s" in text


def test_render_table_with_baseline_shows_signed_delta() -> None:
    rows = [TimingRow("a", "s", 20.0, 10.0, 10.0), TimingRow("b", "s", 5.0, 9.0, -4.0)]
    text = render_table(rows, with_baseline=True)
    assert "Baseline" in text
    assert "+10.0s" in text
    assert "-4.0s" in text


@pytest.mark.parametrize("bad", ["", "12/../x", "abc", "12 3", "١٢٣"])
def test_validate_run_id_rejects(bad: str) -> None:
    with pytest.raises(ValueError, match="digits"):
        validate_run_id(bad)


def test_validate_run_id_accepts_digits() -> None:
    assert validate_run_id("45602796691") == "45602796691"


def test_ensure_gh_missing() -> None:
    with patch(WHICH, return_value=None), pytest.raises(GhUnavailableError, match="not installed"):
        ensure_gh()


def test_ensure_gh_unauthenticated() -> None:
    with (
        patch(WHICH, return_value="/usr/bin/gh"),
        patch(RUN_GH, return_value=_proc(returncode=1)),
        pytest.raises(GhUnavailableError, match="gh auth login"),
    ):
        ensure_gh()


def test_ensure_gh_ok() -> None:
    with patch(WHICH, return_value="/usr/bin/gh"), patch(RUN_GH, return_value=_proc()):
        ensure_gh()


def test_fetch_jobs_passes_exact_arguments() -> None:
    with patch(RUN_GH, return_value=_proc(json.dumps({"jobs": [], "total_count": 0}))) as run:
        assert fetch_jobs("123") == []
    assert run.call_args.args[0] == [
        "gh",
        "api",
        "repos/{owner}/{repo}/actions/runs/123/jobs?per_page=100",
    ]


def test_fetch_jobs_propagates_called_process_error() -> None:
    error = subprocess.CalledProcessError(1, ["gh"], stderr="HTTP 404")
    with patch(RUN_GH, side_effect=error), pytest.raises(subprocess.CalledProcessError):
        fetch_jobs("123")


def test_fetch_jobs_warns_on_truncation() -> None:
    console = MagicMock()
    payload = {"jobs": [{"name": "a"}], "total_count": 150}
    with patch(RUN_GH, return_value=_proc(json.dumps(payload))):
        assert len(fetch_jobs("123", console)) == 1
    assert "150" in str(console.print.call_args.args[0])


def test_fetch_jobs_rejects_bad_id_before_calling_gh() -> None:
    with patch(RUN_GH) as run, pytest.raises(ValueError, match="digits"):
        fetch_jobs("../x")
    run.assert_not_called()


def test_list_junit_artifacts_filters() -> None:
    payload = {
        "artifacts": [
            {"name": "junit-test-ubuntu-3.12", "expired": False},
            {"name": "junit-coverage", "expired": True},
            {"name": "coverage-xml", "expired": False},
        ]
    }
    with patch(RUN_GH, return_value=_proc(json.dumps(payload))):
        assert list_junit_artifacts("1") == ["junit-test-ubuntu-3.12"]


def _junit_xml(cases: dict[str, float]) -> str:
    body = "".join(f'<testcase classname="t" name="{n}" time="{s}"/>' for n, s in cases.items())
    return f"<testsuite>{body}</testsuite>"


def _fake_download(reports: dict[str, dict[str, float]]) -> Callable[..., MagicMock]:
    def run(cmd: list[str], **_: object) -> MagicMock:
        target = Path(cmd[cmd.index("-D") + 1])
        target.mkdir(parents=True)
        (target / "junit.xml").write_text(_junit_xml(reports[cmd[cmd.index("-n") + 1]]))
        return _proc()

    return run


def test_download_junit_parses_reports(tmp_path: Path) -> None:
    with patch(RUN_GH, side_effect=_fake_download({"junit-a": {"x": 1.5}})) as run:
        out = download_junit("9", ["junit-a"], tmp_path)
    assert out == {"junit-a": {"t::x": 1.5}}
    assert run.call_args.args[0][:6] == ["gh", "run", "download", "9", "-n", "junit-a"]


def test_compare_tests_deltas_and_top_cap() -> None:
    cur = {"junit-a": {"t1": 5.0, "t2": 2.0, "t3": 1.0}, "junit-only-cur": {"t": 1.0}}
    base = {"junit-a": {"t1": 1.0, "t2": 2.5}}
    rows = compare_tests(cur, base)
    assert [(r.step, r.delta) for r in rows] == [("t1", 4.0), ("t2", -0.5), ("t3", None)]
    assert all(r.job == "junit-a" for r in rows)
    assert len(compare_tests(cur, base, top=1)) == 1


def _jobs_payload(seconds: int) -> str:
    end = f"2026-01-01T00:00:{seconds:02d}Z"
    return json.dumps(
        {"jobs": [_job("lint", T0, end, [_step("Install", T0, end)])], "total_count": 1}
    )


def _run_task(**kwargs: str | bool) -> None:
    task_ci_timings()["actions"][0](**kwargs)


def test_task_requires_a_run_id(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        _run_task(run="")
    assert exc.value.code == 1
    assert "digits only" in capsys.readouterr().out


def test_task_tests_without_compare_exits(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        _run_task(run="1", tests=True)
    assert exc.value.code == 1
    assert "--tests requires --compare" in capsys.readouterr().out


def test_task_gh_unavailable_exits(capsys: pytest.CaptureFixture[str]) -> None:
    with patch(WHICH, return_value=None), pytest.raises(SystemExit) as exc:
        _run_task(run="1")
    assert exc.value.code == 1
    assert "gh is not installed" in capsys.readouterr().out


def test_task_reports_gh_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    error = subprocess.CalledProcessError(1, ["gh"], stderr="HTTP 404 Not Found")
    with (
        patch(WHICH, return_value="gh"),
        patch(RUN_GH, side_effect=[_proc(), error]),
        pytest.raises(SystemExit),
    ):
        _run_task(run="1")
    assert "HTTP 404 Not Found" in capsys.readouterr().out


def test_task_prints_a_single_run_table(capsys: pytest.CaptureFixture[str]) -> None:
    with (
        patch(WHICH, return_value="gh"),
        patch(RUN_GH, side_effect=[_proc(), _proc(_jobs_payload(20))]),
    ):
        _run_task(run="1")
    out = capsys.readouterr().out
    assert "Install" in out
    assert "20.0s" in out
    assert "Delta" not in out


def test_task_full_path_with_tests(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    artifacts = json.dumps({"artifacts": [{"name": "junit-a", "expired": False}]})
    reports = {"2": {"slow": 9.0}, "1": {"slow": 3.0}}

    def gh(cmd: list[str], **kwargs: object) -> MagicMock:
        if cmd[:3] == ["gh", "auth", "status"]:
            return _proc()
        if cmd[2].endswith("/jobs?per_page=100"):
            return _proc(_jobs_payload(30 if "/runs/2/" in cmd[2] else 10))
        if cmd[2].endswith("/artifacts?per_page=100"):
            return _proc(artifacts)
        run_id = cmd[3]
        result: MagicMock = _fake_download({"junit-a": reports[run_id]})(cmd, **kwargs)
        return result

    with (
        patch(WHICH, return_value="gh"),
        patch(RUN_GH, side_effect=gh),
        patch.object(ci, "REPO_ROOT", tmp_path),
    ):
        _run_task(run="2", compare="1", tests=True)
    out = capsys.readouterr().out
    assert "+20.0s" in out
    assert "t::slow" in out
    assert "+6.0s" in out
    assert list((tmp_path / "tmp").iterdir()) == []


def test_task_no_junit_artifacts_exits(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    def gh(cmd: list[str], **_: object) -> MagicMock:
        if cmd[:3] == ["gh", "auth", "status"]:
            return _proc()
        if "/jobs?" in cmd[2]:
            return _proc(_jobs_payload(10))
        return _proc(json.dumps({"artifacts": []}))

    with (
        patch(WHICH, return_value="gh"),
        patch(RUN_GH, side_effect=gh),
        patch.object(ci, "REPO_ROOT", tmp_path),
        pytest.raises(SystemExit) as exc,
    ):
        _run_task(run="2", compare="1", tests=True)
    assert exc.value.code == 1
    assert "no junit-* artifacts" in capsys.readouterr().out

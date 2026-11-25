"""Tests for tools/junit_summary.py (#1329)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.junit_summary import TestResult, main, parse_junit, render_summary

CASES = """
<testcase classname="tests.test_a" name="test_ok" time="0.10"/>
<testcase classname="tests.test_a" name="test_bad" time="2.50"><failure message="x"/></testcase>
<testcase classname="tests.test_b" name="test_err[a|b]" time="0.30"><error message="x"/></testcase>
<testcase classname="tests.test_b" name="test_skip" time="0.00"><skipped message="x"/></testcase>
"""


def _suite(tmp_path: Path, wrapped: bool) -> Path:
    suite = f'<testsuite name="pytest" tests="4">{CASES}</testsuite>'
    body = f"<testsuites>{suite}</testsuites>" if wrapped else suite
    path = tmp_path / "junit.xml"
    path.write_text(body, encoding="utf-8")
    return path


def test_parse_outcomes(tmp_path: Path) -> None:
    results = parse_junit(_suite(tmp_path, wrapped=False))
    assert [r.outcome for r in results] == ["passed", "failed", "error", "skipped"]
    assert results[1] == TestResult("tests.test_a::test_bad", 2.5, "failed")


def test_testsuites_wrapper_gives_same_results(tmp_path: Path) -> None:
    assert parse_junit(_suite(tmp_path, wrapped=True)) == parse_junit(
        _suite(tmp_path, wrapped=False)
    )


def test_summary_lists_only_failed_and_errored(tmp_path: Path) -> None:
    text = render_summary("T", parse_junit(_suite(tmp_path, wrapped=False)))
    failed_part = text.split("**Failed tests**")[1].split("slowest")[0]
    assert "test_bad" in failed_part
    assert "test_err" in failed_part
    assert "test_ok" not in failed_part
    assert "test_skip" not in failed_part


def test_summary_without_failures() -> None:
    text = render_summary("T", [TestResult("a::b", 0.1, "passed")])
    assert "No failures." in text
    assert "**Failed tests**" not in text


def test_slowest_sorted_descending_and_capped() -> None:
    results = [TestResult(f"t::n{i}", float(i), "passed") for i in range(15)]
    text = render_summary("T", results, slowest=10)
    rows = [line for line in text.splitlines() if line.startswith("| `")]
    assert len(rows) == 10
    assert "n14" in rows[0]
    assert "n5" in rows[-1]


def test_pipe_in_node_id_is_escaped() -> None:
    text = render_summary("T", [TestResult("t::n[a|b]", 1.0, "passed")])
    assert "n[a\\|b]" in text


def test_main_appends_to_step_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    summary = tmp_path / "summary.md"
    summary.write_text("existing\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert main([str(_suite(tmp_path, wrapped=False)), "--title", "My title"]) == 0
    content = summary.read_text(encoding="utf-8")
    assert content.startswith("existing\n")
    assert "### My title" in content


def test_main_prints_without_step_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfdbinary: pytest.CaptureFixture[bytes]
) -> None:
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert main([str(_suite(tmp_path, wrapped=False))]) == 0
    assert b"### Test results" in capfdbinary.readouterr().out


def test_main_missing_report_returns_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert main([str(tmp_path / "missing.xml")]) == 0
    assert "No report" in summary.read_text(encoding="utf-8")


def test_main_malformed_report_returns_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bad = tmp_path / "bad.xml"
    bad.write_text("<testsuite><oops", encoding="utf-8")
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert main([str(bad)]) == 0
    assert "No report" in summary.read_text(encoding="utf-8")

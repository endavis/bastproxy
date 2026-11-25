#!/usr/bin/env python3
"""Write the failed and the slowest tests of a JUnit XML report as a Markdown summary.

CI runs this after pytest, with ``--junitxml``, so a run's page lists the failures and the
slowest tests without opening the log (#1329). The summary is appended to the file named by
``GITHUB_STEP_SUMMARY``, or printed when that variable is unset.

Usage:
    python tools/junit_summary.py <report.xml> [--title TITLE]

A missing or malformed report writes a "no report" line and exits 0: the summary must never
fail a job, and the pytest step already reports the real failure.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree  # nosec B405  # parses only pytest's own report

SLOWEST_COUNT = 10


@dataclass(frozen=True)
class TestResult:
    """One test case from a JUnit report."""

    __test__ = False  # not a pytest test class, despite the name

    node_id: str
    seconds: float
    outcome: str  # "passed", "failed", "error" or "skipped"


def _outcome(case: ElementTree.Element) -> str:
    """Return the outcome of a ``<testcase>`` element."""
    if case.find("failure") is not None:
        return "failed"
    if case.find("error") is not None:
        return "error"
    if case.find("skipped") is not None:
        return "skipped"
    return "passed"


def parse_junit(path: Path) -> list[TestResult]:
    """Parse a JUnit XML report; a ``<testsuite>`` or ``<testsuites>`` root both work.

    Raises:
        OSError: the file cannot be read.
        ElementTree.ParseError: the file is not well-formed XML.
    """
    root = ElementTree.parse(path).getroot()  # nosec B314  # pytest's own report
    results: list[TestResult] = []
    for case in root.iter("testcase"):
        classname = case.get("classname", "")
        name = case.get("name", "")
        node_id = f"{classname}::{name}" if classname else name
        try:
            seconds = float(case.get("time", "0"))
        except ValueError:
            seconds = 0.0
        results.append(TestResult(node_id, seconds, _outcome(case)))
    return results


def _cell(text: str) -> str:
    """Escape ``|`` so a test ID cannot break a Markdown table."""
    return text.replace("|", "\\|")


def render_summary(title: str, results: list[TestResult], slowest: int = SLOWEST_COUNT) -> str:
    """Render the failed tests and the ``slowest`` slowest tests as Markdown."""
    lines = [f"### {title}", ""]
    counts = {
        o: sum(1 for r in results if r.outcome == o)
        for o in ("passed", "failed", "error", "skipped")
    }
    lines.append(
        f"{len(results)} tests: {counts['passed']} passed, {counts['failed']} failed, "
        f"{counts['error']} errored, {counts['skipped']} skipped."
    )
    lines.append("")
    bad = [r for r in results if r.outcome in ("failed", "error")]
    if bad:
        lines.extend(["**Failed tests**", ""])
        lines.extend(f"- `{_cell(r.node_id)}` ({r.outcome})" for r in bad)
    else:
        lines.append("No failures.")
    lines.append("")
    ranked = sorted(results, key=lambda r: r.seconds, reverse=True)[:slowest]
    if ranked:
        lines.extend(
            [f"**{len(ranked)} slowest tests**", "", "| Test | Seconds |", "| :--- | ---: |"]
        )
        lines.extend(f"| `{_cell(r.node_id)}` | {r.seconds:.2f} |" for r in ranked)
        lines.append("")
    return "\n".join(lines)


def _write(text: str) -> None:
    """Append ``text`` to ``GITHUB_STEP_SUMMARY``, or print it when that is unset."""
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if target:
        with Path(target).open("a", encoding="utf-8") as handle:
            handle.write(text + "\n")
        return
    # Windows consoles default to cp1252; never crash on a character it lacks.
    sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))
    sys.stdout.buffer.flush()


def main(argv: list[str] | None = None) -> int:
    """Entry point; always returns 0 so the summary never fails a job."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="JUnit XML report written by pytest")
    parser.add_argument("--title", default="Test results", help="heading of the summary")
    args = parser.parse_args(argv)
    try:
        results = parse_junit(args.report)
    except (OSError, ElementTree.ParseError) as exc:
        _write(
            f"### {args.title}\n\n"
            f"No report: could not read `{args.report}` ({type(exc).__name__}).\n"
        )
        return 0
    _write(render_summary(args.title, results))
    return 0


if __name__ == "__main__":
    sys.exit(main())

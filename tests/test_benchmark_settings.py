"""The project's benchmark settings must reach pytest-benchmark (#879).

The plugin reads its settings only from command-line flags. They used to sit in a
`[tool.pytest-benchmark]` table that nothing read, so every run had GC on and no warmup
although the config said otherwise. They now live in `addopts`. The first test runs a real
benchmark to prove they arrive; the second keeps the dead table from coming back.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = "tests/benchmarks/test_bench_persistentdict.py::test_bench_convert_keys_to_int_flat"
# The child would inherit these from this run. Under xdist, PYTEST_XDIST_WORKER makes
# pytest-benchmark disable itself and refuse --benchmark-only, as PYTEST_ADDOPTS with -n
# would; under pytest-cov, COV_CORE_* would add the child's lines to this run's coverage.
INHERITED_FROM_THIS_RUN = ("PYTEST_XDIST_", "PYTEST_ADDOPTS", "COV_CORE_")


def test_an_enabled_benchmark_run_gets_the_project_settings(tmp_path: Path) -> None:
    report = tmp_path / "benchmark.json"
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(INHERITED_FROM_THIS_RUN)
    }
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            BENCHMARK,
            "--benchmark-enable",
            "--benchmark-only",
            "--benchmark-max-time=0.05",
            f"--benchmark-json={report}",
            "-p",
            "no:cacheprovider",
            "-q",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    options = json.loads(report.read_text(encoding="utf-8"))["benchmarks"][0]["options"]
    assert options["disable_gc"] is True
    # The warmup iteration count when warmup is on, False when it is off.
    assert options["warmup"]


def test_there_is_no_benchmark_settings_table() -> None:
    """pytest-benchmark never reads `[tool.pytest-benchmark]`, so settings there do nothing."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "pytest-benchmark" not in pyproject.get("tool", {})

"""Tests for the same-runner benchmark gate on pull requests (#439).

The workflow wiring is read from the YAML. The script runs for real inside a
throwaway git repository, with ``uv`` replaced by a stub that records each call,
so the assertions are on what the script does, not on how it is spelled.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).parent.parent
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "benchmark.yml"
SCRIPT_PATH = ROOT / ".github" / "scripts" / "benchmark_vs_base.sh"
TEST_FILE = "tests/benchmarks/test_bench_networkdataline.py"

# Records "<cwd> | <BENCH_ABSOLUTE_GATE> | <args>" per call; $STUB_FAIL_ON names a
# substring of the arguments that makes the call exit 1.
_UV_STUB = """\
#!/bin/bash
args="$*"
echo "$PWD | ${BENCH_ABSOLUTE_GATE:-unset} | ${args//$'\n'/ }" >> "$STUB_CALLS"
if [ -n "${STUB_FAIL_ON:-}" ] && [[ "$*" == *"$STUB_FAIL_ON"* ]]; then
  exit 1
fi
exit 0
"""

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="the script runs under bash on Linux; the Windows runner has no usable bash",
)


def _workflow() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    return data


def _steps() -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = _workflow()["jobs"]["benchmark"]["steps"]
    return steps


def _step(name: str) -> dict[str, Any]:
    found = [s for s in _steps() if s.get("name") == name]
    assert len(found) == 1, f"expected one step named {name!r}, found {len(found)}"
    return found[0]


class TestWorkflowWiring:
    """The benchmark workflow gates pull requests against their base."""

    def test_checkout_fetches_the_base_parent(self) -> None:
        checkout = _steps()[0]
        assert checkout["uses"].startswith("actions/checkout@")
        assert checkout["with"]["fetch-depth"] == 2

    def test_absolute_gate_is_report_only_for_pull_requests(self) -> None:
        expr = _step("Run benchmarks")["env"]["BENCH_ABSOLUTE_GATE"]
        assert "github.event_name == 'pull_request'" in expr
        assert "'report'" in expr
        assert "'enforce'" in expr

    def test_compare_step_runs_only_on_pull_requests_against_first_parent(self) -> None:
        step = _step("Compare benchmarks with the base")
        assert "github.event_name == 'pull_request'" in step["if"]
        assert step["run"].strip() == ".github/scripts/benchmark_vs_base.sh HEAD^1"

    def test_no_write_permission_is_reachable_from_the_benchmark_job(self) -> None:
        workflow = _workflow()
        assert workflow["permissions"] == {"contents": "read"}
        assert workflow["jobs"]["benchmark"]["permissions"] == {"contents": "read"}


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repo with a base commit and a head commit that edits the benchmark file."""
    repo = tmp_path / "repo"
    (repo / "tests" / "benchmarks").mkdir(parents=True)
    (repo / TEST_FILE).write_text("# base\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base", "--no-gpg-sign")
    (repo / TEST_FILE).write_text("# head\n", encoding="utf-8")
    _git(repo, "commit", "-qam", "head", "--no-gpg-sign")
    return repo


def _run(
    tmp_path: Path,
    repo: Path,
    args: list[str],
    env: dict[str, str] | None = None,
    stub: str = _UV_STUB,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    uv = bin_dir / "uv"
    uv.write_text(stub, encoding="utf-8")
    uv.chmod(uv.stat().st_mode | stat.S_IEXEC)
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir(exist_ok=True)
    calls = tmp_path / "calls.txt"
    result = subprocess.run(
        ["bash", str(SCRIPT_PATH), *args],
        cwd=repo,
        env={
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "HOME": str(tmp_path),
            "RUNNER_TEMP": str(runner_temp),
            "STUB_CALLS": str(calls),
            **(env or {}),
        },
        capture_output=True,
        text=True,
        timeout=30,
    )
    lines = calls.read_text(encoding="utf-8").splitlines() if calls.exists() else []
    return result, lines


def _leftovers(tmp_path: Path, repo: Path) -> None:
    assert list((tmp_path / "runner-temp").iterdir()) == []
    assert "worktree" not in _git(repo, "worktree", "list").replace(str(repo), "")


class TestScript:
    """benchmark_vs_base.sh benchmarks the base in its own worktree, then the head."""

    def test_success_syncs_and_benchmarks_base_then_compares_in_root(
        self, tmp_path: Path, repo: Path
    ) -> None:
        result, calls = _run(tmp_path, repo, ["HEAD^1"])
        assert result.returncode == 0, result.stderr
        sync, guard, save, compare = calls
        base_dir = sync.split(" | ")[0]
        assert base_dir != str(repo.resolve())
        assert sync.endswith("| sync --frozen --all-extras")
        assert guard.split(" | ")[0] == base_dir
        assert " run python " in guard
        assert save.split(" | ")[0] == base_dir
        assert "--benchmark-save=base" in save
        assert compare.split(" | ")[0] == str(repo.resolve())
        assert "--benchmark-compare-fail=median:25%" in compare
        assert "--benchmark-compare" in compare
        assert all(" | report | " in c for c in calls)
        assert "networkdataline_create or networkdataline_attribute_change" in save
        assert "networkdataline_create or networkdataline_attribute_change" in compare
        _leftovers(tmp_path, repo)

    def test_head_benchmark_file_is_what_the_base_pass_runs(
        self, tmp_path: Path, repo: Path
    ) -> None:
        seen = tmp_path / "seen.txt"
        # Wrap the stub so the pytest call records the test file it would run.
        wrapper = (
            "#!/bin/bash\n"
            f'if [[ "$*" == *"--benchmark-save=base"* ]]; then cat {TEST_FILE} > "{seen}"; fi\n'
            + _UV_STUB.split("\n", 1)[1]
        )
        result, _ = _run(tmp_path, repo, ["HEAD^1"], stub=wrapper)
        assert result.returncode == 0, result.stderr
        assert seen.read_text(encoding="utf-8") == "# head\n"

    def test_head_failure_propagates_and_cleans_up(self, tmp_path: Path, repo: Path) -> None:
        result, calls = _run(
            tmp_path, repo, ["HEAD^1"], {"STUB_FAIL_ON": "--benchmark-compare-fail"}
        )
        assert result.returncode != 0
        assert len(calls) == 4
        _leftovers(tmp_path, repo)

    def test_guard_failure_aborts_before_any_benchmark(self, tmp_path: Path, repo: Path) -> None:
        result, calls = _run(tmp_path, repo, ["HEAD^1"], {"STUB_FAIL_ON": "run python"})
        assert result.returncode != 0
        assert not any(" | run pytest " in c for c in calls)
        _leftovers(tmp_path, repo)

    def test_no_argument_exits_2(self, tmp_path: Path, repo: Path) -> None:
        result, calls = _run(tmp_path, repo, [])
        assert result.returncode == 2
        assert "usage" in result.stderr
        assert calls == []

    def test_unknown_ref_exits_nonzero_without_running_uv(self, tmp_path: Path, repo: Path) -> None:
        result, calls = _run(tmp_path, repo, ["no-such-ref"])
        assert result.returncode != 0
        assert "unknown base ref" in result.stderr
        assert calls == []

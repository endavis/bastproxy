#!/usr/bin/env bash
# Project: bastproxy (#439)
#
# Gate the NetworkDataLine benchmarks against a base ref on the same machine.
#
#   .github/scripts/benchmark_vs_base.sh <base-ref>
#
# Runs the two gated benchmarks in a worktree of <base-ref> (its own
# `uv sync --frozen --all-extras` environment, so the base source is what gets
# imported), then runs them at the current checkout and fails when the median is
# more than 25% slower. The head's benchmark test file is copied over the base's
# so both sides time identical benchmark code. The fixed limits in the test file
# are report-only here (BENCH_ABSOLUTE_GATE=report).
#
# This file is project-specific, not part of pyproject-template. See ADR-0006.
set -euo pipefail

if [ "$#" -ne 1 ] || [ -z "$1" ]; then
  echo "usage: $0 <base-ref>" >&2
  exit 2
fi
base_ref="$1"

TEST_FILE="tests/benchmarks/test_bench_networkdataline.py"
SELECT="networkdataline_create or networkdataline_attribute_change"
FAIL_THRESHOLD="median:25%"

root="$(git rev-parse --show-toplevel)"
git -C "$root" rev-parse --verify --quiet "${base_ref}^{commit}" >/dev/null || {
  echo "error: unknown base ref: $base_ref" >&2
  exit 2
}

work="$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/bench-vs-base.XXXXXX")"
base_dir="$work/base"
# pytest-benchmark prints its storage path relative to the cwd when the two runs
# machine info differs, and fails on a path outside it, so keep it under the root.
storage="$root/tmp/benchmark-vs-base-$$"

cleanup() {
  git -C "$root" worktree remove --force "$base_dir" >/dev/null 2>&1 || true
  git -C "$root" worktree prune >/dev/null 2>&1 || true
  rm -rf "$work" "$storage"
}
trap cleanup EXIT

export BENCH_ABSOLUTE_GATE=report

git -C "$root" worktree add --detach "$base_dir" "$base_ref" >/dev/null
cp "$root/$TEST_FILE" "$base_dir/$TEST_FILE"

echo "::group::Sync base environment ($base_ref)"
(cd "$base_dir" && uv sync --frozen --all-extras)
echo "::endgroup::"

# pytest puts the head's src first only in the head checkout; confirm the base
# environment imports the base source, or the two passes would time the same code.
(cd "$base_dir" && BASE_SRC="$base_dir/src" uv run python -c '
import importlib.util, os, sys
spec = importlib.util.find_spec("bastproxy")
origin = spec.origin if spec else None
base_src = os.path.realpath(os.environ["BASE_SRC"])
if not origin or not os.path.realpath(origin).startswith(base_src + os.sep):
    sys.exit(f"base pass would import bastproxy from {origin}, not {base_src}")
')

echo "::group::Benchmark base ($base_ref)"
(cd "$base_dir" && uv run pytest "$TEST_FILE" \
  --benchmark-enable --benchmark-only -k "$SELECT" \
  --benchmark-storage="$storage" --benchmark-save=base -v)
echo "::endgroup::"

echo "::group::Benchmark head, compared with base ($FAIL_THRESHOLD)"
(cd "$root" && uv run pytest "$TEST_FILE" \
  --benchmark-enable --benchmark-only -k "$SELECT" \
  --benchmark-storage="$storage" \
  --benchmark-compare --benchmark-compare-fail="$FAIL_THRESHOLD" -v)
echo "::endgroup::"

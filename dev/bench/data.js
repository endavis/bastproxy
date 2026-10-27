window.BENCHMARK_DATA = {
  "lastUpdate": 1793112487941,
  "repoUrl": "https://github.com/endavis/bastproxy",
  "entries": {
    "Benchmark": [
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "e257f3eae9411e8b7ac8da96db8852b469f14974",
          "message": "chore: synchronize infra with pyproject-template (merges PR #9)\n\nFirst of three PRs syncing to template main (d80ce96, 481 commits since\n2c1171b). This one covers infra; AI agent config and docs follow.\n\nTemplate improvements adopted:\n- pyproject: ruff PLW1514 (preview), mypy over src/tools/tests, pyright\n  LSP config, vulture, mutmut, commitizen bump/changelog settings,\n  branch coverage over bastproxy + tools with fail_under = 29 (measured\n  32.53%), dev/security deps bumped and extended (hypothesis,\n  pytest-benchmark, mutmut, pyyaml, mkdocstrings, cyclonedx-bom);\n  black and safety dropped\n- pytest.ini folded into pyproject (asyncio auto mode now in effect)\n- workflows: SHA-pinned actions, python-versions composite action;\n  new codeql, daily-check, ci-full-matrix, dependabot automerge and\n  blocked-label, benchmark, mutation; dependabot.yml enabled\n- tools/doit: all task modules updated; new install_tools, benchmark,\n  deadcode/complexity/maintainability/wheel_check/audit tasks\n- pre-commit: commit-msg hook type, actionlint, check-commit-issue-ref\n- template-sync skill and its reference docs, adr-template, completions\n- tests for the adopted tools, workflows and hooks (~1000 tests)\n\nbastproxy changes needed to pass the new gates:\n- export __version__ and ship a top-level py.typed (wheel_check)\n- explicit utf-8 encodings (PLW1514)\n- _version.py untracked and ignored (hatch-vcs generated)\n- examples/ removed (template leftovers that never ran)\n- lockfile bumps for CVEs: virtualenv, urllib3, certifi, idna, msgpack\n- vulture findings whitelisted pending review in #8\n\nPart of #7",
          "timestamp": "2026-10-27T14:47:13Z",
          "tree_id": "19934af42ac988b6c960fe939053e651b320d57d",
          "url": "https://github.com/endavis/bastproxy/commit/e257f3eae9411e8b7ac8da96db8852b469f14974"
        },
        "date": 1793112487241,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_persistentdict.py::test_bench_convert_keys_to_int_flat",
            "value": 2136.049296495526,
            "unit": "iter/sec",
            "range": "stddev: 0.00003912976030345475",
            "extra": "mean: 468.153989536025 usec\nrounds: 2198"
          },
          {
            "name": "tests/benchmarks/test_bench_persistentdict.py::test_bench_convert_keys_to_int_nested",
            "value": 1895.2388609134377,
            "unit": "iter/sec",
            "range": "stddev: 0.000011237447618202994",
            "extra": "mean: 527.637977789267 usec\nrounds: 1936"
          },
          {
            "name": "tests/benchmarks/test_bench_persistentdict.py::test_bench_convert_nested",
            "value": 3448.0127353786984,
            "unit": "iter/sec",
            "range": "stddev: 0.000007479476796174777",
            "extra": "mean: 290.0221306433687 usec\nrounds: 3544"
          }
        ]
      }
    ]
  }
}
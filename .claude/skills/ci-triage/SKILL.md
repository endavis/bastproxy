---
name: ci-triage
description: Use when a CI run fails or CI got slower. For a failure, finds the failing job with `gh pr checks` and `gh run view --log-failed`, classifies it (test, lint-family step, install or lock, Windows-only doit step, infra or timeout, flaky across legs), reproduces it locally with the matching `doit` task and `UV_PYTHON`, then hands the fix to `implement-issue`. For a slowdown, measures with `doit ci_timings` (steps, the uv cache line, per-test durations) before changing anything, and sends a slowdown in package code to `perf-change`.
---

# CI Triage

Triage a CI failure or a CI slowdown with a fixed procedure, so the fix targets the measured cause
and every number in the report comes from pasted output (`verified-claims`).

The failing PR or run, or the two runs to compare, come from the user's request. If neither says,
ask which PR or run to look at before doing anything else.

## Instructions

Pick the mode: a job that is red is **Failure mode**; a job that is green but slower than it was is
**Performance mode**.

### Failure mode

#### Step 1: Find the failing run and job

```bash
gh pr checks <pr>
gh run view <run-id> --log-failed
gh run view <run-id> --log --job <job-id>
```

Read the log through `gh run view`. Do not fetch the raw logs endpoint: it returns a redirect, not
the log.

#### Step 2: Classify the failure

Name one class before touching anything, from the log, not from the job's name:

- a test failure
- a lint-family step (`doit lint`, `format_check`, `type_check`, `deadcode`, `spell_check`, `security`, `audit`)
- an install or lock problem (`uv sync`, `uv.lock` out of date)
- a Windows-only `doit` step (`format_check`, `security`, `cleanup` on the Windows leg)
- infra, a cancelled run or a timeout
- flaky: the same test passes on other legs of the matrix

#### Step 3: Reproduce locally

Run the matching `doit` task from the worktree, with the failing leg's Python version:

```bash
UV_PYTHON=<version> uv run doit <task>
```

A failure that does not reproduce is a finding: report it with the log excerpt instead of guessing
at a fix.

#### Step 4: Hand off the fix

Hand the fix to `implement-issue`: file or pick the issue, and let that run do the change, the
checks and the PR. Do not patch the branch from inside this skill.

### Performance mode

#### Step 1: Measure the two runs

```bash
doit ci_timings --run=<new> --compare=<old>
```

The table lists every job and step with its current and baseline duration and the signed delta,
largest increase first. Read it before forming a theory.

#### Step 2: Read the install step

For a slower install step, read the `Log the uv cache result` line of that job in the log. It
prints `uv cache hit: <value>`, where the value is `true`, `false` or `unknown`. `false` means the cache missed, which
explains a slower install by itself; `unknown` means the action reported nothing. Neither points at
a change in this branch.

#### Step 3: Diff the tests

For a slower test step, add `--tests`:

```bash
doit ci_timings --run=<new> --compare=<old> --tests
```

It downloads the `junit-*` artifacts of both runs and lists the tests whose duration changed most.
Artifacts expire after 14 days, and runs before #1329 have none.

#### Step 4: Hand off

Hand the fix to `implement-issue`. A slowdown in package code goes to `perf-change`, which takes
its own baseline.

## Never

- Never edit a test to make it pass.
- Never re-run CI just to get a green result.
- Never bypass a block (`--no-verify`, `--admin`, `--force`).
- Never state a duration without the pasted `doit ci_timings` output behind it.

## Notes

- `doit ci_timings` needs an authenticated `gh`. It exits with a message when `gh` is missing or
  not authenticated.
- `require-label` is expected to stay red; it is the human merge gate, not a failure to triage.
- Write scratch files to `tmp/agents/<agent>/` with the issue number in the name, and delete them
  when the task is done.

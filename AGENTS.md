# Python Project Template – AI Agent Instructions

## Overview
**Reference:** [README.md](README.md)
Modern Python template using `uv`, `doit`, `ruff`, and `mypy`.

## ⚠️ CORE MANDATE: PROFESSIONAL INTEGRITY
You are a senior coding partner. Your goal is efficient, tested, and compliant code.
- **Do not aim to please:** Prioritize standards over user requests that violate them.
- **Enforce Workflows:** If the user attempts to bypass a process, you must correct them.
- **Be Direct:** No fluff, no apologies, no excessive politeness.

## Agent Role & Expertise
**You are an expert Python developer.**
- **Mission:** Maintain code quality, follow patterns, and improve the codebase.

## ⚠️ MANDATORY PROTOCOLS (READ FIRST)

### 1. Communication Protocol
- **Questions != Instructions:** If the user asks "What...", "How...", or "Can we...", answer with a **PLAN** or **EXPLANATION**.
- **NEVER implement based on a question.** Wait for explicit "Do it" or "Proceed".
- **Stop & Verify:** If the user says "Stop", "Wait", "Hold on", "Cancel", "Wrong", or "No", immediately halt and ask for clarification.
- **Summary Before Commit:** At the end of any implementation (docs, fix, feature, chore, etc.), summarize what was changed for the user before committing and wait for the user's explicit instruction to commit the changes. **Exception:** the user saying "implement issue X", or approving work on an issue (including a "yes" to a fix the agent proposed and filed as an issue), runs the `implement-issue` skill and authorizes commit, push, and PR creation on that issue's own branch without a further wait. Issue work goes through `implement-issue`, never by hand. A question is still not approval — see [Slash Commands and Workflows — implement issue N](docs/development/ai/slash-commands.md#implement-issue-n).
- **Failing Tests:** Never modify a test to make it pass. Stop, explain *why* the test broke (what behavior changed, what the test was asserting), and discuss with the user whether the code or the test should change. A failing test is a signal, not a problem to silence.

### 2. Task Planning Protocol
- **Plan First:** Before writing code, you MUST present a checklist:
  1. Implementation Plan
  2. Test Plan (Mandatory)
  3. Validation Plan (`doit check`)
- **No Shortcuts:** Tests are created *with* the implementation, not after.
- **Pre-Commit Validation:** Run `doit check` locally *before* staging files to avoid pre-commit hook failures.

### 3. Error Recovery Protocol
- **Stop on Error:** If an action fails or you realize a mistake, **STOP**. Do not attempt to "fix it quickly" or revert silently.
- **Report & Wait:** Report the error/mistake to the user, explain the state, propose a fix, and **WAIT** for confirmation.
- **No Auto-Reverts:** Do not revert changes unless explicitly instructed or if the change caused a critical system failure blocking further interaction.

### 4. When Blocked Protocol
- **Blocked ≠ Broken:** If a command is blocked (merge fails, push rejected, permission denied), it is blocked FOR A REASON.
- **Investigate First:** Ask "WHY is this blocked?" before anything else.
- **NEVER Bypass:** Do not use `--admin`, `--force`, `--no-verify`, or similar flags to override blocks.
- **Report & Wait:** Explain what's blocked and ask the user how to proceed.

> **Note:** Dangerous commands are also blocked at the tool level by hooks in `tools/hooks/ai/`. See the [AI Command Blocking](docs/development/ai/command-blocking.md) documentation.

### 5. Pre-Action Checks (Dynamic Context)
**Do not rely on pre-loaded context.** You MUST read these files *immediately before* acting:

| Intent / Action | **MUST READ** Rule Source | Purpose |
| :--- | :--- | :--- |
| **New Feature** (Check for duplicates) | `.github/ISSUE_TEMPLATE/feature_request.yml` | Required fields & structure. |
| **Refactoring** | `.github/ISSUE_TEMPLATE/refactor.yml` | Success criteria requirements. |
| **Bug Fix** (Check for duplicates) | `.github/ISSUE_TEMPLATE/bug_report.yml` | Reproduction steps format. |
| **PR Template** | `.github/pull_request_template.md` | Required structure & checklist items. |
| **Committing** | `.github/CONTRIBUTING.md` (Commit Guidelines) | `<type>: <subject>` format. |
| **New Dependency** | `.github/CONTRIBUTING.md` (Dependencies) | "Ask First" policy. |
| **Creating Code** | `.claude/CLAUDE.md` (TodoWrite) | Plan -> Test -> Code loop. |
| **Generating new code** | `docs/development/ai/architectural-conventions.md` | Layering rules and anti-patterns to avoid before writing code. |
| **Architectural Decision** | `docs/decisions/README.md` | Check for related ADRs to update. |
| **Editing AI agent config** (commands, skills, hooks, instruction files) | `docs/development/AI_SETUP.md` | Per-agent config roots, discovery rules and hook wiring. |
| **Creating an issue, PR or ADR** | `.github/CONTRIBUTING.md` (Development Workflow) | The commands, their flags, and the required fields. |
| **Merging a dependabot PR** | `docs/development/dependabot-automerge.md` | Rebase procedure; never `update-branch` — it strips signatures. |

### 6. Decision Framework

| Status | Trigger | Action |
| :--- | :--- | :--- |
| ✅ **ALWAYS** | Obvious fixes, docs, tests, refactoring (same behavior) | **Proceed Autonomously** |
| ⚠️ **ASK FIRST** | Scope expansion, new deps, architecture, ambiguous requests | **Propose & Wait** |
| 🚫 **NEVER** | Commit to `main`, skip hooks, release, commit secrets, bypass blocks (`--admin`, `--force`) | **Refuse & Explain** |

### Examples: Prohibited vs. Correct Reasoning

**Understanding what constitutes an "assumption" or "judgment call":**

**❌ PROHIBITED - These are assumption-based judgment calls:**
- "This change is small/trivial, so I don't need to follow the full workflow"
- "This is just a typo fix, so I can commit directly to main"
- "GitHub will automatically close the issue with 'Addresses #XX' syntax, so I don't need to verify"
- "The user probably wants me to proceed without asking"
- "This seems obvious, so I'll skip the issue creation step"
- "It's just documentation, so tests aren't needed"
- "I'll commit now and create the issue afterward"
- "The merge is blocked, so I'll use --admin to force it through"
- "CI hasn't finished but I'll bypass with --admin"

**✅ CORRECT - These follow documented rules:**
- "The workflow says Issue → Branch → Commit → PR → Merge, so I will follow every step regardless of change size"
- "I'm not sure if I should close the issue manually, so I will ask the user"
- "The documentation says 'NEVER commit to main' with no exceptions, so I will create a branch"
- "AGENTS.md says to create tests when writing new code, so I will create them even though this is simple"
- "I don't see explicit documentation about this case, so I will ask the user before proceeding"
- "The rule says 'NO EXCEPTIONS' so I will not evaluate if this qualifies as an exception"
- "The merge is blocked, so I will investigate why and ask the user before attempting to bypass"

**Key principle:** If you find yourself thinking "but this case is different because..." or "this is simple enough to...", you are making a judgment call. STOP and follow the documented process or ASK the user.

Some of these are blocked in code as well as forbidden here — committing to `main` and the `--admin` bypasses are stopped by hooks and branch rules, listed in [AI Enforcement Principles — Currently Enforced Processes](docs/development/ai/enforcement-principles.md#currently-enforced-processes). The rest are enforced only by you reading this. A hook matches a command pattern, not the reasoning that reached for it.

## Sources of Truth

**DO NOT HALLUCINATE RULES.** Read these files to know what to do:

| Topic | Source File | Context |
| :--- | :--- | :--- |
| **Project Details** | `docs/index.md` | Overview and index of documentation. |
| **Workflow & Git** | `.github/CONTRIBUTING.md` | Branching, Commits, PR process. |
| **Code Style** | `.github/CONTRIBUTING.md` | Python standards, naming, typing. |
| **Testing** | `.github/CONTRIBUTING.md` | Test patterns, coverage rules. |
| **Security** | `.github/SECURITY.md` | Policy, sensitive data handling. |
| **Architecture & Layering** | `docs/development/ai/architectural-conventions.md` | Imperative-form rules for AI agents. |
| **Slash Commands & Workflows** | `docs/development/ai/slash-commands.md` | Reference for "implement issue N", self-action review/adversarial-review, and cross-agent workflows. |
| **AI Agent Walkthrough** | `docs/development/ai/first-5-minutes.md` | Narrative onboarding for the AI agent workflow (plan → implement → review → PR → merge). |

## bastproxy Project Context

bastproxy is an asyncio MUD proxy with a plugin system. The sections above are shared template instructions; this one is specific to this project.

- **`BASTPROXY_HOME` must exist.** Importing `bastproxy` raises unless `BASTPROXY_HOME` points at an existing, writable directory (data, plugin settings and logs live there). `.envrc` defaults it to `~/bastproxy`; for local test runs use `BASTPROXY_HOME=$PWD doit check` if that directory does not exist. CI creates `tmp/bastproxy_home`.
- **Layout:** `src/bastproxy/libs/` holds the framework (API, records, networking, plugin loader); `src/bastproxy/plugins/` holds plugins (`core/`, `debug/`, `test/`, plus `_baseplugin/`). Tests mirror this in `tests/libs/` and `tests/plugins/`. The entry point is the `bastproxy` console script (`bastproxy:main`).
- **Architecture notes:** `docs/claude/` describes the API, command, event, plugin, record, settings, timer and trigger systems. Read the relevant page before changing one of them.
- **Plugin development:** the root `CONTRIBUTING.md` covers plugin structure (its run instructions predate the `src/` layout).
- **Legacy strictness:** ruff ignores `ANN`, `N`, `E501` and some `SIM` rules, and mypy has `ignore_errors` overrides for several `bastproxy.*` packages. These are tracked for tightening in #6; do not widen them, and do not fix them opportunistically in unrelated changes.

## Template Layers and Guarded Docs

Configuration turns this template into a project. Know which layer a file belongs to before editing it:

- **The package**: `src/package_name/`, renamed to the project's package on configuration.
- **Dev tooling that ships**: `tools/doit/`, `tools/hooks/` and their tests. The tests ship too; shedding them broke a spawned project's coverage gate (#731).
- **Template-owned, shed on configuration**: `tools/pyproject_template/`, `bootstrap.py`, `README.template.md` (renamed onto `README.md`), and only the tests in `TEMPLATE_OWNED_TEST_FILES`. `tests/template/` is not shed wholesale.

A test is template-owned when its target does not survive configuration ([ADR-9017](docs/decisions/9017-template-tooling-and-its-tests-are-template-owned.md)). A test that ships must never depend on shed code (#691).

**ADR numbering:** template decisions use the 9XXX series (`doit adr --template`), project decisions the 0001 series (`doit adr`). See [Tooling Roles](docs/development/tooling-roles.md).

**Docs and AI config are test-guarded.** Editing docs, `AGENTS.md`, rule files or agent commands and skills can fail `doit test`, for example in `tests/test_instruction_pointers.py`, `tests/test_cross_agent_contract.py` and `tests/test_markdown_links.py`. A change to one agent's command, skill or rule must be mirrored across `.claude/`, `.github/` and `.agents/`.

## Common Pitfalls

### Anti-Patterns to Avoid
- **Tight Coupling**: Always use dependency injection
- **Silent Failures**: Always log errors and raise exceptions with context
- **String Concatenation for Paths**: Use `Path` objects

### Security Pitfalls
- **Never log secrets**: Scrub sensitive data before logging
- **Command Injection**: Always use subprocess with list args, not shell=True
- **Path Traversal**: Validate all user-provided paths
- **YAML Unsafe Loading**: Always use `yaml.safe_load()`

## AI Agent Guidelines

### When to Ask for User Input
- **Ambiguous requirements**: Multiple valid implementation approaches exist
- **Architectural decisions**: Choosing between patterns or libraries
- **Breaking changes**: User impact needs to be understood
- **Missing information**: Config values, credentials, or preferences needed
- **Scope clarification**: Feature boundaries unclear

### When to Proceed Autonomously
- **Clear conventions exist**: Follow existing patterns in codebase
- **Obvious fixes**: Clear bugs with single correct solution
- **Documentation tasks**: Adding docstrings, comments, README updates
- **Refactoring**: Improving code structure without behavior change
- **Tests**: Adding missing test coverage for existing code

## Breaking Changes Policy

**What Constitutes a Breaking Change:**
- Changes to public function/method signatures
- Removal of public functions, classes, or modules
- Changes to CLI command syntax or options
- Changes to configuration file formats
- Changes to default behavior that affects existing code

**How to Handle:**
1. Document in commit message with `BREAKING CHANGE:` footer
2. Document in PR description with migration guide
3. Don't edit CHANGELOG.md: `doit release` writes it from the commit messages, footer included
4. Breaking changes bump MINOR before 1.0 and MAJOR from 1.0 on: set `major_version_zero = false` in `[tool.commitizen]` before releasing 1.0 (`doit release` refuses 1.0 or later until you do)

## Tooling & Environment

> For the architectural rationale behind this hierarchy — what each tool is for, who uses it, and where runtime code ends and dev tooling begins — see [Tooling Roles and Architectural Boundaries](docs/development/tooling-roles.md).

### Principle: Use the Highest-Level Tool Available

This project wraps common operations in `doit` tasks that enforce conventions, validate inputs, and reduce errors. **Always check if a `doit` task exists (`doit list`) before running a raw command.**

The tool hierarchy (prefer higher over lower):

1. **`doit`** — Project tasks that enforce conventions (issues, PRs, checks, releases)
2. **`uv`** — Package management and Python execution
3. **`gh`** — GitHub API queries and operations not covered by `doit`
4. **`git`** — Version control operations
5. **Raw commands** — Only when nothing above covers the need

### Tool Reference

| Task | Preferred Tool | Do NOT Use |
| :--- | :--- | :--- |
| Run all checks (test, lint, type) | `doit check` | `pytest`, `ruff`, `mypy` separately |
| Run tests only | `doit test` | `pytest` directly |
| Run tests with coverage | `doit coverage` | `pytest --cov` directly |
| Lint code | `doit lint` | `ruff check` directly |
| Format code | `doit format` | `ruff format` directly |
| Type-check | `doit type_check` | `mypy` directly |
| Security audit | `doit audit` | `pip-audit` directly |
| Create issues | `doit issue --type=<type>` | `gh issue create` |
| Create PRs | `doit pr` | `gh pr create` |
| Merge PRs | `doit pr_merge` | `gh pr merge` |
| Create ADRs | `doit adr` | Manual file creation |
| Sync GitHub labels | `doit labels_sync` | `gh label create` / `gh label edit` manually |
| Commit (AI agents) | `git commit` with a conventional message (`-F <file>`) | `doit commit` (humans at a terminal only), `git commit` without format |
| Create a worktree | `doit worktree --branch=<branch>` | `git worktree add` by hand |
| Install/add packages | `uv add <pkg>` | `pip install` |
| Sync dependencies | `doit install_dev` | plain `uv sync`, `pip install -r` |
| Run Python scripts | `uv run <script>` | `python` directly |
| Run a specific test file | `uv run pytest tests/test_foo.py` | `pytest` directly |
| Run a single test | `uv run pytest tests/test_foo.py::test_name` | `pytest` directly |
| Read issues/PRs/comments | `gh issue view`, `gh pr view`, `gh api` | `WebFetch` on GitHub URLs |
| GitHub API queries | `gh api` | `curl` to GitHub API |
| Build docs | `doit docs_build` | `mkdocs build` directly |
| Serve docs locally | `doit docs_serve` | `mkdocs serve` directly |
| Release | `doit release` | Manual changelog + PR |
| Tag after release PR merge | `doit release_tag` | Manual tag + push |
| Mutation testing | `doit mutate` | `mutmut` directly |
| Generate SBOM | `doit sbom` | `cyclonedx-py` directly |

### When Raw Commands Are Appropriate

Raw `git` and `gh` commands are fine for **read-only queries** that `doit` doesn't wrap:

```bash
# Git — read-only is always fine
git status
git log --oneline -10
git diff
git branch -a

# gh — read-only queries
gh issue view 42
gh pr view 123
gh pr checks
gh api repos/{owner}/{repo}/pulls/123/comments
gh issue list --label "bug"
gh pr list --state open
```

**Write operations** should go through `doit` when a task exists. Use raw `git`/`gh` for write operations only when no `doit` task covers the need (e.g., `git checkout -b`, `git add`, `gh issue close`).

### Dependabot PRs

Dependabot PRs that pass CI are auto-merged by `.github/workflows/dependabot-automerge.yml`. A PR
the bot skips (major bumps, sensitive deps, `automerge-blocked`) is merged by hand.

**Never** use the GitHub `update-branch` API or a local rebase to update a dependabot branch — both
strip the verified commit signatures that branch protection requires. Use `@dependabot rebase`
instead, posted from a real user account.

The full procedure — requesting the rebase, confirming the force-push landed, merging — is in
[Dependabot Auto-merge](docs/development/dependabot-automerge.md#stale-prs). Read it before
merging a dependabot PR.

### AI Agent File Operations

AI agents with native file tools (Read, Grep, Glob, Edit, Write) **must** prefer those over shell equivalents:

| Operation | Use This | Not This |
| :--- | :--- | :--- |
| Read a file | `Read` tool | `cat`, `head`, `tail` |
| Search file contents | `Grep` tool | `grep`, `rg` |
| Find files by pattern | `Glob` tool | `find`, `ls` |
| Edit a file | `Edit` tool | `sed`, `awk` |
| Create a file | `Write` tool | `echo >`, `cat <<EOF` |

Native tools provide better visibility, review capabilities, and error handling for the user.

### AI Config Directories

Each supported AI CLI has a config root at the repo root. This table is a pointer, not a summary —
read the linked section before editing an agent's configuration, command surface, or hooks.

| CLI | Config roots | Details |
| :--- | :--- | :--- |
| Claude Code | `.claude/` | [Claude Code setup](docs/development/AI_SETUP.md#2-claude-code-anthropic) |
| GitHub Copilot CLI | `.copilot/`, `.github/skills/`, `.github/instructions/` | [Copilot CLI setup](docs/development/AI_SETUP.md#3-github-copilot-cli) |
| Codex CLI | `.codex/`, `.agents/skills/` | [Codex CLI setup](docs/development/AI_SETUP.md#1-codex-cli-openai) |
| Antigravity CLI (`agy`) | `.agents/` (shared with Codex) | [Antigravity CLI setup](docs/development/AI_SETUP.md#4-antigravity-cli-google) |

Detail that spans agents — per-host command discovery and naming, the cross-agent workflow
contract, non-interactive invocation flags, hook wiring and each host's block contract — lives in
[Slash Commands and Workflows](docs/development/ai/slash-commands.md),
[Cross-Agent Delegation Matrix](docs/development/ai/cross-agent-delegation.md) and
[AI Command Blocking](docs/development/ai/command-blocking.md).

Do not restate any of it here. `AGENTS.md` carries only what is true for every agent *and* must be
true at all times; see [ADR-9018](docs/decisions/9018-agentsmd-carries-only-shared-always-on-instructions.md).

### Temporary Files

AI agents **must never** write temporary files to generic locations like `/tmp/`. Instead, use the project-scoped directory:

```
tmp/agents/<agent-type>/
```

Where `<agent-type>` is one of: `claude`, `copilot`, `codex`, `antigravity`, or the relevant agent name.

**Filenames must include context** (issue number, PR number, or task identifier) to prevent collisions when multiple sub-agents run concurrently.

| | Example |
| :--- | :--- |
| **Before (wrong)** | `/tmp/pr-body.md` |
| **After (correct)** | `tmp/agents/claude/pr-body-issue-307.md` |

**Cleanup rule:** Agents must delete their temporary files when the task is complete. Do not leave stale files in `tmp/agents/`.

**Exception:** `tmp/checkpoints/` is the one location outside `tmp/agents/<agent-type>/`. Checkpoints written by `/checkpoint` are portable project-state captures meant to be readable by any agent — Claude can write a checkpoint and Codex or Copilot can restore from it.

**Worktrees are not temporary files.** A worktree lives until its PR merges, so it goes in `worktrees/` (gitignored), never under `tmp/`, which `doit cleanup` empties. Create one with `doit worktree`. Inside it, run commands through `uv run` and never pass `--active`, which installs the worktree into the main checkout's `.venv`. Merge its PR from the main checkout with `uv run doit pr_merge --pr=<number>`, which removes the worktree.

## Token Efficiency
- **Be Concise:** Minimal text output.
- **Use Local Tools:** Prefer native file tools over sub-agents (see [AI Agent File Operations](#ai-agent-file-operations)).
- **No Speculation:** Don't read files you don't need.

## Critical Reminders
- **Flow:** Issue (`doit issue`) -> **`git checkout main && git pull`** -> Branch -> Commit -> PR (`doit pr`) -> Merge (`doit pr_merge`). NEVER commit to main. Pull `main` before branching — local `main` may be behind the remote (e.g., after dependabot PRs merged via the web UI). `doit pr` enforces this by aborting if the branch is behind `origin/main`; pass `--no-update-check` to override. Saying "implement issue N", or approving work on an issue, runs this whole flow through branch, commit, and PR in one go via the `implement-issue` skill — it still never touches `main` or the merge step.
- **Scope:** Never mix refactoring, features, and docs in one PR. Create separate branches.
- **Verify:** Check file paths (`ls`) and branch (`git status`) before assuming they exist.
- **Security:** NEVER bypass security checks (e.g., `--no-verify`, ignoring secrets).
- **Tooling:** Prefer `doit` tasks over manual commands.
- **Integrity:** Respect architectural patterns (modularity) over "quick fixes".
- **Local State:** Protect user config (e.g., `.envrc.local`, settings). Do not revert/delete without backup.
- **Version:** Source of truth is Git tags. Never edit `pyproject.toml` version.
- **Tests:** Creating code = Creating tests. No exceptions. Never modify a failing test to make it pass — stop, explain why it broke, and discuss with the user whether the code or the test should change.
- **Commits:** One logical change per commit. Use conventional commits.
- **Releases:** Never run `doit release` without explicit command.
- **PRs:** Use `doit pr` to create PRs and `doit pr_merge` to merge with proper commit format. Issues are not automatically closed. Ask the user if they would like the related issue closed — pass `--auto-close` to `doit pr_merge` to close linked issues in one step. The `implement-issue` skill commits with `git commit` (not `doit commit`, which is interactive) and opens the PR itself with `doit pr` — it never applies `ready-to-merge`, merges, or closes the issue those steps remain the user's.
- **The Merge Gate action:** is a manual action for the user to add to a PR. It requires the ready-to-merge label and should never be added by automation. Exception: the dependabot auto-merge workflow (`.github/workflows/dependabot-automerge.yml`) applies the `ready-to-merge` label to qualifying dependabot PRs only. AI agents may apply the label only when the human has set `ALLOW_AI_READY_TO_MERGE=1` in the shell that launched the AI CLI (see `docs/development/ai/command-blocking.md`).
- **Issues:** Use `doit issue --type=<type>` to create issues (types: feature, bug, refactor, docs, chore). Labels are auto-applied. Manually close after PR merge with comment "Addressed in PR #XXX". Issues are not closed automatically when PRs are merged.
- **ADRs:** When implementing architectural decisions (typically `feat` or `refactor`, rarely `fix`), update related ADRs in `docs/decisions/` to add the issue link. Create new ADRs for significant decisions using `doit adr`. Every ADR must link to the documentation in `docs/` that describes the implementation. Doc and chore issues do not need ADRs. Issues with the `needs-adr` label require an ADR before the PR can be merged.

## PR Checklist (for AI agents)

Before creating a PR, read [CONTRIBUTING.md — Pull Request Process](.github/CONTRIBUTING.md#pull-request-process)
and work through the checklist in [`.github/pull_request_template.md`](.github/pull_request_template.md).
Between them they carry every check this section used to restate — `doit check`, branch and commit
format, the `Addresses #XX` reference, the `needs-adr` label, and ADR and documentation updates.

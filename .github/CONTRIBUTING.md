# Contributing to __PROJECT_NAME__

Thank you for your interest in contributing to this project! We welcome contributions from everyone.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [How to Contribute](#how-to-contribute)
- [Coding Standards](#coding-standards)
- [Testing Guidelines](#testing-guidelines)
- [Dependencies](#dependencies)
- [Commit Guidelines](#commit-guidelines)
- [Pull Request Process](#pull-request-process)
- [Release Process](#release-process)
- [Reporting Bugs](#reporting-bugs)
- [Requesting Features](#requesting-features)
- [Development Workflow](#development-workflow)
- [Questions?](#questions)
- [Thank You!](#thank-you)

## Code of Conduct

This project adheres to the Contributor Covenant [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## Getting Started

1. Fork the repository on GitHub
2. Clone your fork locally
3. Set up the development environment (see below)
4. Create a new branch for your changes
5. Make your changes
6. Run tests and checks
7. Submit a pull request

## Development Setup

### Prerequisites

- Python 3.12 or higher
- [uv](https://github.com/astral-sh/uv) - Fast Python package installer
- [direnv](https://direnv.net/) - Automatic environment management (recommended)

### Initial Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/bastproxy.git
cd bastproxy

# Set up direnv
direnv allow
# Optional: Create .envrc.local for personal settings
cp .envrc.local.example .envrc.local

# Install the project and its development tools (creates the venv)
uv sync --all-extras --dev

# Install pre-commit hooks
doit pre_commit_install
```

The development tools, `doit` included, live in the `dev` and `security` extras, and a plain
`uv sync` uninstalls them. Every sync after this first one is `doit install_dev`, which runs the
same command.

### Available Commands

View all available development tasks:
```bash
doit list
```

Common commands:
```bash
doit test          # Run tests
doit coverage      # Run tests with coverage
doit lint          # Run linting
doit format        # Format code
doit type_check    # Run type checking
doit check         # Run all checks
doit benchmark     # Run performance benchmarks
doit cleanup       # Clean build artifacts
```

## How to Contribute

### Types of Contributions

We welcome many types of contributions:

- **Bug fixes** - Fix issues in the codebase
- **New features** - Add new functionality
- **Documentation** - Improve docs, docstrings, examples
- **Tests** - Add or improve test coverage
- **Refactoring** - Improve code quality without changing behavior
- **Performance** - Optimize performance

### Before You Start

1. **Check existing issues** - See if someone is already working on it
2. **Open an issue** - Discuss your proposed changes before starting work
3. **Get feedback** - Especially for large changes or new features

## Coding Standards

### Python Style

- **Python version:** 3.12+ with modern type hints
- **Line length:** Max 100 characters
- **Docstrings:** Google-style for all public APIs
- **Type hints:** Required for all public functions/methods
- **Naming:** `snake_case` for functions/variables, `PascalCase` for classes
- **File I/O:** Always pass `encoding="utf-8"` to `Path.read_text()`,
  `Path.write_text()`, text-mode `open()`, and `tempfile.NamedTemporaryFile()`.
  Omitting the kwarg falls back to `locale.getpreferredencoding()`, which is
  `cp1252` on Windows and breaks silently on non-ASCII content. Binary-mode
  calls (`"rb"`, `"wb"`, `"ab"`) and `tarfile.open(...)` do not take an
  encoding kwarg. Enforced by ruff's `PLW1514` rule.

### Type Hints

Use modern type hint syntax:
```python
# Good
def process_items(items: list[str]) -> dict[str, int]:
    pass

# Bad
from typing import List, Dict
def process_items(items: List[str]) -> Dict[str, int]:
    pass
```

### Docstrings

Use Google-style docstrings. These are automatically extracted into the
[API Reference](../docs/reference/api.md) documentation using mkdocstrings.

```python
def example_function(param1: str, param2: int = 10) -> bool:
    """Short description of the function.

    Longer description if needed, explaining the purpose,
    behavior, and any important details.

    Args:
        param1: Description of param1.
        param2: Description of param2. Defaults to 10.

    Returns:
        Description of return value.

    Raises:
        ValueError: When param2 is negative.

    Examples:
        >>> example_function("test", 5)
        True
        >>> example_function("", 10)
        False
    """
```

**Key points:**

- Type hints go in signatures, not duplicated in docstrings
- End descriptions with periods for consistency
- Include `Examples` section for complex functions (used by doctests)
- Document all public functions, classes, and methods
- Module-level docstrings describe the module's purpose

### Code Organization

Organize imports in three groups:
```python
# Standard library
import os
from pathlib import Path

# Third-party
import click
import pytest

# Local
from bastproxy import module
```

## Testing Guidelines

### Writing Tests

- Write tests for all new functionality
- Maintain or improve test coverage (target: ≥80%)
- Use descriptive test names: `test_function_does_something_when_condition`
- Use fixtures for common setup
- Test edge cases and error conditions

### Running Tests

```bash
# Run all tests
doit test

# Run with coverage
doit coverage

# Run specific test file
uv run pytest tests/test_example.py

# Run specific test
uv run pytest tests/test_example.py::test_specific_function -v
```

### Test Structure

```python
import pytest

def test_feature_works_correctly():
    """Test that feature produces expected output."""
    # Arrange
    input_data = "test input"

    # Act
    result = function_to_test(input_data)

    # Assert
    assert result == expected_output


@pytest.mark.parametrize("input_value,expected", [
    ("value1", "expected1"),
    ("value2", "expected2"),
])
def test_feature_with_multiple_inputs(input_value, expected):
    """Test feature with various inputs."""
    assert function_to_test(input_value) == expected
```

## Dependencies

### Ask First

Get approval before you add any dependency: a runtime dependency, an entry in the `dev` or
`security` extra, or a type stub. Propose it first — name the package, what it is for, the table
it belongs in, and why the standard library or an existing dependency will not do. Contributors
propose it on the issue. AI agents ask the user and wait.

AI agents cannot run `uv add` at all. The dangerous-command hook,
[`block-dangerous-commands.py`](../tools/hooks/ai/block-dangerous-commands.py), blocks it in any
form — with flags, chained after another command, even `uv add --help` — and tells the agent to
suggest the package and let the user run the command. The script is wired into every supported
agent's hook configuration; see
[AI Command Blocking](../docs/development/ai/command-blocking.md#blocked-workflow-commands). The
hook matches the command, not the intent: writing the entry into `pyproject.toml` by hand is the
same change and needs the same approval.

### Where a Dependency Goes

| `pyproject.toml` table | Holds | Command |
| :--- | :--- | :--- |
| `[project] dependencies` | What code under `src/` imports at runtime. It ships to every user of the package, so keep it minimal. | `uv add <package>` |
| `[project.optional-dependencies] dev` | Tests, linting, type checking, docs, and `doit` tasks. Type stubs go here, even for a runtime package. | `uv add --optional dev <package>` |
| `[project.optional-dependencies] security` | The tools behind `doit audit`, `doit security`, `doit licenses` and `doit sbom`. | `uv add --optional security <package>` |

There is no `[dependency-groups]` table. uv's `--dev` flags act on a `dev` dependency *group*,
not on the `dev` extra above.

Give every entry a `>=` lower bound, as the existing entries have, and commit `pyproject.toml`
and `uv.lock` together.

### Typing

mypy runs without a global `ignore_missing_imports`, so importing a package that ships neither
inline types nor stubs fails with `[import-untyped]`. Either:

- add its stub package to the `dev` extra, as `types-pyyaml` is there for `pyyaml`; or
- if no stubs exist, add a `[[tool.mypy.overrides]]` entry with `ignore_missing_imports = true`
  for that package's modules only, as `pyproject.toml` has for `doit.*`.

### Checks

Both tasks need the `security` extra, which `doit install_dev` installs with the other development
tools. Then run:

- `doit audit` — `pip-audit` checks the environment for dependencies with known
  vulnerabilities.
- `doit licenses` — `pip-licenses` lists every installed package by license. Confirm the new
  package, and anything it pulls in, is compatible with the project's license.

Without the extra, both tasks print an install hint and exit 0, a pass that checked nothing.
`doit check` runs `audit` but not `licenses`.

## Commit Guidelines

Follow [Conventional Commits](https://www.conventionalcommits.org/):

### Commit Format

```
<type>: <subject>

[optional body]

[optional footer]
```

### Commit Types

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Formatting, whitespace (no code change)
- `test`: Adding or updating tests
- `refactor`: Code refactoring
- `perf`: Performance improvements
- `chore`: Maintenance tasks (deps, tooling)
- `ci`: CI/CD changes
- `revert`: Reverting previous commits

### Examples

```bash
feat: add support for async operations

fix: handle None values in data processor

docs: update installation instructions

test: add tests for edge cases in parser
```

### Passing the Message

Short one-liners are fine inline:

```bash
git commit -m "fix: handle None values in data processor"
```

**Anything longer goes in a file.** Write the message, then pass it with `-F`:

```bash
# AI agents: use tmp/agents/<agent-type>/ and delete the file afterwards
git commit -F tmp/agents/claude/commit-752.md
```

This matches how every other long-form body in this project is passed —
`doit issue --body-file=`, `doit pr --body-file=`, `doit adr --body-file=`.

It is also the only reliable way to write a message *about* the enforcement system. A heredoc
(`git commit -F - <<EOF`) is scanned by the dangerous-command hook as command arguments, so a
message that merely names `--admin`, `gh issue create` or any other blocked pattern is refused as
if it invoked it. The hook is not taught to tell prose from commands — doing that means skipping
heredoc bodies for a list of trusted commands, and a mistake in such a list is a bypass rather than
an inconvenience (see [ADR-9019](../docs/decisions/9019-the-dangerous-command-hook-is-a-guardrail-not-a-security-boundary.md)).
Passing the message by file costs nothing and avoids the question entirely.

### Breaking Changes

For breaking changes, include `BREAKING CHANGE:` in the footer:

```
refactor: change API to use async/await

BREAKING CHANGE: All public methods are now async.
Update calling code to use `await`.
```

### Exceptions

**Dependabot commits** are exempt from the full merge commit format. Dependabot automatically generates commits with:

```
chore(deps): bump <package> from X to Y (#PR)
```

This is acceptable because:
- Dependabot creates commit messages before the PR exists (cannot reference PR number)
- Automated dependency updates don't have linked issues
- The `chore(deps):` format follows conventional commits with a scope

## Pull Request Process

### Before Submitting

1. **Run all checks locally:**
   ```bash
   doit check
   ```

2. **Use conventional commit messages** - Your commit messages (`feat:`, `fix:`, etc.) automatically become changelog entries during release. See [Commit Guidelines](#commit-guidelines).

3. **Update documentation** (if needed)

4. **Update related ADRs** (if implementing an architectural decision) - Add your issue link to the Related section

5. **Self-review your code**

### PR Title

Use the same format as commits: `<type>: <subject>`

Examples:
- `feat: add support for custom validators`
- `fix: handle edge case in data parsing`
- `docs: improve API documentation`

### PR Description

Fill out the PR template (`.github/pull_request_template.md`):
- Provide a clear summary
- List specific changes
- Reference related issues
- Describe testing performed
- Note any breaking changes

### PR Review Process

1. **Automated checks** - CI must pass (tests, lint, type-check)
2. **Code review** - At least one maintainer approval required
3. **Address feedback** - Respond to review comments
4. **Add `ready-to-merge` label** - When PR is approved and CI passes (see below)
5. **Merge** - Maintainer will merge when approved

### Merge Gate and `ready-to-merge` Label

This repository uses a **merge gate** workflow to prevent premature merges:

**Why this exists:**
- Ensures full CI matrix (all OS/Python versions) completes before merge
- Prevents merging while tests are still running
- Provides explicit "ready" signal after review

**How it works:**
1. Open a PR - initial CI checks run
2. Get code review and address feedback
3. Wait for **all** CI checks to pass (including full OS matrix)
4. Add the `ready-to-merge` label to signal the PR is ready
5. The merge gate check passes, allowing merge

**Important:**
- The `ready-to-merge` label should only be added after:
  - All CI checks have passed (including full OS matrix)
  - Code review is complete and approved
  - All feedback has been addressed
- Adding the label prematurely doesn't bypass CI - the merge gate waits for CI completion
- The label works alongside GitHub's approval requirement - both must be satisfied

**With approval workflows enabled:**

If your repository requires PR approvals (branch protection → "Require approvals"), the merge flow becomes:

1. CI checks pass
2. Reviewer approves the PR
3. Add `ready-to-merge` label (final "ship it" signal)
4. Merge allowed

The label and approval are independent checks - both must pass. The label serves as an explicit final confirmation after review and CI are complete.

### After Merge

- Delete your branch
- Update your fork with the latest changes
- Close any related issues with comment "Addressed in PR #XXX"

## Release Process

This section documents how to publish releases to TestPyPI and PyPI.

> **Note:** Releases can only be performed by maintainers with push access to the repository and appropriate PyPI/TestPyPI permissions.

### How Versioning Works

This project uses **semantic versioning** derived automatically from git tags via [hatch-vcs](https://github.com/ofek/hatch-vcs):

- **No manual version editing** - Version is determined by git tags
- **Tag format:** `v<major>.<minor>.<patch>` (e.g., `v1.2.3`)
- **Pre-release format:** PEP440 `v<version><type><n>` (e.g., `v1.2.3a0`, `v1.2.3b1`, `v1.2.3rc0`, `v1.2.3.dev0`) — emitted by commitizen via `doit release --prerelease=...`

Version bumping is handled by [commitizen](https://commitizen-tools.github.io/commitizen/) based on conventional commit history:

| Commit Type | Version Bump |
|-------------|--------------|
| `fix:` | Patch (1.0.0 → 1.0.1) |
| `feat:` | Minor (1.0.0 → 1.1.0) |
| `BREAKING CHANGE:` | Major (1.0.0 → 2.0.0) |

The table assumes `major_version_zero = false` in `[tool.commitizen]`. The template ships it as
`true` for a project still on 0.x, where a `BREAKING CHANGE:` bumps MINOR (0.3.0 → 0.4.0).
commitizen applies the setting at every version, not only below 1.0, so set it to `false` before
the 1.0.0 release: `doit release` refuses to release 1.0.0 or later while it is `true`.
`doit release --increment=MAJOR` then cuts 1.0.0 from 0.x.

### Release Workflow

All releases — production and pre-release — go through a pull request.
`doit release` opens the release PR; a reviewer merges it; `doit release_tag`
then tags `main` and triggers the publish workflow. Direct-to-`main` release
commands are not supported.

```bash
# Step 1: open a release PR
doit release                       # auto-detect next version from commits
doit release --increment=major     # force MAJOR (1.0.0 → 2.0.0)
doit release --increment=minor     # force MINOR
doit release --increment=patch     # force PATCH
doit release --prerelease=alpha    # open a pre-release PR (1.0.0 → 1.0.1a0)
doit release --prerelease=beta
doit release --prerelease=rc

# --> reviewer merges the PR --

# Step 2: tag main and trigger publish
git checkout main
git pull
doit release_tag
```

`--increment` and `--prerelease` can be combined to force a pre-release of a
specific bump type (e.g. `--prerelease=alpha --increment=minor` → `1.1.0a0`).
See [issue #475](https://github.com/endavis/pyproject-template/issues/475).

**What `doit release` does:**

1. Verifies you're on `main`
2. Validates `--prerelease` (must be empty, `alpha`, `beta`, or `rc`), `--issue` (must be empty or a number) and `--increment` (must be empty, `MAJOR`, `MINOR` or `PATCH`, in any case)
3. Checks for uncommitted changes
4. Pulls latest changes from remote
5. Validates merge commit format (governance check)
6. Validates issue links in commits
7. Runs all checks (`doit check`)
8. Determines the next version using commitizen (`cz bump --get-next`)
9. Creates a `release/vX.Y.Z` branch and updates `CHANGELOG.md`
10. Commits the changelog, pushes the branch, and opens PR `release: vX.Y.Z`

A project with a static version or a hand-written changelog gets two more
steps here — see [Release Automation — Downstream opt-ins](../docs/development/release-and-automation.md#downstream-opt-ins-static-version-and-hand-written-changelog).

**What `doit release_tag` does:**

1. Verifies you're on `main`, pulls latest changes
2. Finds the most recently merged `release: vX.Y.Z` PR
3. Extracts the version from the PR title (falls back to the branch name)
4. Creates the git tag `vX.Y.Z` on `main`
5. Pushes the tag
6. **Triggers:** `.github/workflows/release.yml` (production) or
   `.github/workflows/testpypi.yml` (pre-release)
7. **Publishes to:** TestPyPI first, then PyPI for production tags; TestPyPI
   only for pre-release tags

**Testing a pre-release from TestPyPI:**

```bash
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ __PYPI_NAME__==1.0.1a0
```

### Workflow Triggers

| Workflow | Trigger | Destination |
|----------|---------|-------------|
| `testpypi.yml` | PEP440 pre-release tags: `v*a[0-9]*`, `v*b[0-9]*`, `v*rc[0-9]*`, `v*.dev[0-9]*` (e.g., `v1.0.0a0`) | TestPyPI only |
| `release.yml` | Tag matching `v[0-9]+.[0-9]+.[0-9]+` (e.g., `v1.0.0`) | TestPyPI → PyPI |

### Setting Up Release Permissions

`doit release_tag` pushes the version tag directly to `main`. If your branch
protection rules cover tag pushes, configure a bypass for the tagging step.
The release PR itself is reviewed and merged through the normal PR flow, so
no bypass is required for the commit and changelog changes.

#### Which path should I use?

The two paths below are not "personal vs. organization" — a GitHub App
works just as well on a personal account. The real distinction is **where
your release runs from** and **whether you want full dependabot
auto-merge automation**:

| Use case | Recommended |
| :--- | :--- |
| CI-driven releases (workflow publishes from GitHub Actions) | **GitHub App** |
| Dependabot auto-merge end-to-end automation | **GitHub App** (required) |
| Org policy disallows PATs | **GitHub App** |
| Solo / hobby repo, releasing only from your laptop, no CI release | **Fine-grained PAT** |

> [!IMPORTANT]
> The dependabot auto-merge workflow at
> `.github/workflows/dependabot-automerge.yml` **requires a GitHub App**. A
> PAT does not substitute, because the workflow needs the bot's `labeled`
> event to trigger the Merge Gate — see
> [Dependabot Auto-merge → Required GitHub App configuration](../docs/development/dependabot-automerge.md#required-github-app-configuration).

#### Recommended: GitHub App

A dedicated GitHub App is the modern, audit-friendly identity for release
automation. It works for both personal-account repositories and
organization repositories. Use this path if you want:

- The dependabot auto-merge workflow to be fully automated end-to-end
- A clean bot identity in the audit log instead of human attribution
- Automatic short-lived token rotation (no manual PAT renewals)
- A bypass-listed actor for any CI-driven tag-push flow you add later

> [!NOTE]
> The publish workflow at `.github/workflows/release.yml` uses **PyPI
> trusted publishing (OIDC)** and the built-in `GITHUB_TOKEN`. It does not
> consume `RELEASE_APP_ID` or `RELEASE_APP_PRIVATE_KEY`. Those credentials
> exist for the dependabot auto-merge workflow and for any CI-driven
> tag-push extension you might add — see step 5 below.

Create a dedicated GitHub App that can bypass branch protection:

**1. Create the GitHub App:**

1. Go to **GitHub Settings** → **Developer Settings** → **GitHub Apps**
2. Click **New GitHub App**
3. Fill in:
   - **Name:** `<your-org>-release-bot` (must be globally unique)
   - **Homepage URL:** Your repository URL
   - **Webhook:** Uncheck "Active" (not needed)
4. Set **Repository Permissions:**
   - **Contents:** Read and write (to push commits/tags)
   - **Metadata:** Read-only (required)
   - **Pull requests:** Write (required for the dependabot auto-merge
     workflow to apply the `ready-to-merge` label via the App — see
     [Dependabot Auto-merge → Required GitHub App configuration](../docs/development/dependabot-automerge.md#required-github-app-configuration))
5. Click **Create GitHub App**
6. Note the **App ID** displayed on the app page
7. Scroll down → **Generate a private key** → saves a `.pem` file

**2. Install the App:**

1. On the App page, click **Install App** (left sidebar)
2. Select your organization
3. Choose **Only select repositories** → select your repo
4. Click **Install**

**3. Add to Ruleset Bypass:**

1. Go to **Repo Settings** → **Rules** → **Rulesets** → select your main branch ruleset
2. Under **Bypass list**, click **Add bypass**
3. Select your release app from the list
4. Save the ruleset

**4. Store Credentials at the Repository Scope:**

In your repo **Settings** → **Secrets and variables** → **Actions** — store
both at the **repository** scope, not in an environment:

- **Secrets** tab → **New repository secret:**
  `RELEASE_APP_PRIVATE_KEY` = contents of the `.pem` file
- **Variables** tab → **New repository variable:**
  `RELEASE_APP_ID` = the App ID from step 1

> [!WARNING]
> Use the repository scope, not an environment scope. The `enable-automerge`
> job in `.github/workflows/dependabot-automerge.yml` does not declare an
> `environment:`, so `${{ vars.RELEASE_APP_ID }}` and
> `${{ secrets.RELEASE_APP_PRIVATE_KEY }}` only resolve at the repository (or
> organization) scope. Storing either as an environment secret/variable makes
> them silently resolve to an empty string at runtime — the workflow's
> `if: vars.RELEASE_APP_ID != ''` guard fails closed and the label is applied
> with `GITHUB_TOKEN`, which leaves the Merge Gate's `require-label` check
> stuck at `FAILURE`.

**5. Optional: CI-Driven Tag-Push Flow (not used by this project's `release.yml`):**

This project's `release.yml` is triggered by a tag push that the
maintainer makes locally with `doit release_tag`, and the publish step
itself uses OIDC + `GITHUB_TOKEN` — so no App credentials are consumed by
the workflow as shipped.

If you later add a CI-driven flow that needs to push commits or tags from
inside Actions (for example, a `workflow_dispatch` job that runs `cz
bump`, commits the changelog, and pushes the tag), mint an App
installation token and check out with it so the push uses the App's
identity:

```yaml
- name: Generate release token
  id: app-token
  uses: actions/create-github-app-token@v3
  with:
    app-id: ${{ vars.RELEASE_APP_ID }}
    private-key: ${{ secrets.RELEASE_APP_PRIVATE_KEY }}

- name: Checkout with token
  uses: actions/checkout@v4
  with:
    token: ${{ steps.app-token.outputs.token }}
    fetch-depth: 0
```

Because the App is on the Ruleset bypass list (step 3), pushes signed by
its installation token can land on `main` and on protected tag refs
without rule violations.

#### Alternative: Fine-Grained PAT (local-only releases)

Use this path **only** if all of the following apply:

- You release from a maintainer's laptop with `doit release_tag` (no CI)
- You don't need the dependabot auto-merge workflow's full automation
- You're comfortable rotating the PAT before its expiration

For any other case, use the [GitHub App path](#recommended-github-app)
above. CI-driven releases or dependabot auto-merge automation should not
use a PAT.

**1. Create a Fine-Grained PAT:**

1. Go to **GitHub Settings** → **Developer Settings** → **Personal access tokens** → **Fine-grained tokens**
2. Click **Generate new token**
3. Fill in:
   - **Name:** `release-token`
   - **Expiration:** Set appropriate expiration
   - **Repository access:** Select your repository
4. Set **Repository Permissions:**
   - **Contents:** Read and write
   - **Metadata:** Read-only
5. Click **Generate token** and copy it immediately

**2. Configure Git to Use the Token:**

For local releases, configure git to use the token:

```bash
# Option 1: Use credential helper (recommended)
git config --global credential.helper store
# Then git will prompt for credentials on first push

# Option 2: Include token in remote URL (less secure)
git remote set-url origin https://<token>@github.com/username/repo.git
```

### Release Checklist

Before opening a release PR:

- [ ] All CI checks pass on `main`
- [ ] No uncommitted changes on your working tree
- [ ] You have push access to the repository
- [ ] PyPI/TestPyPI environments are configured in GitHub

After the release PR is merged:

- [ ] `git checkout main && git pull`
- [ ] `doit release_tag`
- [ ] Monitor the publish workflow in GitHub Actions
- [ ] Verify the new version on TestPyPI (pre-release) or PyPI (production)

### Typical Release Cycle

1. **Development:** Features merged to `main` via PRs
2. **Alpha testing:** `doit release --prerelease=alpha` → merge PR → `doit release_tag` → Test on TestPyPI
3. **Beta testing:** `doit release --prerelease=beta` → merge PR → `doit release_tag` → Wider testing
4. **Release candidate:** `doit release --prerelease=rc` → merge PR → `doit release_tag` → Final testing
5. **Production:** `doit release` → merge PR → `doit release_tag` → Publish to PyPI

### Troubleshooting

**"Uncommitted changes detected"**
- Commit or stash your changes before releasing

**"Not on main branch"**
- Switch to main: `git checkout main && git pull`

**"Pre-release checks failed"**
- Run `doit check` and fix any issues before retrying

**"commitizen bump failed"**
- Ensure commits follow conventional format
- Check that there are commits since the last tag

**PyPI publish fails**
- Verify GitHub environment secrets are configured
- Check that the version doesn't already exist on PyPI

## Reporting Bugs

Use the bug report template (`.github/ISSUE_TEMPLATE/bug_report.yml`):

1. Go to **Issues** → **New Issue** → **Bug Report**
2. Fill out all sections:
   - Clear description of the bug
   - Steps to reproduce
   - Expected vs actual behavior
   - Environment details (OS, Python version, package version)
   - Error messages or logs
3. Add relevant labels
4. Be responsive to follow-up questions

## Requesting Features

Use the feature request template (`.github/ISSUE_TEMPLATE/feature_request.yml`):

1. Go to **Issues** → **New Issue** → **Feature Request**
2. Fill out all sections:
   - Problem statement
   - Proposed solution
   - Alternative solutions considered
   - Use cases
   - Benefits
3. Be open to discussion and feedback
4. Be willing to implement it yourself (or help)

## Development Workflow

**MANDATORY RULE:** All changes must originate from a GitHub Issue.

### Issue-Driven Development

Every code change must be linked to a GitHub Issue. This ensures:
- **Traceability:** Every change is linked to a documented need
- **Context:** Issues capture the "why" behind changes
- **Planning:** Better project management and prioritization
- **History:** Searchable record of decisions and rationale
- **Collaboration:** Clear communication about work in progress

### Workflow Steps

#### 1. **Issue:** Ensure GitHub Issue Exists

**Create issue using doit (recommended):**
```bash
# Interactive: Opens $EDITOR with template
doit issue --type=feature    # For new features
doit issue --type=bug        # For bugs and defects
doit issue --type=refactor   # For code refactoring
doit issue --type=docs       # For documentation
doit issue --type=chore      # For maintenance tasks

# Non-interactive: For AI agents or scripts
doit issue --type=feature --title="Add export" --body-file=issue.md
doit issue --type=docs --title="Add guide" --body="## Description\n..."
```

**Or use gh CLI directly:**
```bash
gh issue create --title "<description>" --label "enhancement" --body "..."
```

**Issue types auto-apply labels:**
- `feature` → `enhancement, needs-triage`
- `bug` → `bug, needs-triage`
- `refactor` → `refactor, needs-triage`
- `docs` → `documentation, needs-triage`
- `chore` → `chore, needs-triage`

**Required fields ensure complete information** - Fill all fields to provide context.

#### 2. **Branch:** Create Branch Linked to Issue

**Branch Format:** `<type>/<number>-<description>`

**Allowed Types:**
- `issue`, `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `ci`, `perf`, `hotfix`
- Special: `release/<version>` (no issue number required)

**Examples:**
```bash
feat/42-user-authentication
fix/123-handle-null-values
docs/41-update-guidelines
refactor/55-simplify-parser
```

**Create and link branch:**
```bash
# Option 1: GitHub CLI (auto-links)
gh issue develop <issue-number> --checkout

# Option 2: Manual (include issue number in name)
git checkout -b feat/42-add-feature
```

**Branch naming is enforced by pre-commit hooks.**

**When your checkout holds other work,** create the branch in a worktree instead:

```bash
doit worktree --branch=feat/42-add-feature
```

The worktree goes in `worktrees/feat/42-add-feature` (gitignored), with its own `.venv`. Inside it,
run everything through `uv run` (`uv run doit check`, `uv run doit pr`) and never pass `--active`,
which installs the worktree into the main checkout's `.venv`. Merge the PR from the main checkout
with `uv run doit pr_merge --pr=<number>`, which then removes the worktree and its branch and
fast-forwards `main`. See
[`doit worktree`](../docs/development/doit-tasks-reference.md#worktree).

#### 3. **Commit:** Use Conventional Commits

**Format:** `<type>: <subject>`

Use `doit commit` for interactive commit creation with commitizen.

**Enforced by:**
- Pre-commit hooks (locally)
- CI checks (on PR)

#### 4. **Pull Request:** Submit PR from Branch to `main`

**Create PR using doit (recommended):**
```bash
# Interactive: Opens $EDITOR with template
doit pr

# Non-interactive: For AI agents or scripts
doit pr --title="feat: add export" --body-file=pr.md
doit pr --title="feat: add export" --body="## Description\n..."

# Create as draft
doit pr --draft
```

Features:
- Auto-detects issue number from branch name (e.g., `feat/42-description` → `Addresses #42`)
- Pre-fills the PR template with detected issue
- Validates required fields before creating

**Work that builds on an unmerged branch:** When issue B needs code from issue A's branch before A
merges, branch B from A and open B's PR against A's branch. The PR then shows only B's changes:

```bash
git checkout -b feat/43-use-parser feat/42-add-parser
doit pr --base=feat/42-add-parser --title="feat: use the parser" --body-file=pr.md
```

`doit pr` then checks that B is up to date with `origin/feat/42-add-parser` instead of
`origin/main`. While B targets A's branch, `ci.yml` and `merge-gate.yml` do not run on it (both
filter on `branches: [main]`), and `doit pr_merge` refuses it.

Merge A first. Then replay only B's own commits onto `main`, retarget the PR, and push:

```bash
lower_tip=$(gh pr view <A's PR number> --json headRefOid --jq .headRefOid)
git fetch origin
git rebase --onto origin/main "$lower_tip"
gh pr edit <B's PR number> --base main
git push --force-with-lease origin feat/43-use-parser
```

Do not use a plain `git rebase origin/main` here. A was squash-merged, so B still carries A's
original commits, and replaying them can conflict. Retarget before pushing: CI starts on the push,
not on the retarget.

**PR Title:**
- Must follow conventional commit format: `<type>: <subject>`
- PR title becomes the merge commit message
- Examples: ✅ `feat: add validators`, ❌ `Add validators`

**PR Description Requirements (enforced by CI):**
- Minimum 50 characters
- Reference related issue: "Addresses #42"
- Describe what changed and why
- Include testing information

#### 5. **Merge:** Format Must Include PR and Issue Numbers

**Merge commit format:**
```
<type>: <subject> (merges PR #XX, addresses #YY)
```

**Examples - Correct:**
```
feat: add user authentication (merges PR #18, addresses #42)
fix: handle None values (merges PR #23, addresses #19)
docs: update installation guide (merges PR #29, addresses #25)
```

**Examples - Incorrect:**
```
❌ Merge pull request #18 from user/branch
❌ feat: Add Feature (capitalized subject)
❌ added feature (missing type)
❌ feat: add feature (missing PR reference)
```

**Using `doit pr_merge`:**

The `doit pr_merge` task enforces this format automatically:

```bash
# Merge PR for current branch
doit pr_merge

# Merge specific PR
doit pr_merge --pr=123

# Keep branch after merge (default deletes it)
doit pr_merge --delete-branch=false
```

The task:
- Fetches PR title, number, and linked issues from GitHub
- Refuses a PR whose base is not the default branch, before merging or closing anything
- Validates PR title follows conventional commit format
- Constructs the merge commit subject automatically
- Uses squash merge with the formatted subject
- When a linked worktree has the PR's branch checked out, deletes the branch itself and removes a
  worktree under `worktrees/`. Run it from the main checkout, with `--pr`. See
  [`pr_merge`](../docs/development/doit-tasks-reference.md#pr_merge)
- Fast-forwards the base branch after the merge when it was run from that branch, which is where a
  worktree's PR is merged from

### Architecture Decision Records (ADRs)

When your PR implements or relates to an architectural decision, update the relevant ADR:

**When to update an ADR:**
- Your PR implements a decision documented in an existing ADR
- Your PR changes behavior described in an ADR
- Your issue is related to an architectural decision

**How to update:**
1. Find related ADRs in `docs/decisions/`
2. Add your issue to the "Related Issues" section: `- Issue #XX: Brief description`
3. Add links to implementation docs in "Related Documentation" section
4. Include the ADR update in your PR

**When to create a new ADR:**
- Introducing a new tool, framework, or library
- Changing development workflow or processes
- Making decisions that affect project architecture
- Decisions that future contributors should understand

**Which issue types may need ADRs:**
- **Feature**: Often - new features may introduce architectural decisions
- **Refactor**: Often - refactoring may change architecture or patterns
- **Bug**: Rarely - only if the fix reveals a significant design decision
- **Doc/Chore**: No - documentation and maintenance don't need ADRs

**The `needs-adr` label:**
Use the `needs-adr` label on issues that require an ADR. This signals that:
- The issue involves an architectural decision
- An ADR should be created as part of the PR
- The PR should not be merged without the ADR

**Create a new ADR:**
```bash
# Interactive (opens editor)
doit adr --title="Use Redis for caching"

# Non-interactive (for scripts/AI)
doit adr --title="Use Redis" --body-file=adr.md
doit adr --title="Use Redis" --body="## Status\nAccepted\n..."
```

**ADR requirements:**
- Every ADR must link to the GitHub Issues where the decision was discussed
- Every ADR must link to documentation in `docs/` that describes the implementation
- If no documentation exists, create it as part of the PR

ADRs provide context for why decisions were made, helping future contributors understand the project's evolution.

### Edge Cases

**Issue needs to be split during work:**
- Create new issues for discovered separate concerns
- Update original issue to reference the new issues
- Continue work on current branch or create new branches

**Issue is obsolete or duplicate:**
- Comment explaining why it's obsolete/duplicate
- Link to the duplicate issue if applicable
- Close with appropriate label (duplicate, wontfix)
- Delete branch if no work committed

**Work spans multiple sessions:**
- Update issue with progress comments
- Document decisions and approaches tried
- Push commits regularly
- Keep PR description updated

### Keeping Your Fork Updated

```bash
# Add upstream remote (one-time setup)
git remote add upstream https://github.com/endavis/bastproxy.git

# Fetch and merge upstream changes
git checkout main
git fetch upstream
git merge upstream/main
git push origin main
```

## Questions?

If you have questions:

1. Check the [README.md](../README.md) and [AGENTS.md](../AGENTS.md)
2. Search existing [Issues](https://github.com/endavis/bastproxy/issues)
3. Open a new issue with the "question" label
4. Join our discussions (if available)

## Thank You!

Your contributions make this project better for everyone. We appreciate your time and effort!

---

For more detailed information, see:
- [README.md](../README.md) - Project overview
- [AGENTS.md](../AGENTS.md) - Development guide for AI agents
- [Architecture Decision Records](../docs/decisions/README.md) - Documented architectural decisions
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) - Community guidelines
- [SECURITY.md](SECURITY.md) - Security policy

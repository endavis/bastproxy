## Migrating an Existing Project to This Template

Use this checklist to bring an existing Python project into the template. The flow assumes hatch-vcs for versioning, commitizen for tagging/changelog, uv for deps, and doit for tasks.

### 1) Inventory & Prep
- Note current package import name, supported Python versions, dependencies (runtime/dev/extras), scripts/entry points, CI/release setup.
- Ensure current tests pass before migrating.

### 2) Bring in the Template
- **Backup:** Rename your existing `README.md`, `LICENSE`, and `pyproject.toml` (e.g., to `*.old`) so you don't lose content.
- **Copy Files:** Copy template files into your repo:
    - **Config:** `pyproject.toml`, `dodo.py`, `.envrc`, `.pre-commit-config.yaml`, `.python-version`, `mkdocs.yml`.
    - **Docs & Guides:** `AGENTS.md`, `AI_SETUP.md`, `docs/*`, `examples/*`, `CHANGELOG.md`.
    - **Hidden Configs:** `.github/workflows/*`, `.vscode/`, `.devcontainer/`, `.claude/`, `.codex/`, `.gemini/`, `tmp/.gitkeep`.
- **Keep your code:** You’ll move it in step 4.

### 3) Run the Configurator
- From the template root: `python configure.py`.
- Provide project name, package name (import), PyPI name, author, GitHub user, description.
- **What it does:** Rewrites placeholders (badges/links/docs/workflows), renames `src/bastproxy → src/<your_package>`, and removes itself.

### 4) Move Your Code
- Move your existing package source into the newly renamed `src/<your_package>/`.
- **Cleanup:** Delete the template's default `core.py` if not needed.
- **Type Hinting:** Ensure `py.typed` exists in `src/<your_package>/` to mark your package as typed.
- **Versioning:** Leave `_version.py` as the stub; hatch-vcs generates it at build time from git tags.

### 5) Update pyproject.toml
- **Merge, don't overwrite:** Copy your dependencies and metadata *into* the new `pyproject.toml`. Preserve the `[tool]` sections (hatch, ruff, mypy, doit) provided by the template.
- Update `[project.dependencies]`.
- Add dev tools to `[project.optional-dependencies]` (keep the template's defaults like `ruff`, `pytest` if possible).
- Define entry points under `[project.scripts]` if you have a CLI.

### 6) Tests & Coverage
- Move your tests to `tests/`.
- If moving from a flat layout to `src/`, you may need to adjust imports in your tests.
- Ensure `dodo.py` and workflows point coverage to the correct package (handled by `configure.py`, but worth double-checking).

### 7) Regenerate Lockfile
- Run `uv lock` to refresh `uv.lock` with your merged dependencies.

### 8) Tasks and CI
- Local tasks: `doit check` runs format (ruff), lint, mypy, tests.
- Workflows: `ci.yml` runs checks; `release.yml` triggers on stable `v*` tags; `testpypi.yml` triggers on prerelease `v*-<pre>` tags.

### 9) Docs & Badges
- Check `README.md`: Restore your project description, but keep the new badges (links were updated by `configure.py`).
- Update docs (`docs/installation.md`, `docs/usage.md`, `docs/api.md`) with your specific details.

### 10) Verify Locally
- Install environment: `uv sync --all-extras --dev`
- Install hooks: `doit pre_commit_install`
- Run checks: `doit check`
- Run tests: `doit test`

### 11) Release Flow
- **Prerelease:** `doit release_dev` → bumps version (e.g., alpha) → tags → triggers `testpypi.yml`.
- **Production:** `doit release` → bumps version (stable) → tags → triggers `release.yml`.
- **Important:** No manual edits to `pyproject.toml` version or `_version.py`; the git tag is the source of truth.

### 12) Clean Up & Commit
- Remove old CI configs/Makefiles you no longer need.
- `direnv allow` to load `.envrc`.
- Commit and push. Monitor CI actions to ensure the migration was successful.
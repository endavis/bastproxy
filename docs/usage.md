# Usage Guide

This guide covers both package usage and development workflows.

## Package Usage

### Basic Usage

```python
from bastproxy import greet

# Simple greeting
message = greet("World")
print(message)  # Output: Hello, World!

# Custom name
message = greet("Python")
print(message)  # Output: Hello, Python!
```

### API Documentation

See the [API Reference](api.md) for complete documentation of all available functions and classes.

---

## Development Workflows

This section is for developers working on the project.

### Migration

Coming from an existing project? See the [Migration Guide](migration.md) for step-by-step instructions to adopt this template (configure placeholders, move code to `src/`, update deps, and align CI/release).

### Quick Reference

```bash
# Run tests (parallel)
uv run pytest -n auto -v

# Run all quality checks
uv run doit check

# Format code
uv run doit format

# Build documentation
uv run doit docs_serve
```

### Available Tasks

Use `doit list` to see all available tasks:

```bash
uv run doit list
```

#### Testing Tasks

```bash
# Run tests with parallel execution
uv run doit test
# or directly: uv run pytest -n auto -v

# Run tests with coverage report
uv run doit coverage

# Run specific test file
uv run pytest tests/test_example.py -v

# Run specific test function
uv run pytest tests/test_example.py::test_version -v
```

#### Code Quality Tasks

```bash
# Format code (ruff format + ruff check --fix)
uv run doit format

# Check formatting without changes
uv run doit format_check

# Run linting
uv run doit lint

# Run type checking
uv run doit type_check

# Run all checks (format, lint, type check, test)
uv run doit check
```

#### Security Tasks

```bash
# Run security scan with bandit
uv run doit security

# Run dependency vulnerability audit
uv run doit audit

# Check for typos
uv run doit spell_check
```

#### Documentation Tasks

```bash
# Serve docs locally with live reload (http://127.0.0.1:8000)
uv run doit docs_serve

# Build static documentation site
uv run doit docs_build

# Deploy documentation to GitHub Pages
uv run doit docs_deploy
```

#### Pre-commit Tasks

```bash
# Install pre-commit hooks
uv run doit pre_commit_install

# Run pre-commit on all files
uv run doit pre_commit_run

# Or run pre-commit directly
uv run pre-commit run --all-files
```

### Pre-commit Hooks

The project includes pre-commit hooks that run automatically before each commit:

- **ruff** - Code formatting and linting (auto-fixes issues)
- **mypy** - Type checking (strict mode)
- **bandit** - Security vulnerability scanning
- **codespell** - Spell checking
- **trailing-whitespace** - Remove trailing whitespace
- **end-of-file-fixer** - Ensure files end with newline
- **check-yaml** - Validate YAML syntax
- **check-toml** - Validate TOML syntax
- **check-merge-conflict** - Detect merge conflict markers
- **detect-private-key** - Prevent committing private keys

Install hooks after cloning:

```bash
uv run pre-commit install
```

### Making Changes

1. **Create a branch**:
   ```bash
   git checkout -b feature/my-feature
   ```

2. **Make your changes**

3. **Format and check**:
   ```bash
   uv run doit format
   uv run doit check
   ```

4. **Commit** (pre-commit hooks run automatically):
   ```bash
   git add .
   git commit -m "feat: add new feature"
   ```

5. **Push and create PR**:
   ```bash
   git push -u origin feature/my-feature
   ```

### Running CI Locally

To run the same checks that CI runs:

```bash
# Format check (what CI runs)
uv run ruff format --check src/ tests/

# Linting
uv run ruff check src/ tests/

# Type checking
uv run mypy src/

# Tests with coverage
uv run pytest --cov=bastproxy --cov-report=xml:tmp/coverage.xml --cov-report=term -v
```

### Updating Dependencies

```bash
# Show outdated packages
uv pip list --outdated

# Update dependencies and run tests
uv run doit update_deps

# Or manually:
uv pip install --upgrade -e ".[dev,security]"
uv lock
uv run doit check
```

### Building Documentation

#### Local Development

```bash
# Serve with live reload
uv run mkdocs serve

# Or using doit
uv run doit docs_serve
```

Open http://127.0.0.1:8000 in your browser.

#### Switching to Material Theme

The template includes mkdocs-material but uses ReadTheDocs theme by default. To switch:

1. Edit `mkdocs.yml`
2. Change `name: readthedocs` to `name: material`
3. Uncomment the Material theme features
4. Rebuild docs: `uv run doit docs_build`

#### Deploying to GitHub Pages

```bash
# Build and deploy to gh-pages branch
uv run doit docs_deploy
```

This builds the documentation and pushes to the `gh-pages` branch. Enable GitHub Pages in your repository settings to host it.

### Creating a Release

```bash
# Create release tag, changelog, and push (commitizen-powered)
uv run doit release
```

Notes:
- Versions are derived from git tags via hatch-vcs; no manual edits to `pyproject.toml` or `_version.py` are required.
- Use `v*` tags for production (e.g., `v1.0.0`) and prerelease `v*` tags for TestPyPI (e.g., `v1.0.0-alpha.1`). The `doit release` task runs commitizen to choose the next version, update CHANGELOG.md, and create/push the stable `v*` tag; for TestPyPI, run `uv run doit release_dev` to compute the next prerelease via commitizen, create the prerelease `v*` tag, and push.

This will:
1. Verify you're on the main branch
2. Check for uncommitted changes
3. Pull latest changes
4. Run all quality checks
5. Use commitizen to update CHANGELOG.md (merging prerelease entries) and create the `v*` git tag
6. Push the tag
7. Trigger CI/CD to build and publish to PyPI

The release workflow includes:
- ✅ All CI checks (format, lint, type check, tests)
- ✅ Build package artifacts
- ✅ Publish to TestPyPI (for verification)
- ✅ Publish to PyPI (production)

### Environment Configuration

#### Using direnv (Optional)

The project includes `.envrc` for automatic environment setup:

```bash
# Install direnv
uv run doit install_direnv

# Hook into your shell (one-time)
echo 'eval "$(direnv hook bash)"' >> ~/.bashrc
source ~/.bashrc

# Allow direnv in this directory
direnv allow
```

Once configured, direnv automatically:
- Activates the virtual environment
- Sets cache directories (UV_CACHE_DIR, RUFF_CACHE_DIR, etc.)
- Loads project-specific environment variables

#### Manual Environment Setup

Without direnv:

```bash
# Activate virtual environment
source .venv/bin/activate

# Set cache directories (optional)
export UV_CACHE_DIR="$(pwd)/tmp/.uv_cache"
export RUFF_CACHE_DIR="$(pwd)/tmp/.ruff_cache"
export MYPY_CACHE_DIR="$(pwd)/tmp/.mypy_cache"
export COVERAGE_FILE="$(pwd)/tmp/.coverage"
```

### Troubleshooting

#### Tests Failing

```bash
# Run with verbose output
uv run pytest -vv

# Run without parallel execution
uv run pytest -v

# Clear cache and retry
rm -rf .pytest_cache tmp/
uv run pytest -v
```

#### Type Checking Issues

```bash
# Show detailed error information
uv run mypy --show-error-codes --pretty src/

# Check specific file
uv run mypy src/bastproxy/core.py
```

#### Pre-commit Hook Failures

```bash
# Skip hooks (only when absolutely necessary)
git commit --no-verify -m "message"

# Update pre-commit hooks
uv run pre-commit autoupdate

# Clear pre-commit cache
uv run pre-commit clean
```

#### Clean Build

```bash
# Deep clean all artifacts
uv run doit cleanup

# Remove virtual environment and reinstall
rm -rf .venv
uv venv
uv sync --all-extras --dev
uv run pre-commit install
```

## Best Practices

### Code Style

- Follow PEP 8 (enforced by ruff)
- Use type hints for all functions
- Write docstrings for public APIs
- Keep functions small and focused

### Testing

- Write tests for all new features
- Maintain test coverage above 80%
- Use descriptive test names
- Test edge cases and error conditions

### Documentation

- Update docstrings when changing functions
- Add examples for new features
- Update CHANGELOG.md for notable changes
- Keep README.md up to date

### Git Commits

- Use conventional commit messages: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`
- Keep commits atomic and focused
- Write clear commit messages
- Reference issues in commits when applicable

## Next Steps

- Check the [API Reference](api.md) for complete documentation
- Read [CONTRIBUTING.md](https://github.com/endavis/bastproxy/blob/main/.github/CONTRIBUTING.md) for contribution guidelines
- Review the docs and TODOs in this template to identify improvements for your project

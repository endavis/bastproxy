import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
from doit.action import CmdAction
from doit.tools import title_with_actions
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# Configuration
DOIT_CONFIG = {
    "verbosity": 2,
    "default_tasks": ["list"],
}

# Use direnv-managed UV_CACHE_DIR if available, otherwise use tmp/
UV_CACHE_DIR = os.environ.get("UV_CACHE_DIR", "tmp/.uv_cache")


def success_message():
    """Print success message after all checks pass."""
    console = Console()
    console.print()
    console.print(Panel.fit(
        "[bold green]✓ All checks passed![/bold green]",
        border_style="green",
        padding=(1, 2)
    ))
    console.print()


# --- Setup / Install Tasks ---


def task_install():
    """Install package with dependencies."""
    return {
        "actions": [
            f"UV_CACHE_DIR={UV_CACHE_DIR} uv sync",
        ],
        "title": title_with_actions,
    }


def task_dev():
    """Install package with dev dependencies."""
    return {
        "actions": [
            f"UV_CACHE_DIR={UV_CACHE_DIR} uv sync --all-extras --dev",
        ],
        "title": title_with_actions,
    }


def task_sync():
    """Sync virtualenv with all extras and dev deps (alias of dev)."""
    return {
        "actions": [
            f"UV_CACHE_DIR={UV_CACHE_DIR} uv sync --all-extras --dev",
        ],
        "title": title_with_actions,
    }


def task_cleanup():
    """Clean build and cache artifacts (deep clean)."""

    def clean_artifacts():
        console = Console()
        console.print("[bold yellow]Performing deep clean...[/bold yellow]")
        console.print()

        # Remove build artifacts
        console.print("[cyan]Removing build artifacts...[/cyan]")
        dirs = [
            "build",
            "dist",
            ".eggs",
            "__pycache__",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
        ]
        for d in dirs:
            if os.path.exists(d):
                console.print(f"  [dim]Removing {d}...[/dim]")
                if os.path.isdir(d):
                    shutil.rmtree(d)
                else:
                    os.remove(d)

        # Remove *.egg-info directories
        for item in os.listdir("."):
            if item.endswith(".egg-info") and os.path.isdir(item):
                console.print(f"  [dim]Removing {item}...[/dim]")
                shutil.rmtree(item)

        # Clear tmp/ directory but keep the directory and .gitkeep
        console.print("[cyan]Clearing tmp/ directory...[/cyan]")
        if os.path.exists("tmp"):
            for item in os.listdir("tmp"):
                if item != ".gitkeep":
                    path = os.path.join("tmp", item)
                    if os.path.isdir(path):
                        shutil.rmtree(path)
                    else:
                        os.remove(path)
        else:
            os.makedirs("tmp", exist_ok=True)

        # Ensure .gitkeep exists
        gitkeep = os.path.join("tmp", ".gitkeep")
        if not os.path.exists(gitkeep):
            open(gitkeep, "a").close()

        # Recursive removal of Python cache
        console.print("[cyan]Removing Python cache files...[/cyan]")
        for root, dirs_list, files in os.walk("."):
            # Skip .venv directory
            if ".venv" in dirs_list:
                dirs_list.remove(".venv")

            for d in dirs_list:
                if d == "__pycache__":
                    full_path = os.path.join(root, d)
                    console.print(f"  [dim]Removing {full_path}...[/dim]")
                    shutil.rmtree(full_path)

            for f in files:
                if f.endswith((".pyc", ".pyo")) or f.startswith(".coverage"):
                    full_path = os.path.join(root, f)
                    console.print(f"  [dim]Removing {full_path}...[/dim]")
                    os.remove(full_path)

        console.print()
        console.print(Panel.fit(
            "[bold green]✓ Deep clean complete![/bold green]",
            border_style="green",
            padding=(1, 2)
        ))

    return {
        "actions": [clean_artifacts],
        "title": title_with_actions,
    }


# --- Development Tasks ---


def task_test():
    """Run pytest with parallel execution."""
    return {
        "actions": [f"UV_CACHE_DIR={UV_CACHE_DIR} uv run pytest -n auto -v"],
        "title": title_with_actions,
    }


def task_coverage():
    """Run pytest with coverage (note: parallel execution disabled for accurate coverage)."""
    return {
        "actions": [
            f"UV_CACHE_DIR={UV_CACHE_DIR} uv run pytest "
            "--cov=bastproxy --cov-report=term-missing "
            "--cov-report=html:tmp/htmlcov --cov-report=xml:tmp/coverage.xml -v"
        ],
        "title": title_with_actions,
    }


def task_lint():
    """Run ruff linting."""
    return {
        "actions": [f"UV_CACHE_DIR={UV_CACHE_DIR} uv run ruff check src/ tests/"],
        "title": title_with_actions,
    }


def task_format():
    """Format code with ruff."""
    return {
        "actions": [
            f"UV_CACHE_DIR={UV_CACHE_DIR} uv run ruff format src/ tests/",
            f"UV_CACHE_DIR={UV_CACHE_DIR} uv run ruff check --fix src/ tests/",
        ],
        "title": title_with_actions,
    }


def task_format_check():
    """Check code formatting without modifying files."""
    return {
        "actions": [f"UV_CACHE_DIR={UV_CACHE_DIR} uv run ruff format --check src/ tests/"],
        "title": title_with_actions,
    }


def task_type_check():
    """Run mypy type checking."""
    return {
        "actions": [f"UV_CACHE_DIR={UV_CACHE_DIR} uv run mypy src/"],
        "title": title_with_actions,
    }


def task_check():
    """Run all checks (format, lint, type check, test)."""
    return {
        "actions": [success_message],
        "task_dep": ["format_check", "lint", "type_check", "test"],
        "title": title_with_actions,
    }


def task_audit():
    """Run security audit with pip-audit (requires security extras)."""
    return {
        "actions": [
            f"UV_CACHE_DIR={UV_CACHE_DIR} uv run pip-audit || "
            "echo 'pip-audit not installed. Run: uv sync --extra security'"
        ],
        "title": title_with_actions,
    }


def task_security():
    """Run security checks with bandit and safety (requires security extras)."""
    return {
        "actions": [
            f"UV_CACHE_DIR={UV_CACHE_DIR} uv run bandit -c pyproject.toml -r src/ || "
            "echo 'bandit not installed. Run: uv sync --extra security'",
            f"UV_CACHE_DIR={UV_CACHE_DIR} uv run safety check || "
            "echo 'safety not installed. Run: uv sync --extra security'",
        ],
        "title": title_with_actions,
    }


def task_spell_check():
    """Check spelling in code and documentation."""
    return {
        "actions": [f"UV_CACHE_DIR={UV_CACHE_DIR} uv run codespell src/ tests/ docs/ README.md"],
        "title": title_with_actions,
    }


def task_fmt_pyproject():
    """Format pyproject.toml with pyproject-fmt."""
    return {
        "actions": [f"UV_CACHE_DIR={UV_CACHE_DIR} uv run pyproject-fmt pyproject.toml"],
        "title": title_with_actions,
    }


def task_licenses():
    """Check licenses of dependencies (requires security extras)."""
    return {
        "actions": [
            f"UV_CACHE_DIR={UV_CACHE_DIR} uv run pip-licenses --format=markdown --order=license || "
            "echo 'pip-licenses not installed. Run: uv sync --extra security'"
        ],
        "title": title_with_actions,
    }


def task_commit():
    """Interactive commit with commitizen (ensures conventional commit format)."""
    return {
        "actions": [
            f"UV_CACHE_DIR={UV_CACHE_DIR} uv run cz commit || "
            "echo 'commitizen not installed. Run: uv sync'"
        ],
        "title": title_with_actions,
    }


def task_bump():
    """Bump version automatically based on conventional commits."""
    return {
        "actions": [
            f"UV_CACHE_DIR={UV_CACHE_DIR} uv run cz bump || "
            "echo 'commitizen not installed. Run: uv sync'"
        ],
        "title": title_with_actions,
    }


def task_changelog():
    """Generate CHANGELOG from conventional commits."""
    return {
        "actions": [
            f"UV_CACHE_DIR={UV_CACHE_DIR} uv run cz changelog || "
            "echo 'commitizen not installed. Run: uv sync'"
        ],
        "title": title_with_actions,
    }


def task_pre_commit_install():
    """Install pre-commit hooks."""
    return {
        "actions": [f"UV_CACHE_DIR={UV_CACHE_DIR} uv run pre-commit install"],
        "title": title_with_actions,
    }


def task_pre_commit_run():
    """Run pre-commit on all files."""
    return {
        "actions": [f"UV_CACHE_DIR={UV_CACHE_DIR} uv run pre-commit run --all-files"],
        "title": title_with_actions,
    }


# --- Documentation Tasks ---


def task_docs_serve():
    """Serve documentation locally with live reload."""
    return {
        "actions": [f"UV_CACHE_DIR={UV_CACHE_DIR} uv run mkdocs serve"],
        "title": title_with_actions,
    }


def task_docs_build():
    """Build documentation site."""
    return {
        "actions": [f"UV_CACHE_DIR={UV_CACHE_DIR} uv run mkdocs build"],
        "title": title_with_actions,
    }


def task_docs_deploy():
    """Deploy documentation to GitHub Pages."""
    return {
        "actions": [f"UV_CACHE_DIR={UV_CACHE_DIR} uv run mkdocs gh-deploy --force"],
        "title": title_with_actions,
    }


def task_update_deps():
    """Update dependencies and run tests to verify."""

    def update_dependencies():
        console = Console()
        console.print()
        console.print(Panel.fit(
            "[bold cyan]Updating Dependencies[/bold cyan]",
            border_style="cyan"
        ))
        console.print()

        print("Checking for outdated dependencies...")
        print()
        subprocess.run(
            f"UV_CACHE_DIR={UV_CACHE_DIR} uv pip list --outdated",
            shell=True,
            check=False,
        )

        print()
        print("=" * 70)
        print("Updating all dependencies (including extras)...")
        print("=" * 70)
        print()

        # Update dependencies and refresh lockfile
        result = subprocess.run(
            f"UV_CACHE_DIR={UV_CACHE_DIR} uv sync --all-extras --dev --upgrade",
            shell=True,
        )

        if result.returncode != 0:
            print("\n❌ Dependency update failed!")
            sys.exit(1)

        print()
        print("=" * 70)
        print("Running tests to verify updates...")
        print("=" * 70)
        print()

        # Run all checks
        check_result = subprocess.run("doit check", shell=True)

        print()
        if check_result.returncode == 0:
            print("=" * 70)
            print(" " * 20 + "✓ All checks passed!")
            print("=" * 70)
            print()
            print("Next steps:")
            print("1. Review the changes: git diff pyproject.toml")
            print("2. Test thoroughly")
            print("3. Commit the updated dependencies")
        else:
            print("=" * 70)
            print("⚠ Warning: Some checks failed after update")
            print("=" * 70)
            print()
            print("You may need to:")
            print("1. Fix compatibility issues")
            print("2. Update code for breaking changes")
            print("3. Revert problematic updates")
            sys.exit(1)

    return {
        "actions": [update_dependencies],
        "title": title_with_actions,
    }


def task_release_dev(type="alpha"):
    """Create a pre-release (alpha/beta) tag for TestPyPI and push to GitHub.

    Args:
        type (str): Pre-release type (e.g., 'alpha', 'beta', 'rc'). Defaults to 'alpha'.
    """

    def create_dev_release():
        console = Console()
        console.print("=" * 70)
        console.print(f"[bold green]Starting {type} release tagging...[/bold green]")
        console.print("=" * 70)
        console.print()

        # Check if on main branch
        current_branch = subprocess.getoutput("git branch --show-current").strip()
        if current_branch != "main":
            console.print(f"[bold yellow]⚠ Warning: Not on main branch (currently on {current_branch})[/bold yellow]")
            response = input("Continue anyway? (y/N) ").strip().lower()
            if response != "y":
                console.print("[bold red]❌ Release cancelled.[/bold red]")
                sys.exit(1)

        # Check for uncommitted changes
        status = subprocess.getoutput("git status -s").strip()
        if status:
            console.print("[bold red]❌ Error: Uncommitted changes detected.[/bold red]")
            console.print(status)
            sys.exit(1)

        # Pull latest changes
        console.print("\n[cyan]Pulling latest changes...[/cyan]")
        try:
            subprocess.run("git pull", shell=True, check=True, capture_output=True, text=True)
            console.print("[green]✓ Git pull successful.[/green]")
        except subprocess.CalledProcessError as e:
            console.print(f"[bold red]❌ Error pulling latest changes:[/bold red]")
            console.print(f"[red]Stdout: {e.stdout}[/red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            sys.exit(1)

        # Run checks
        console.print("\n[cyan]Running all pre-release checks...[/cyan]")
        try:
            subprocess.run("doit check", shell=True, check=True, capture_output=True, text=True)
            console.print("[green]✓ All checks passed.[/green]")
        except subprocess.CalledProcessError as e:
            console.print("[bold red]❌ Pre-release checks failed! Please fix issues before tagging.[/bold red]")
            console.print(f"[red]Stdout: {e.stdout}[/red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            sys.exit(1)

        # Automated version bump and tagging
        console.print(f"\n[cyan]Bumping version ({type}) and updating changelog...[/cyan]")
        try:
            # Use cz bump --prerelease <type> --changelog
            result = subprocess.run(
                f"UV_CACHE_DIR={UV_CACHE_DIR} uv run cz bump --prerelease {type} --changelog",
                shell=True, check=True, capture_output=True, text=True
            )
            console.print(f"[green]✓ Version bumped to {type}.[/green]")
            console.print(f"[dim]{result.stdout}[/dim]")
            # Extract new version
            version_match = Text(result.stdout).search(r"Bumping to version (\d+\.\d+\.\d+[^\s]*)")
            if version_match:
                new_version = version_match.group(1)
            else:
                new_version = "unknown"

        except subprocess.CalledProcessError as e:
            console.print("[bold red]❌ commitizen bump failed![/bold red]")
            console.print(f"[red]Stdout: {e.stdout}[/red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            sys.exit(1)

        console.print(f"\n[cyan]Pushing tag v{new_version} to origin...[/cyan]")
        try:
            subprocess.run(f"git push --follow-tags origin {current_branch}", shell=True, check=True, capture_output=True, text=True)
            console.print("[green]✓ Tags pushed to origin.[/green]")
        except subprocess.CalledProcessError as e:
            console.print("[bold red]❌ Error pushing tag to origin:[/bold red]")
            console.print(f"[red]Stdout: {e.stdout}[/red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            sys.exit(1)

        console.print("\n" + "=" * 70)
        console.print(f"[bold green]✓ Development release {new_version} complete![/bold green]")
        console.print("=" * 70)
        console.print("\nNext steps:")
        console.print("1. Monitor GitHub Actions (testpypi.yml) for the TestPyPI publish.")
        console.print("2. Verify on TestPyPI once the workflow completes.")

    return {
        "actions": [create_dev_release],
        "params": [
            {
                "name": "type",
                "short": "t",
                "long": "type",
                "default": "alpha",
                "help": "Pre-release type (alpha, beta, rc)",
            }
        ],
        "title": title_with_actions,
    }


def task_release():
    """Automate release: bump version, update CHANGELOG, and push to GitHub (triggers CI/CD)."""

    def automated_release():
        console = Console()
        console.print("=" * 70)
        console.print("[bold green]Starting automated release process...[/bold green]")
        console.print("=" * 70)
        console.print()

        # Check if on main branch
        current_branch = subprocess.getoutput("git branch --show-current").strip()
        if current_branch != "main":
            console.print(f"[bold yellow]⚠ Warning: Not on main branch (currently on {current_branch})[/bold yellow]")
            response = input("Continue anyway? (y/N) ").strip().lower()
            if response != "y":
                console.print("[bold red]❌ Release cancelled.[/bold red]")
                sys.exit(1)

        # Check for uncommitted changes
        status = subprocess.getoutput("git status -s").strip()
        if status:
            console.print("[bold red]❌ Error: Uncommitted changes detected.[/bold red]")
            console.print(status)
            sys.exit(1)

        # Pull latest changes
        console.print("\n[cyan]Pulling latest changes...[/cyan]")
        try:
            subprocess.run("git pull", shell=True, check=True, capture_output=True, text=True)
            console.print("[green]✓ Git pull successful.[/green]")
        except subprocess.CalledProcessError as e:
            console.print(f"[bold red]❌ Error pulling latest changes:[/bold red]")
            console.print(f"[red]Stdout: {e.stdout}[/red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            sys.exit(1)

        # Run all checks
        console.print("\n[cyan]Running all pre-release checks...[/cyan]")
        try:
            subprocess.run("doit check", shell=True, check=True, capture_output=True, text=True)
            console.print("[green]✓ All checks passed.[/green]")
        except subprocess.CalledProcessError as e:
            console.print("[bold red]❌ Pre-release checks failed! Please fix issues before releasing.[/bold red]")
            console.print(f"[red]Stdout: {e.stdout}[/red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            sys.exit(1)

        # Automated version bump and CHANGELOG generation using commitizen
        console.print("\n[cyan]Bumping version and generating CHANGELOG with commitizen...[/cyan]")
        try:
            # Use cz bump --changelog --merge-prerelease to update version, changelog, commit, and tag
            # This consolidates pre-release changes into the final release entry
            result = subprocess.run(
                f"UV_CACHE_DIR={UV_CACHE_DIR} uv run cz bump --changelog --merge-prerelease",
                shell=True, check=True, capture_output=True, text=True
            )
            console.print("[green]✓ Version bumped and CHANGELOG updated (merged pre-releases).[/green]")
            console.print(f"[dim]{result.stdout}[/dim]")
            # Extract new version from cz output (example: "Bumping to version 1.0.0")
            version_match = Text(result.stdout).search(r"Bumping to version (\d+\.\d+\.\d+)")
            if version_match:
                new_version = version_match.group(1)
            else:
                new_version = "unknown" # Fallback if regex fails

        except subprocess.CalledProcessError as e:
            console.print("[bold red]❌ commitizen bump failed! Ensure your commit history is conventional.[/bold red]")
            console.print(f"[red]Stdout: {e.stdout}[/red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            sys.exit(1)
        except Exception as e:
            console.print(f"[bold red]❌ An unexpected error occurred during commitizen bump: {e}[/bold red]")
            sys.exit(1)

        # Push commits and tags to GitHub
        console.print("\n[cyan]Pushing commits and tags to GitHub...[/cyan]")
        try:
            subprocess.run(f"git push --follow-tags origin {current_branch}", shell=True, check=True, capture_output=True, text=True)
            console.print("[green]✓ Pushed new commits and tags to GitHub.[/green]")
        except subprocess.CalledProcessError as e:
            console.print("[bold red]❌ Error pushing to GitHub:[/bold red]")
            console.print(f"[red]Stdout: {e.stdout}[/red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            sys.exit(1)

        console.print("\n" + "=" * 70)
        console.print(f"[bold green]✓ Automated release {new_version} complete![/bold green]")
        console.print("=" * 70)
        console.print("\nNext steps:")
        console.print("1. Monitor GitHub Actions for build and publish.")
        console.print("2. Check TestPyPI: [link=https://test.pypi.org/project/bastproxy/]https://test.pypi.org/project/bastproxy/[/link]")
        console.print("3. Check PyPI: [link=https://pypi.org/project/bastproxy/]https://pypi.org/project/bastproxy/[/link]")
        console.print("4. Verify the updated CHANGELOG.md in the repository.")

    return {
        "actions": [automated_release],
        "title": title_with_actions,
    }


# --- Build & Publish Tasks ---


def task_build():
    """Build package."""
    return {
        "actions": [f"UV_CACHE_DIR={UV_CACHE_DIR} uv build"],
        "title": title_with_actions,
    }


def task_publish():
    """Build and publish package to PyPI."""

    def publish_cmd():
        token = os.environ.get("PYPI_TOKEN")
        if not token:
            raise RuntimeError("PYPI_TOKEN environment variable must be set.")
        return f"UV_CACHE_DIR={UV_CACHE_DIR} uv publish --token '{token}'"

    return {
        "actions": [f"UV_CACHE_DIR={UV_CACHE_DIR} uv build", CmdAction(publish_cmd)],
        "title": title_with_actions,
    }


# --- Installation Helper Tasks ---


def _get_latest_github_release(repo):
    """Helper to get latest GitHub release version."""
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    request = urllib.request.Request(url)

    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        request.add_header("Authorization", f"token {github_token}")

    with urllib.request.urlopen(request) as response:
        data = json.loads(response.read().decode())
        return data["tag_name"].lstrip("v")


def _install_direnv():
    """Install direnv if not already installed."""
    if shutil.which("direnv"):
        print(f"✓ direnv already installed: {subprocess.getoutput('direnv --version')}")
        return

    print("Installing direnv...")
    version = _get_latest_github_release("direnv/direnv")
    print(f"Latest version: {version}")

    system = platform.system().lower()
    install_dir = os.path.expanduser("~/.local/bin")
    if not os.path.exists(install_dir):
        os.makedirs(install_dir, exist_ok=True)

    if system == "linux":
        bin_url = (
            f"https://github.com/direnv/direnv/releases/download/"
            f"v{version}/direnv.linux-amd64"
        )
        bin_path = os.path.join(install_dir, "direnv")
        print(f"Downloading {bin_url}...")
        urllib.request.urlretrieve(bin_url, bin_path)
        subprocess.run(f"chmod +x {bin_path}", shell=True, check=True)
    elif system == "darwin":
        subprocess.run("brew install direnv", shell=True, check=True)
    else:
        print(f"Unsupported OS: {system}")
        sys.exit(1)

    print("✓ direnv installed.")
    print("\nIMPORTANT: Add direnv hook to your shell:")
    print('  Bash: echo \'eval "$(direnv hook bash)"\' >> ~/.bashrc')
    print('  Zsh:  echo \'eval "$(direnv hook zsh)"\' >> ~/.zshrc')


def task_install_direnv():
    """Install direnv for automatic environment loading."""
    return {
        "actions": [_install_direnv],
        "title": title_with_actions,
    }

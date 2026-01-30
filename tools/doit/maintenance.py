"""Maintenance-related doit tasks."""

import os
import shutil
import subprocess  # nosec B404 - subprocess is required for doit tasks
import sys
from typing import Any

from doit.tools import title_with_actions
from rich.console import Console
from rich.panel import Panel

from .base import UV_CACHE_DIR


def task_cleanup() -> dict[str, Any]:
    """Clean build and cache artifacts (deep clean)."""

    def clean_artifacts() -> None:
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
        console.print(
            Panel.fit(
                "[bold green]\u2713 Deep clean complete![/bold green]",
                border_style="green",
                padding=(1, 2),
            )
        )

    return {
        "actions": [clean_artifacts],
        "title": title_with_actions,
    }


def task_update_deps() -> dict[str, Any]:
    """Update dependencies and run tests to verify."""

    def update_dependencies() -> None:
        console = Console()
        console.print()
        console.print(
            Panel.fit(
                "[bold cyan]Updating Dependencies[/bold cyan]", border_style="cyan"
            )
        )
        console.print()

        print("Checking for outdated dependencies...")
        print()
        subprocess.run(
            ["uv", "pip", "list", "--outdated"],
            env={**os.environ, "UV_CACHE_DIR": UV_CACHE_DIR},
            check=False,
        )

        print()
        print("=" * 70)
        print("Updating all dependencies (including extras)...")
        print("=" * 70)
        print()

        # Update dependencies and refresh lockfile
        result = subprocess.run(
            ["uv", "sync", "--all-extras", "--dev", "--upgrade"],
            check=False,
            env={**os.environ, "UV_CACHE_DIR": UV_CACHE_DIR},
        )

        if result.returncode != 0:
            print("\n\u274c Dependency update failed!")
            sys.exit(1)

        print()
        print("=" * 70)
        print("Running tests to verify updates...")
        print("=" * 70)
        print()

        # Run all checks
        check_result = subprocess.run(["doit", "check"], check=False)

        print()
        if check_result.returncode == 0:
            print("=" * 70)
            print(" " * 20 + "\u2713 All checks passed!")
            print("=" * 70)
            print()
            print("Next steps:")
            print("1. Review the changes: git diff pyproject.toml")
            print("2. Test thoroughly")
            print("3. Commit the updated dependencies")
        else:
            print("=" * 70)
            print("\u26a0 Warning: Some checks failed after update")
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


def task_fmt_pyproject() -> dict[str, Any]:
    """Format pyproject.toml with pyproject-fmt."""
    return {
        "actions": ["uv run pyproject-fmt pyproject.toml"],
        "title": title_with_actions,
    }

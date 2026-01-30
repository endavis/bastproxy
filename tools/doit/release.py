"""Release-related doit tasks."""

import os
import re
import subprocess  # nosec B404 - subprocess is required for doit tasks
import sys
from typing import Any

from doit.tools import title_with_actions
from rich.console import Console

from .base import UV_CACHE_DIR


def task_release_dev(type: str = "alpha") -> dict[str, Any]:
    """Create a pre-release (alpha/beta) tag for TestPyPI and push to GitHub.

    Args:
        type (str): Pre-release type (e.g., 'alpha', 'beta', 'rc'). Defaults to 'alpha'.
    """

    def create_dev_release() -> None:
        console = Console()
        console.print("=" * 70)
        console.print(f"[bold green]Starting {type} release tagging...[/bold green]")
        console.print("=" * 70)
        console.print()

        # Check if on main branch
        current_branch = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        if current_branch != "main":
            console.print(
                f"[bold yellow]\u26a0 Warning: Not on main branch "
                f"(currently on {current_branch})[/bold yellow]"
            )
            response = input("Continue anyway? (y/N) ").strip().lower()
            if response != "y":
                console.print("[bold red]\u274c Release cancelled.[/bold red]")
                sys.exit(1)

        # Check for uncommitted changes
        status = subprocess.run(
            ["git", "status", "-s"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        if status:
            console.print(
                "[bold red]\u274c Error: Uncommitted changes detected.[/bold red]"
            )
            console.print(status)
            sys.exit(1)

        # Pull latest changes
        console.print("\n[cyan]Pulling latest changes...[/cyan]")
        try:
            subprocess.run(["git", "pull"], check=True, capture_output=True, text=True)
            console.print("[green]\u2713 Git pull successful.[/green]")
        except subprocess.CalledProcessError as e:
            console.print("[bold red]\u274c Error pulling latest changes:[/bold red]")
            console.print(f"[red]Stdout: {e.stdout}[/red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            sys.exit(1)

        # Run checks
        console.print("\n[cyan]Running all pre-release checks...[/cyan]")
        try:
            subprocess.run(
                ["doit", "check"], check=True, capture_output=True, text=True
            )
            console.print("[green]\u2713 All checks passed.[/green]")
        except subprocess.CalledProcessError as e:
            console.print(
                "[bold red]\u274c Pre-release checks failed! "
                "Please fix issues before tagging.[/bold red]"
            )
            console.print(f"[red]Stdout: {e.stdout}[/red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            sys.exit(1)

        # Automated version bump and tagging
        console.print(
            f"\n[cyan]Bumping version ({type}) and updating changelog...[/cyan]"
        )
        try:
            # Use cz bump --prerelease <type> --changelog
            result = subprocess.run(
                ["uv", "run", "cz", "bump", "--prerelease", type, "--changelog"],
                env={**os.environ, "UV_CACHE_DIR": UV_CACHE_DIR},
                check=True,
                capture_output=True,
                text=True,
            )
            console.print(f"[green]\u2713 Version bumped to {type}.[/green]")
            console.print(f"[dim]{result.stdout}[/dim]")
            # Extract new version
            version_match = re.search(
                r"Bumping to version (\d+\.\d+\.\d+[^\s]*)", result.stdout
            )
            new_version = version_match.group(1) if version_match else "unknown"

        except subprocess.CalledProcessError as e:
            console.print("[bold red]\u274c commitizen bump failed![/bold red]")
            console.print(f"[red]Stdout: {e.stdout}[/red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            sys.exit(1)

        console.print(f"\n[cyan]Pushing tag v{new_version} to origin...[/cyan]")
        try:
            subprocess.run(
                ["git", "push", "--follow-tags", "origin", current_branch],
                check=True,
                capture_output=True,
                text=True,
            )
            console.print("[green]\u2713 Tags pushed to origin.[/green]")
        except subprocess.CalledProcessError as e:
            console.print("[bold red]\u274c Error pushing tag to origin:[/bold red]")
            console.print(f"[red]Stdout: {e.stdout}[/red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            sys.exit(1)

        console.print("\n" + "=" * 70)
        console.print(
            f"[bold green]\u2713 Development release {new_version} complete![/bold green]"
        )
        console.print("=" * 70)
        console.print("\nNext steps:")
        console.print(
            "1. Monitor GitHub Actions (testpypi.yml) for the TestPyPI publish."
        )
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


def task_release() -> dict[str, Any]:
    """Automate release: bump version, update CHANGELOG, and push to GitHub (triggers CI/CD)."""

    def automated_release() -> None:
        console = Console()
        console.print("=" * 70)
        console.print("[bold green]Starting automated release process...[/bold green]")
        console.print("=" * 70)
        console.print()

        # Check if on main branch
        current_branch = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        if current_branch != "main":
            console.print(
                f"[bold yellow]\u26a0 Warning: Not on main branch "
                f"(currently on {current_branch})[/bold yellow]"
            )
            response = input("Continue anyway? (y/N) ").strip().lower()
            if response != "y":
                console.print("[bold red]\u274c Release cancelled.[/bold red]")
                sys.exit(1)

        # Check for uncommitted changes
        status = subprocess.run(
            ["git", "status", "-s"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        if status:
            console.print(
                "[bold red]\u274c Error: Uncommitted changes detected.[/bold red]"
            )
            console.print(status)
            sys.exit(1)

        # Pull latest changes
        console.print("\n[cyan]Pulling latest changes...[/cyan]")
        try:
            subprocess.run(["git", "pull"], check=True, capture_output=True, text=True)
            console.print("[green]\u2713 Git pull successful.[/green]")
        except subprocess.CalledProcessError as e:
            console.print("[bold red]\u274c Error pulling latest changes:[/bold red]")
            console.print(f"[red]Stdout: {e.stdout}[/red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            sys.exit(1)

        # Run all checks
        console.print("\n[cyan]Running all pre-release checks...[/cyan]")
        try:
            subprocess.run(
                ["doit", "check"], check=True, capture_output=True, text=True
            )
            console.print("[green]\u2713 All checks passed.[/green]")
        except subprocess.CalledProcessError as e:
            console.print(
                "[bold red]\u274c Pre-release checks failed! "
                "Please fix issues before releasing.[/bold red]"
            )
            console.print(f"[red]Stdout: {e.stdout}[/red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            sys.exit(1)

        # Automated version bump and CHANGELOG generation using commitizen
        console.print(
            "\n[cyan]Bumping version and generating CHANGELOG with commitizen...[/cyan]"
        )
        try:
            # Use cz bump --changelog --merge-prerelease to update version,
            # changelog, commit, and tag. This consolidates pre-release changes
            # into the final release entry
            result = subprocess.run(
                ["uv", "run", "cz", "bump", "--changelog", "--merge-prerelease"],
                env={**os.environ, "UV_CACHE_DIR": UV_CACHE_DIR},
                check=True,
                capture_output=True,
                text=True,
            )
            console.print(
                "[green]\u2713 Version bumped and CHANGELOG updated (merged pre-releases).[/green]"
            )
            console.print(f"[dim]{result.stdout}[/dim]")
            # Extract new version from cz output (example: "Bumping to version 1.0.0")
            version_match = re.search(
                r"Bumping to version (\d+\.\d+\.\d+)", result.stdout
            )
            # Fallback to "unknown" if regex fails
            new_version = version_match.group(1) if version_match else "unknown"

        except subprocess.CalledProcessError as e:
            console.print(
                "[bold red]\u274c commitizen bump failed! "
                "Ensure your commit history is conventional.[/bold red]"
            )
            console.print(f"[red]Stdout: {e.stdout}[/red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            sys.exit(1)
        except Exception as e:
            console.print(
                f"[bold red]\u274c An unexpected error occurred during commitizen bump: {e}[/bold red]"
            )
            sys.exit(1)

        # Push commits and tags to GitHub
        console.print("\n[cyan]Pushing commits and tags to GitHub...[/cyan]")
        try:
            subprocess.run(
                ["git", "push", "--follow-tags", "origin", current_branch],
                check=True,
                capture_output=True,
                text=True,
            )
            console.print(
                "[green]\u2713 Pushed new commits and tags to GitHub.[/green]"
            )
        except subprocess.CalledProcessError as e:
            console.print("[bold red]\u274c Error pushing to GitHub:[/bold red]")
            console.print(f"[red]Stdout: {e.stdout}[/red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            sys.exit(1)

        console.print("\n" + "=" * 70)
        console.print(
            f"[bold green]\u2713 Automated release {new_version} complete![/bold green]"
        )
        console.print("=" * 70)
        console.print("\nNext steps:")
        console.print("1. Monitor GitHub Actions for build and publish.")
        console.print(
            "2. Check TestPyPI: [link=https://test.pypi.org/project/bastproxy/]https://test.pypi.org/project/bastproxy/[/link]"
        )
        console.print(
            "3. Check PyPI: [link=https://pypi.org/project/bastproxy/]https://pypi.org/project/bastproxy/[/link]"
        )
        console.print("4. Verify the updated CHANGELOG.md in the repository.")

    return {
        "actions": [automated_release],
        "title": title_with_actions,
    }

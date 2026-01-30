"""Release-related doit tasks."""

import json
import os
import re
import subprocess  # nosec B404 - subprocess is required for doit tasks
import sys
from typing import TYPE_CHECKING, Any

from doit.tools import title_with_actions
from rich.console import Console

from .base import UV_CACHE_DIR

if TYPE_CHECKING:
    from rich.console import Console as ConsoleType


def validate_merge_commits(console: "ConsoleType") -> bool:
    """Validate that all merge commits follow the required format.

    Returns:
        bool: True if all merge commits are valid, False otherwise.
    """
    console.print("\n[cyan]Validating merge commit format...[/cyan]")

    # Get merge commits since last tag (or all if no tags)
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            capture_output=True,
            text=True,
        )
        last_tag = result.stdout.strip() if result.returncode == 0 else ""
        range_spec = f"{last_tag}..HEAD" if last_tag else "HEAD"

        result = subprocess.run(
            ["git", "log", "--merges", "--pretty=format:%h %s", range_spec],
            capture_output=True,
            text=True,
        )
        merge_commits = result.stdout.strip().split("\n") if result.stdout.strip() else []

    except Exception as e:
        console.print(f"[yellow]⚠ Could not check merge commits: {e}[/yellow]")
        return True  # Don't block on this check

    if not merge_commits or merge_commits == [""]:
        console.print("[green]✓ No merge commits to validate.[/green]")
        return True

    # Pattern: <type>: <subject> (merges PR #XX, closes #YY) or (merges PR #XX)
    merge_pattern = re.compile(
        r"^[a-f0-9]+\s+(feat|fix|refactor|docs|test|chore|ci|perf):\s.+\s"
        r"\(merges PR #\d+(?:, closes #\d+)?\)$"
    )

    invalid_commits = []
    for commit in merge_commits:
        if commit and not merge_pattern.match(commit):
            invalid_commits.append(commit)

    if invalid_commits:
        console.print("[bold red]❌ Invalid merge commit format found:[/bold red]")
        for commit in invalid_commits:
            console.print(f"  [red]{commit}[/red]")
        console.print("\n[yellow]Expected format:[/yellow]")
        console.print("  <type>: <subject> (merges PR #XX, closes #YY)")
        console.print("  <type>: <subject> (merges PR #XX)")
        return False

    console.print("[green]✓ All merge commits follow required format.[/green]")
    return True


def validate_issue_links(console: "ConsoleType") -> bool:
    """Validate that commits (except docs) reference issues.

    Returns:
        bool: True if validation passes, False otherwise.
    """
    console.print("\n[cyan]Validating issue links in commits...[/cyan]")

    try:
        # Get commits since last tag
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            capture_output=True,
            text=True,
        )
        last_tag = result.stdout.strip() if result.returncode == 0 else ""
        # If no tags, check last 10 commits
        range_spec = f"{last_tag}..HEAD" if last_tag else "HEAD~10..HEAD"

        result = subprocess.run(
            ["git", "log", "--pretty=format:%h %s", range_spec],
            capture_output=True,
            text=True,
        )
        commits = result.stdout.strip().split("\n") if result.stdout.strip() else []

    except Exception as e:
        console.print(f"[yellow]⚠ Could not check issue links: {e}[/yellow]")
        return True  # Don't block on this check

    if not commits or commits == [""]:
        console.print("[green]✓ No commits to validate.[/green]")
        return True

    issue_pattern = re.compile(r"#\d+")
    docs_pattern = re.compile(r"^[a-f0-9]+\s+docs:", re.IGNORECASE)

    commits_without_issues = []
    for commit in commits:
        if commit:
            # Skip docs commits
            if docs_pattern.match(commit):
                continue
            # Skip merge commits (already validated separately)
            if "merge" in commit.lower():
                continue
            # Check for issue reference
            if not issue_pattern.search(commit):
                commits_without_issues.append(commit)

    if commits_without_issues:
        console.print("[bold yellow]⚠ Warning: Some commits don't reference issues:[/bold yellow]")
        for commit in commits_without_issues[:5]:  # Show first 5
            console.print(f"  [yellow]{commit}[/yellow]")
        if len(commits_without_issues) > 5:
            console.print(f"  [dim]...and {len(commits_without_issues) - 5} more[/dim]")
        console.print("\n[dim]This is a warning only - release can continue.[/dim]")
        console.print("[dim]Consider linking commits to issues for better traceability.[/dim]")
    else:
        console.print("[green]✓ All non-docs commits reference issues.[/green]")

    return True  # Warning only, don't block release


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
                f"[bold yellow]⚠ Warning: Not on main branch "
                f"(currently on {current_branch})[/bold yellow]"
            )
            response = input("Continue anyway? (y/N) ").strip().lower()
            if response != "y":
                console.print("[bold red]❌ Release cancelled.[/bold red]")
                sys.exit(1)

        # Check for uncommitted changes
        status = subprocess.run(
            ["git", "status", "-s"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        if status:
            console.print("[bold red]❌ Error: Uncommitted changes detected.[/bold red]")
            console.print(status)
            sys.exit(1)

        # Pull latest changes
        console.print("\n[cyan]Pulling latest changes...[/cyan]")
        try:
            subprocess.run(["git", "pull"], check=True, capture_output=True, text=True)
            console.print("[green]✓ Git pull successful.[/green]")
        except subprocess.CalledProcessError as e:
            console.print("[bold red]❌ Error pulling latest changes:[/bold red]")
            console.print(f"[red]Stdout: {e.stdout}[/red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            sys.exit(1)

        # Run checks
        console.print("\n[cyan]Running all pre-release checks...[/cyan]")
        try:
            subprocess.run(["doit", "check"], check=True, capture_output=True, text=True)
            console.print("[green]✓ All checks passed.[/green]")
        except subprocess.CalledProcessError as e:
            console.print(
                "[bold red]❌ Pre-release checks failed! "
                "Please fix issues before tagging.[/bold red]"
            )
            console.print(f"[red]Stdout: {e.stdout}[/red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            sys.exit(1)

        # Automated version bump and tagging
        console.print(f"\n[cyan]Bumping version ({type}) and updating changelog...[/cyan]")
        try:
            # Use cz bump --prerelease <type> --changelog
            result = subprocess.run(
                ["uv", "run", "cz", "bump", "--prerelease", type, "--changelog"],
                env={**os.environ, "UV_CACHE_DIR": UV_CACHE_DIR},
                check=True,
                capture_output=True,
                text=True,
            )
            console.print(f"[green]✓ Version bumped to {type}.[/green]")
            console.print(f"[dim]{result.stdout}[/dim]")
            # Extract new version
            version_match = re.search(r"Bumping to version (\d+\.\d+\.\d+[^\s]*)", result.stdout)
            new_version = version_match.group(1) if version_match else "unknown"

        except subprocess.CalledProcessError as e:
            console.print("[bold red]❌ commitizen bump failed![/bold red]")
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


def task_release(increment: str = "") -> dict[str, Any]:
    """Automate release: bump version, update CHANGELOG, and push to GitHub (triggers CI/CD).

    Args:
        increment (str): Force version increment type (MAJOR, MINOR, PATCH). Auto-detects if empty.
    """

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
                f"[bold yellow]⚠ Warning: Not on main branch "
                f"(currently on {current_branch})[/bold yellow]"
            )
            response = input("Continue anyway? (y/N) ").strip().lower()
            if response != "y":
                console.print("[bold red]❌ Release cancelled.[/bold red]")
                sys.exit(1)

        # Check for uncommitted changes
        status = subprocess.run(
            ["git", "status", "-s"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        if status:
            console.print("[bold red]❌ Error: Uncommitted changes detected.[/bold red]")
            console.print(status)
            sys.exit(1)

        # Pull latest changes
        console.print("\n[cyan]Pulling latest changes...[/cyan]")
        try:
            subprocess.run(["git", "pull"], check=True, capture_output=True, text=True)
            console.print("[green]✓ Git pull successful.[/green]")
        except subprocess.CalledProcessError as e:
            console.print("[bold red]❌ Error pulling latest changes:[/bold red]")
            console.print(f"[red]Stdout: {e.stdout}[/red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            sys.exit(1)

        # Governance validation
        console.print("\n[bold cyan]Running governance validations...[/bold cyan]")

        # Validate merge commit format (blocking)
        if not validate_merge_commits(console):
            console.print("\n[bold red]❌ Merge commit validation failed![/bold red]")
            console.print("[yellow]Please ensure all merge commits follow the format:[/yellow]")
            console.print("[yellow]  <type>: <subject> (merges PR #XX, closes #YY)[/yellow]")
            sys.exit(1)

        # Validate issue links (warning only)
        validate_issue_links(console)

        console.print("[bold green]✓ Governance validations complete.[/bold green]")

        # Run all checks
        console.print("\n[cyan]Running all pre-release checks...[/cyan]")
        try:
            subprocess.run(["doit", "check"], check=True, capture_output=True, text=True)
            console.print("[green]✓ All checks passed.[/green]")
        except subprocess.CalledProcessError as e:
            console.print(
                "[bold red]❌ Pre-release checks failed! "
                "Please fix issues before releasing.[/bold red]"
            )
            console.print(f"[red]Stdout: {e.stdout}[/red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            sys.exit(1)

        # Automated version bump and CHANGELOG generation using commitizen
        console.print("\n[cyan]Bumping version and generating CHANGELOG with commitizen...[/cyan]")
        try:
            # Use cz bump --changelog --merge-prerelease to update version,
            # changelog, commit, and tag. This consolidates pre-release changes
            # into the final release entry
            bump_cmd = ["uv", "run", "cz", "bump", "--changelog", "--merge-prerelease"]
            if increment:
                bump_cmd.extend(["--increment", increment.upper()])
                console.print(f"[dim]Forcing {increment.upper()} version bump[/dim]")
            result = subprocess.run(
                bump_cmd,
                env={**os.environ, "UV_CACHE_DIR": UV_CACHE_DIR},
                check=True,
                capture_output=True,
                text=True,
            )
            console.print(
                "[green]✓ Version bumped and CHANGELOG updated (merged pre-releases).[/green]"
            )
            console.print(f"[dim]{result.stdout}[/dim]")
            # Extract new version from cz output (example: "Bumping to version 1.0.0")
            version_match = re.search(r"Bumping to version (\d+\.\d+\.\d+)", result.stdout)
            # Fallback to "unknown" if regex fails
            new_version = version_match.group(1) if version_match else "unknown"

        except subprocess.CalledProcessError as e:
            console.print(
                "[bold red]❌ commitizen bump failed! "
                "Ensure your commit history is conventional.[/bold red]"
            )
            console.print(f"[red]Stdout: {e.stdout}[/red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            sys.exit(1)
        except Exception as e:
            console.print(
                f"[bold red]❌ An unexpected error occurred during commitizen bump: {e}[/bold red]"
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
        console.print(
            "2. Check TestPyPI: [link=https://test.pypi.org/project/package-name/]https://test.pypi.org/project/package-name/[/link]"
        )
        console.print(
            "3. Check PyPI: [link=https://pypi.org/project/package-name/]https://pypi.org/project/package-name/[/link]"
        )
        console.print("4. Verify the updated CHANGELOG.md in the repository.")

    return {
        "actions": [automated_release],
        "params": [
            {
                "name": "increment",
                "short": "i",
                "long": "increment",
                "default": "",
                "help": "Force increment (MAJOR, MINOR, PATCH). Auto-detects if empty.",
            }
        ],
        "title": title_with_actions,
    }


def task_release_pr(increment: str = "") -> dict[str, Any]:
    """Create a release PR with changelog updates (PR-based workflow).

    This task creates a release branch, updates the changelog, and opens a PR.
    After the PR is merged, use `doit release_tag` to tag the release.

    Args:
        increment (str): Force version increment type (MAJOR, MINOR, PATCH). Auto-detects if empty.
    """

    def create_release_pr() -> None:
        console = Console()
        console.print("=" * 70)
        console.print("[bold green]Starting PR-based release process...[/bold green]")
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
                f"[bold red]❌ Error: Must be on main branch "
                f"(currently on {current_branch})[/bold red]"
            )
            sys.exit(1)

        # Check for uncommitted changes
        status = subprocess.run(
            ["git", "status", "-s"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        if status:
            console.print("[bold red]❌ Error: Uncommitted changes detected.[/bold red]")
            console.print(status)
            sys.exit(1)

        # Pull latest changes
        console.print("\n[cyan]Pulling latest changes...[/cyan]")
        try:
            subprocess.run(["git", "pull"], check=True, capture_output=True, text=True)
            console.print("[green]✓ Git pull successful.[/green]")
        except subprocess.CalledProcessError as e:
            console.print("[bold red]❌ Error pulling latest changes:[/bold red]")
            console.print(f"[red]Stdout: {e.stdout}[/red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            sys.exit(1)

        # Governance validation
        console.print("\n[bold cyan]Running governance validations...[/bold cyan]")

        # Validate merge commit format (blocking)
        if not validate_merge_commits(console):
            console.print("\n[bold red]❌ Merge commit validation failed![/bold red]")
            console.print("[yellow]Please ensure all merge commits follow the format:[/yellow]")
            console.print("[yellow]  <type>: <subject> (merges PR #XX, closes #YY)[/yellow]")
            sys.exit(1)

        # Validate issue links (warning only)
        validate_issue_links(console)

        console.print("[bold green]✓ Governance validations complete.[/bold green]")

        # Run all checks
        console.print("\n[cyan]Running all pre-release checks...[/cyan]")
        try:
            subprocess.run(["doit", "check"], check=True, capture_output=True, text=True)
            console.print("[green]✓ All checks passed.[/green]")
        except subprocess.CalledProcessError as e:
            console.print(
                "[bold red]❌ Pre-release checks failed! "
                "Please fix issues before releasing.[/bold red]"
            )
            console.print(f"[red]Stdout: {e.stdout}[/red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            sys.exit(1)

        # Get next version using commitizen
        console.print("\n[cyan]Determining next version...[/cyan]")
        try:
            get_next_cmd = ["uv", "run", "cz", "bump", "--get-next"]
            if increment:
                get_next_cmd.extend(["--increment", increment.upper()])
                console.print(f"[dim]Forcing {increment.upper()} version bump[/dim]")
            result = subprocess.run(
                get_next_cmd,
                env={**os.environ, "UV_CACHE_DIR": UV_CACHE_DIR},
                check=True,
                capture_output=True,
                text=True,
            )
            next_version = result.stdout.strip()
            console.print(f"[green]✓ Next version: {next_version}[/green]")
        except subprocess.CalledProcessError as e:
            console.print("[bold red]❌ Failed to determine next version.[/bold red]")
            console.print(f"[red]Stdout: {e.stdout}[/red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            sys.exit(1)

        # Create release branch
        branch_name = f"release/v{next_version}"
        console.print(f"\n[cyan]Creating branch {branch_name}...[/cyan]")
        try:
            subprocess.run(
                ["git", "checkout", "-b", branch_name],
                check=True,
                capture_output=True,
                text=True,
            )
            console.print(f"[green]✓ Created branch {branch_name}[/green]")
        except subprocess.CalledProcessError as e:
            console.print(f"[bold red]❌ Failed to create branch {branch_name}.[/bold red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            sys.exit(1)

        # Update changelog
        console.print("\n[cyan]Updating CHANGELOG.md...[/cyan]")
        try:
            changelog_cmd = ["uv", "run", "cz", "changelog", "--incremental"]
            subprocess.run(
                changelog_cmd,
                env={**os.environ, "UV_CACHE_DIR": UV_CACHE_DIR},
                check=True,
                capture_output=True,
                text=True,
            )
            console.print("[green]✓ CHANGELOG.md updated.[/green]")
        except subprocess.CalledProcessError as e:
            console.print("[bold red]❌ Failed to update changelog.[/bold red]")
            console.print(f"[red]Stdout: {e.stdout}[/red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            # Cleanup: go back to main
            subprocess.run(["git", "checkout", "main"], capture_output=True)
            subprocess.run(["git", "branch", "-D", branch_name], capture_output=True)
            sys.exit(1)

        # Commit changelog
        console.print("\n[cyan]Committing changelog...[/cyan]")
        try:
            subprocess.run(
                ["git", "add", "CHANGELOG.md"],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "commit", "-m", f"chore: update changelog for v{next_version}"],
                check=True,
                capture_output=True,
                text=True,
            )
            console.print("[green]✓ Changelog committed.[/green]")
        except subprocess.CalledProcessError as e:
            console.print("[bold red]❌ Failed to commit changelog.[/bold red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            # Cleanup
            subprocess.run(["git", "checkout", "main"], capture_output=True)
            subprocess.run(["git", "branch", "-D", branch_name], capture_output=True)
            sys.exit(1)

        # Push branch
        console.print(f"\n[cyan]Pushing branch {branch_name}...[/cyan]")
        try:
            subprocess.run(
                ["git", "push", "-u", "origin", branch_name],
                check=True,
                capture_output=True,
                text=True,
            )
            console.print("[green]✓ Branch pushed.[/green]")
        except subprocess.CalledProcessError as e:
            console.print("[bold red]❌ Failed to push branch.[/bold red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            sys.exit(1)

        # Create PR using doit pr
        console.print("\n[cyan]Creating pull request...[/cyan]")
        try:
            pr_title = f"release: v{next_version}"
            pr_body = f"""## Description
Release v{next_version}

## Type of Change
- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (would cause existing functionality to not work as expected)
- [ ] Documentation update
- [x] Release

## Changes Made
- Updated CHANGELOG.md for v{next_version}

## Testing
- [ ] All existing tests pass

## Checklist
- [x] My changes generate no new warnings

## Additional Notes
After this PR is merged, run `doit release_tag` to create the version tag
and trigger the release workflow.
"""
            # Use gh CLI directly since we're in a non-interactive context
            subprocess.run(
                [
                    "gh",
                    "pr",
                    "create",
                    "--title",
                    pr_title,
                    "--body",
                    pr_body,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            console.print("[green]✓ Pull request created.[/green]")
        except subprocess.CalledProcessError as e:
            console.print("[bold red]❌ Failed to create PR.[/bold red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            sys.exit(1)

        console.print("\n" + "=" * 70)
        console.print(f"[bold green]✓ Release PR for v{next_version} created![/bold green]")
        console.print("=" * 70)
        console.print("\nNext steps:")
        console.print("1. Review and merge the PR.")
        console.print("2. After merge, run: doit release_tag")

    return {
        "actions": [create_release_pr],
        "params": [
            {
                "name": "increment",
                "short": "i",
                "long": "increment",
                "default": "",
                "help": "Force increment (MAJOR, MINOR, PATCH). Auto-detects if empty.",
            }
        ],
        "title": title_with_actions,
    }


def task_release_tag() -> dict[str, Any]:
    """Tag the release after a release PR is merged.

    This task finds the most recently merged release PR, extracts the version,
    creates a git tag, and pushes it to trigger the release workflow.
    """

    def create_release_tag() -> None:
        console = Console()
        console.print("=" * 70)
        console.print("[bold green]Creating release tag...[/bold green]")
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
                f"[bold red]❌ Error: Must be on main branch "
                f"(currently on {current_branch})[/bold red]"
            )
            sys.exit(1)

        # Pull latest changes
        console.print("\n[cyan]Pulling latest changes...[/cyan]")
        try:
            subprocess.run(["git", "pull"], check=True, capture_output=True, text=True)
            console.print("[green]✓ Git pull successful.[/green]")
        except subprocess.CalledProcessError as e:
            console.print("[bold red]❌ Error pulling latest changes:[/bold red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            sys.exit(1)

        # Find the most recently merged release PR
        console.print("\n[cyan]Finding merged release PR...[/cyan]")
        try:
            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "list",
                    "--state",
                    "merged",
                    "--search",
                    "release: v in:title",
                    "--limit",
                    "1",
                    "--json",
                    "title,mergedAt,headRefName",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            prs = json.loads(result.stdout)
            if not prs:
                console.print("[bold red]❌ No merged release PR found.[/bold red]")
                console.print(
                    "[yellow]Ensure a release PR with title 'release: vX.Y.Z' was merged.[/yellow]"
                )
                sys.exit(1)

            pr = prs[0]
            pr_title = pr["title"]
            branch_name = pr["headRefName"]

            # Extract version from PR title (format: "release: vX.Y.Z")
            version_match = re.search(r"release:\s*v?(\d+\.\d+\.\d+)", pr_title)
            if not version_match:
                # Try extracting from branch name (format: "release/vX.Y.Z")
                version_match = re.search(r"release/v?(\d+\.\d+\.\d+)", branch_name)

            if not version_match:
                console.print("[bold red]❌ Could not extract version from PR.[/bold red]")
                console.print(f"[yellow]PR title: {pr_title}[/yellow]")
                console.print(f"[yellow]Branch: {branch_name}[/yellow]")
                sys.exit(1)

            version = version_match.group(1)
            tag_name = f"v{version}"
            console.print(f"[green]✓ Found release PR: {pr_title}[/green]")
            console.print(f"[green]✓ Version to tag: {tag_name}[/green]")

        except subprocess.CalledProcessError as e:
            console.print("[bold red]❌ Failed to find release PR.[/bold red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            sys.exit(1)

        # Check if tag already exists
        existing_tags = subprocess.run(
            ["git", "tag", "-l", tag_name],
            capture_output=True,
            text=True,
        ).stdout.strip()
        if existing_tags:
            console.print(f"[bold red]❌ Tag {tag_name} already exists.[/bold red]")
            sys.exit(1)

        # Create tag
        console.print(f"\n[cyan]Creating tag {tag_name}...[/cyan]")
        try:
            subprocess.run(
                ["git", "tag", tag_name],
                check=True,
                capture_output=True,
                text=True,
            )
            console.print(f"[green]✓ Tag {tag_name} created.[/green]")
        except subprocess.CalledProcessError as e:
            console.print("[bold red]❌ Failed to create tag.[/bold red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            sys.exit(1)

        # Push tag
        console.print(f"\n[cyan]Pushing tag {tag_name}...[/cyan]")
        try:
            subprocess.run(
                ["git", "push", "origin", tag_name],
                check=True,
                capture_output=True,
                text=True,
            )
            console.print(f"[green]✓ Tag {tag_name} pushed.[/green]")
        except subprocess.CalledProcessError as e:
            console.print("[bold red]❌ Failed to push tag.[/bold red]")
            console.print(f"[red]Stderr: {e.stderr}[/red]")
            sys.exit(1)

        console.print("\n" + "=" * 70)
        console.print(f"[bold green]✓ Release {tag_name} tagged![/bold green]")
        console.print("=" * 70)
        console.print("\nNext steps:")
        console.print("1. Monitor GitHub Actions for build and publish.")
        console.print(
            "2. Check TestPyPI: [link=https://test.pypi.org/project/package-name/]https://test.pypi.org/project/package-name/[/link]"
        )
        console.print(
            "3. Check PyPI: [link=https://pypi.org/project/package-name/]https://pypi.org/project/package-name/[/link]"
        )

    return {
        "actions": [create_release_tag],
        "title": title_with_actions,
    }

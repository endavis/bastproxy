"""Git-related doit tasks."""

from typing import Any

from doit.tools import title_with_actions


def task_commit() -> dict[str, Any]:
    """Interactive commit with commitizen (ensures conventional commit format)."""
    return {
        "actions": ["uv run cz commit || echo 'commitizen not installed. Run: uv sync'"],
        "title": title_with_actions,
    }


def task_bump() -> dict[str, Any]:
    """Bump version automatically based on conventional commits."""
    return {
        "actions": ["uv run cz bump || echo 'commitizen not installed. Run: uv sync'"],
        "title": title_with_actions,
    }


def task_changelog() -> dict[str, Any]:
    """Generate CHANGELOG from conventional commits."""
    return {
        "actions": ["uv run cz changelog || echo 'commitizen not installed. Run: uv sync'"],
        "title": title_with_actions,
    }


def task_pre_commit_install() -> dict[str, Any]:
    """Install pre-commit hooks."""
    return {
        "actions": ["uv run pre-commit install"],
        "title": title_with_actions,
    }


def task_pre_commit_run() -> dict[str, Any]:
    """Run pre-commit on all files."""
    return {
        "actions": ["uv run pre-commit run --all-files"],
        "title": title_with_actions,
    }

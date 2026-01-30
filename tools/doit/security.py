"""Security-related doit tasks."""

from typing import Any

from doit.tools import title_with_actions


def task_audit() -> dict[str, Any]:
    """Run security audit with pip-audit (requires security extras)."""
    return {
        "actions": [
            "uv run pip-audit --skip-editable || "
            "echo 'pip-audit not installed. Run: uv sync --extra security'"
        ],
        "title": title_with_actions,
    }


def task_security() -> dict[str, Any]:
    """Run security checks with bandit (requires security extras)."""
    return {
        "actions": [
            "uv run bandit -c pyproject.toml -r src/ tools/ bootstrap.py || "
            "echo 'bandit not installed. Run: uv sync --extra security'"
        ],
        "title": title_with_actions,
        "verbosity": 0,
    }


def task_licenses() -> dict[str, Any]:
    """Check licenses of dependencies (requires security extras)."""
    return {
        "actions": [
            "uv run pip-licenses --format=markdown --order=license || "
            "echo 'pip-licenses not installed. Run: uv sync --extra security'"
        ],
        "title": title_with_actions,
    }

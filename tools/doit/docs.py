"""Documentation-related doit tasks."""

from typing import Any

from doit.tools import title_with_actions


def task_docs_serve() -> dict[str, Any]:
    """Serve documentation locally with live reload."""
    return {
        "actions": ["uv run mkdocs serve"],
        "title": title_with_actions,
    }


def task_docs_build() -> dict[str, Any]:
    """Build documentation site."""
    return {
        "actions": ["uv run mkdocs build"],
        "title": title_with_actions,
    }


def task_docs_deploy() -> dict[str, Any]:
    """Deploy documentation to GitHub Pages."""
    return {
        "actions": ["uv run mkdocs gh-deploy --force"],
        "title": title_with_actions,
    }


def task_spell_check() -> dict[str, Any]:
    """Check spelling in code and documentation."""
    return {
        "actions": ["uv run codespell src/ tests/ docs/ README.md"],
        "title": title_with_actions,
        "verbosity": 0,
    }

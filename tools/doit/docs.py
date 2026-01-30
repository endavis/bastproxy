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
        "actions": ["uv run codespell src/ tests/ tools/ docs/ bootstrap.py README.md"],
        "title": title_with_actions,
        "verbosity": 0,
    }


def task_docs_toc() -> dict[str, Any]:
    """Generate documentation table of contents from frontmatter."""
    return {
        "actions": ["uv run python tools/generate_doc_toc.py"],
        "title": title_with_actions,
        "verbosity": 2,
    }

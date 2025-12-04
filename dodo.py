"""doit task definitions wrapping uv-managed tooling."""

from __future__ import annotations

from typing import Iterable


def _uv(*args: str | Iterable[str]) -> str:
    parts: list[str] = ["uv"]
    for arg in args:
        if isinstance(arg, str):
            parts.append(arg)
        else:
            parts.extend(arg)
    return " ".join(parts)


DOIT_CONFIG = {"default_tasks": ["lint", "test"]}


def task_sync():
    """Sync the virtual environment with uv."""

    return {
        "actions": [_uv("sync", "--all-extras")],
        "verbosity": 2,
    }


def task_fmt():
    """Format code with ruff and black."""

    return {
        "actions": [
            _uv("run", ("ruff", "format", "src", "tests")),
            _uv("run", ("black", "src", "tests")),
        ],
        "task_dep": ["sync"],
        "verbosity": 2,
    }


def task_lint():
    """Lint with ruff."""

    return {
        "actions": [_uv("run", ("ruff", "check", "src", "tests"))],
        "task_dep": ["sync"],
        "verbosity": 2,
    }


def task_typecheck():
    """Type-check with mypy."""

    return {
        "actions": [_uv("run", ("mypy", "src", "tests"))],
        "task_dep": ["sync"],
        "verbosity": 2,
    }


def task_test():
    """Run the test suite."""

    return {
        "actions": [_uv("run", "pytest")],
        "task_dep": ["sync"],
        "verbosity": 2,
    }


def task_security():
    """Security checks with bandit and safety."""

    return {
        "actions": [
            _uv("run", ("bandit", "-c", "pyproject.toml", "-r", "src")),
            _uv("run", ("safety", "check")),
        ],
        "task_dep": ["sync"],
        "verbosity": 2,
    }

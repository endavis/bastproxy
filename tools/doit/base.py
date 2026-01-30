"""Base utilities and configuration for doit tasks."""

import os

from rich.console import Console
from rich.panel import Panel

# Configuration
DOIT_CONFIG = {
    "verbosity": 2,
    "default_tasks": ["list"],
}

# Use direnv-managed UV_CACHE_DIR if available, otherwise use tmp/
# Set in os.environ so subprocesses inherit it (cross-platform compatible)
UV_CACHE_DIR = os.environ.get("UV_CACHE_DIR", "tmp/.uv_cache")
os.environ["UV_CACHE_DIR"] = UV_CACHE_DIR


def success_message() -> None:
    """Print success message after all checks pass."""
    console = Console()
    console.print()
    console.print(
        Panel.fit(
            "[bold green]✓ All checks passed![/bold green]", border_style="green", padding=(1, 2)
        )
    )
    console.print()

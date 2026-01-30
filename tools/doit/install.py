"""Installation-related doit tasks."""

import json
import os
import platform
import shutil
import subprocess  # nosec B404 - subprocess is required for doit tasks
import sys
import urllib.request
from typing import Any

from doit.tools import title_with_actions


def _get_latest_github_release(repo: str) -> str:
    """Helper to get latest GitHub release version."""
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    request = urllib.request.Request(url)

    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        request.add_header("Authorization", f"token {github_token}")

    with urllib.request.urlopen(request) as response:  # nosec B310 - URL is hardcoded GitHub API
        data = json.loads(response.read().decode())
        tag_name: str = data["tag_name"]
        return tag_name.lstrip("v")


def _install_direnv() -> None:
    """Install direnv if not already installed."""
    if shutil.which("direnv"):
        version = subprocess.run(
            ["direnv", "--version"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        print(f"✓ direnv already installed: {version}")
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
            f"https://github.com/direnv/direnv/releases/download/v{version}/direnv.linux-amd64"
        )
        bin_path = os.path.join(install_dir, "direnv")
        print(f"Downloading {bin_url}...")
        urllib.request.urlretrieve(bin_url, bin_path)  # nosec B310 - downloading from hardcoded GitHub release URL
        os.chmod(bin_path, 0o755)  # nosec B103 - rwxr-xr-x is required for executable binary
    elif system == "darwin":
        subprocess.run(["brew", "install", "direnv"], check=True)
    else:
        print(f"Unsupported OS: {system}")
        sys.exit(1)

    print("✓ direnv installed.")
    print("\nIMPORTANT: Add direnv hook to your shell:")
    print("  Bash: echo 'eval \"$(direnv hook bash)\"'")
    print("  Zsh:  echo 'eval \"$(direnv hook zsh)\"'")


def task_install() -> dict[str, Any]:
    """Install package with dependencies."""
    return {
        "actions": [
            "uv sync",
        ],
        "title": title_with_actions,
    }


def task_install_dev() -> dict[str, Any]:
    """Install package with dev dependencies."""
    return {
        "actions": [
            "uv sync --all-extras --dev",
        ],
        "title": title_with_actions,
    }


def task_install_direnv() -> dict[str, Any]:
    """Install direnv for automatic environment loading."""
    return {
        "actions": [_install_direnv],
        "title": title_with_actions,
    }

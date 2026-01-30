#!/usr/bin/env python3
"""
check-template-updates.py - Compare project against latest template

This script fetches the latest pyproject-template release and shows which files
differ from the template. User can then manually review and merge changes.

Usage:
    python tools/pyproject_template/check_template_updates.py
    python tools/pyproject_template/check_template_updates.py --template-version v2.2.0
    python tools/pyproject_template/check_template_updates.py --skip-changelog

Requirements:
    - Git installed
    - Python 3.12+
    - Internet connection (to fetch template)

Author: Generated from pyproject-template
License: MIT
"""

from __future__ import annotations

import argparse
import filecmp
import json
import os
import shutil
import subprocess  # nosec B404
import sys
import urllib.request
from pathlib import Path

# Support running as script or as module
_script_dir = Path(__file__).parent
if str(_script_dir) not in sys.path:
    sys.path.insert(0, str(_script_dir))

# Import shared utilities
from utils import (  # noqa: E402
    TEMPLATE_REPO,
    TEMPLATE_URL,
    Colors,
    Logger,
    download_and_extract_archive,
)

# Default archive URL derived from template constants
DEFAULT_ARCHIVE_URL = f"{TEMPLATE_URL}/archive/refs/heads/main.zip"


def get_latest_release() -> str | None:
    """Get the latest release tag from GitHub API."""
    api_url = f"https://api.github.com/repos/{TEMPLATE_REPO}/releases/latest"
    try:
        with urllib.request.urlopen(api_url) as response:  # nosec B310
            data = json.loads(response.read())
            tag_name: str | None = data.get("tag_name")
            return tag_name
    except Exception as e:
        Logger.warning(f"Could not fetch latest release: {e}")
        return None


def download_template(target_dir: Path, version: str | None = None) -> Path:
    """Download and extract template to target directory."""
    # Determine download URL
    if version:
        archive_url = f"{TEMPLATE_URL}/archive/refs/tags/{version}.zip"
    else:
        archive_url = DEFAULT_ARCHIVE_URL

    template_root = Path(download_and_extract_archive(archive_url, target_dir))
    Logger.success(f"Template extracted to {template_root}")
    return template_root


def open_changelog(template_dir: Path) -> None:
    """Open CHANGELOG.md in user's editor."""
    changelog = template_dir / "CHANGELOG.md"
    if not changelog.exists():
        Logger.warning("CHANGELOG.md not found in template")
        return

    editor = os.environ.get("EDITOR", "less")

    print(f"\n{Colors.CYAN}Opening CHANGELOG.md for review...{Colors.NC}")
    print("(Close the editor when you're done)\n")

    try:
        subprocess.run([editor, str(changelog)], check=True)
    except subprocess.CalledProcessError:
        Logger.warning(f"Failed to open editor '{editor}'")
    except FileNotFoundError:
        Logger.warning(f"Editor '{editor}' not found, skipping changelog view")


def compare_files(project_root: Path, template_root: Path) -> list[Path]:
    """Compare project files against template and return list of different files."""
    # Files/directories to skip
    skip_patterns = {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "tmp",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "*.pyc",
        "*.pyo",
        "uv.lock",
        ".envrc.local",
        "site",  # mkdocs build output
    }

    # Detect user's actual package name (directory under src/ that isn't package_name)
    actual_package_name: str | None = None
    src_dir = project_root / "src"
    if src_dir.exists():
        for item in src_dir.iterdir():
            if item.is_dir() and item.name != "package_name" and not item.name.startswith("."):
                actual_package_name = item.name
                break

    different_files: list[Path] = []

    # Walk through template files
    for template_file in template_root.rglob("*"):
        if not template_file.is_file():
            continue

        # Skip ignored patterns
        rel_path = template_file.relative_to(template_root)
        if any(part in skip_patterns for part in rel_path.parts):
            continue
        if any(rel_path.match(pattern) for pattern in skip_patterns):
            continue

        # Map src/package_name/* to src/{actual_package_name}/*
        mapped_path = rel_path
        if (
            actual_package_name
            and len(rel_path.parts) >= 2
            and rel_path.parts[0] == "src"
            and rel_path.parts[1] == "package_name"
        ):
            mapped_path = Path("src", actual_package_name, *rel_path.parts[2:])

        # Compare with project file
        project_file = project_root / mapped_path

        if not project_file.exists() or not filecmp.cmp(template_file, project_file, shallow=False):
            different_files.append(rel_path)

    return sorted(different_files)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare your project against the latest pyproject-template."
    )
    parser.add_argument(
        "--template-version",
        type=str,
        default=None,
        help=(
            "Compare against specific template version tag (e.g., v2.2.0). "
            "Defaults to latest release."
        ),
    )
    parser.add_argument(
        "--skip-changelog",
        action="store_true",
        help="Skip opening CHANGELOG.md in editor",
    )
    parser.add_argument(
        "--keep-template",
        action="store_true",
        help="Keep downloaded template after comparison (don't clean up)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be checked without downloading (currently same as normal)",
    )
    return parser.parse_args(argv)


def run_check_updates(
    template_version: str | None = None,
    skip_changelog: bool = False,
    keep_template: bool = False,
    dry_run: bool = False,
) -> int:
    """Check for template updates.

    Args:
        template_version: Specific template version to compare against.
        skip_changelog: Skip opening CHANGELOG.md in editor.
        keep_template: Keep downloaded template after comparison.
        dry_run: Show what would be done without making changes.

    Returns:
        Exit code (0 for success, non-zero for error).
    """
    project_root = Path.cwd()
    tmp_dir = project_root / "tmp"
    tmp_dir.mkdir(exist_ok=True)

    # Get template version
    version: str | None = None
    if template_version:
        version = template_version
        Logger.info(f"Comparing against template version: {version}")
    else:
        version = get_latest_release()
        if version:
            Logger.info(f"Latest template release: {version}")
        else:
            Logger.info("Comparing against template main branch")

    if dry_run:
        Logger.info("Dry run mode - would download and compare template files")
        return 0

    # Download template
    template_dir = download_template(tmp_dir, version)

    # Open CHANGELOG.md for review
    if not skip_changelog:
        open_changelog(template_dir)

    # Compare files
    Logger.header("Comparing your project to template")
    different_files = compare_files(project_root, template_dir)

    # Detect user's actual package name for display mapping
    actual_package_name: str | None = None
    src_dir = project_root / "src"
    if src_dir.exists():
        for item in src_dir.iterdir():
            if item.is_dir() and item.name != "package_name" and not item.name.startswith("."):
                actual_package_name = item.name
                break

    if not different_files:
        Logger.success("Your project matches the template perfectly!")
        print("\nNo differences found.")
    else:
        count = len(different_files)
        print(f"\n{Colors.YELLOW}Files different from template ({count} files):{Colors.NC}")
        print("━" * 60)

        for file_path in different_files:
            # Map src/package_name/* to src/{actual_package_name}/* for checking
            mapped_path = file_path
            if (
                actual_package_name
                and len(file_path.parts) >= 2
                and file_path.parts[0] == "src"
                and file_path.parts[1] == "package_name"
            ):
                mapped_path = Path("src", actual_package_name, *file_path.parts[2:])

            project_file = project_root / mapped_path
            if project_file.exists():
                print(f"  {file_path}")
            else:
                print(f"  {file_path} {Colors.CYAN}(new in template){Colors.NC}")

        # Show how to compare
        Logger.header("How to Review Changes")
        template_rel = template_dir.relative_to(project_root)
        print(f"Template files downloaded to: {Colors.CYAN}{template_rel}{Colors.NC}\n")

        print("To compare specific files:")
        # Show a few example diff commands
        for file_path in different_files[:3]:
            project_file = project_root / file_path
            template_file = template_dir / file_path
            if project_file.exists():
                print(f"  diff {file_path} {template_file.relative_to(project_root)}")

        if len(different_files) > 3:
            print(f"  ... ({len(different_files) - 3} more files)")

        print(f"\nOr browse all template files: {template_dir.relative_to(project_root)}/")

    # Cleanup
    if not keep_template:
        print()
        Logger.info("Cleaning up downloaded template...")
        shutil.rmtree(template_dir.parent)
        Logger.success("Cleanup complete")
    else:
        print()
        Logger.info(f"Template kept at: {template_dir.relative_to(project_root)}")

    print()
    return 0


def main(argv: list[str] | None = None) -> int:
    """Main entry point for CLI usage."""
    args = parse_args(argv)
    return run_check_updates(
        template_version=args.template_version,
        skip_changelog=args.skip_changelog,
        keep_template=args.keep_template,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    import sys

    print("This script should not be run directly.")
    print("Please use: python manage.py")
    sys.exit(1)

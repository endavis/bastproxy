#!/usr/bin/env python3
"""
cleanup.py - Template file cleanup utilities.

This module provides functions to remove template-specific files from projects
created from pyproject-template. Users can choose to:
1. Remove setup files only (keep update checking capability)
2. Remove all template files (no future update checking)

Usage:
    from cleanup import cleanup_template_files, CleanupMode

    # Remove setup files only
    cleanup_template_files(CleanupMode.SETUP_ONLY)

    # Remove all template files
    cleanup_template_files(CleanupMode.ALL)

    # Preview what would be deleted
    cleanup_template_files(CleanupMode.SETUP_ONLY, dry_run=True)
"""

from __future__ import annotations

import re
import shutil
import sys
from enum import Enum
from pathlib import Path
from typing import NamedTuple

# Support running as script or as module
_script_dir = Path(__file__).parent
if str(_script_dir) not in sys.path:
    sys.path.insert(0, str(_script_dir))

from utils import Logger  # noqa: E402


class CleanupMode(Enum):
    """Cleanup mode selection."""

    SETUP_ONLY = "setup"  # Remove setup files, keep update checking
    ALL = "all"  # Remove all template files


class CleanupResult(NamedTuple):
    """Result of cleanup operation."""

    deleted_files: list[Path]
    deleted_dirs: list[Path]
    failed: list[tuple[Path, str]]
    mkdocs_updated: bool


# Files to delete when removing setup files only
# These are only needed for initial project creation
SETUP_FILES = [
    "bootstrap.py",
    "tools/pyproject_template/setup_repo.py",
    "tools/pyproject_template/migrate_existing_project.py",
    "docs/template/new-project.md",
    "docs/template/migration.md",
]

# Additional files to delete when removing all template files
# After this, no template update checking is possible
ALL_TEMPLATE_FILES = [
    "tools/pyproject_template/manage.py",
    "tools/pyproject_template/check_template_updates.py",
    "tools/pyproject_template/configure.py",
    "tools/pyproject_template/settings.py",
    "tools/pyproject_template/repo_settings.py",
    "tools/pyproject_template/cleanup.py",
    "tools/pyproject_template/utils.py",
    "tools/pyproject_template/__init__.py",
    "docs/template/index.md",
    "docs/template/manage.md",
    "docs/template/updates.md",
    "docs/template/tools-reference.md",
]

# Directories to delete when removing all template files
ALL_TEMPLATE_DIRS = [
    "tools/pyproject_template",
    "docs/template",
    ".config/pyproject_template",
]


def get_files_to_delete(mode: CleanupMode, root: Path | None = None) -> list[Path]:
    """Get list of files that would be deleted for the given mode.

    Args:
        mode: Cleanup mode (SETUP_ONLY or ALL)
        root: Project root directory (defaults to cwd)

    Returns:
        List of file paths that exist and would be deleted
    """
    if root is None:
        root = Path.cwd()

    files = SETUP_FILES.copy()
    if mode == CleanupMode.ALL:
        files.extend(ALL_TEMPLATE_FILES)

    existing_files = []
    for file_path in files:
        full_path = root / file_path
        if full_path.is_file():
            existing_files.append(full_path)

    return existing_files


def get_dirs_to_delete(mode: CleanupMode, root: Path | None = None) -> list[Path]:
    """Get list of directories that would be deleted for the given mode.

    Args:
        mode: Cleanup mode (only ALL mode deletes directories)
        root: Project root directory (defaults to cwd)

    Returns:
        List of directory paths that exist and would be deleted
    """
    if root is None:
        root = Path.cwd()

    if mode != CleanupMode.ALL:
        return []

    existing_dirs = []
    for dir_path in ALL_TEMPLATE_DIRS:
        full_path = root / dir_path
        if full_path.is_dir():
            existing_dirs.append(full_path)

    return existing_dirs


def update_mkdocs_nav(root: Path | None = None, dry_run: bool = False) -> bool:
    """Remove Template section from mkdocs.yml navigation.

    Args:
        root: Project root directory (defaults to cwd)
        dry_run: If True, only report what would be changed

    Returns:
        True if mkdocs.yml was updated (or would be), False otherwise
    """
    if root is None:
        root = Path.cwd()

    mkdocs_file = root / "mkdocs.yml"
    if not mkdocs_file.exists():
        return False

    content = mkdocs_file.read_text()

    # Pattern to match the Template section in nav
    # Matches from "  - Template:" to the next "  - " at the same indent level or end of nav
    pattern = r"(  - Template:\n(?:      - [^\n]+\n)*)"

    if not re.search(pattern, content):
        return False

    if dry_run:
        Logger.info("Would remove Template section from mkdocs.yml")
        return True

    new_content = re.sub(pattern, "", content)
    mkdocs_file.write_text(new_content)
    Logger.success("Removed Template section from mkdocs.yml")
    return True


def cleanup_template_files(
    mode: CleanupMode,
    root: Path | None = None,
    dry_run: bool = False,
) -> CleanupResult:
    """Remove template-specific files from the project.

    Args:
        mode: Cleanup mode (SETUP_ONLY or ALL)
        root: Project root directory (defaults to cwd)
        dry_run: If True, only report what would be deleted

    Returns:
        CleanupResult with details of what was deleted
    """
    if root is None:
        root = Path.cwd()

    deleted_files: list[Path] = []
    deleted_dirs: list[Path] = []
    failed: list[tuple[Path, str]] = []

    # Get files and directories to delete
    files_to_delete = get_files_to_delete(mode, root)
    dirs_to_delete = get_dirs_to_delete(mode, root)

    if not files_to_delete and not dirs_to_delete:
        Logger.info("No template files found to clean up")
        return CleanupResult([], [], [], False)

    # Report what will be deleted
    if files_to_delete:
        Logger.step(f"{'Would delete' if dry_run else 'Deleting'} files:")
        for file_path in files_to_delete:
            rel_path = file_path.relative_to(root)
            print(f"  - {rel_path}")

    if dirs_to_delete:
        Logger.step(f"{'Would delete' if dry_run else 'Deleting'} directories:")
        for dir_path in dirs_to_delete:
            rel_path = dir_path.relative_to(root)
            print(f"  - {rel_path}/")

    if dry_run:
        # Check mkdocs update
        mkdocs_would_update = False
        if mode == CleanupMode.ALL:
            mkdocs_would_update = update_mkdocs_nav(root, dry_run=True)
        return CleanupResult(files_to_delete, dirs_to_delete, [], mkdocs_would_update)

    # Delete files
    for file_path in files_to_delete:
        try:
            file_path.unlink()
            deleted_files.append(file_path)
        except OSError as e:
            failed.append((file_path, str(e)))

    # Delete directories (only for ALL mode, and only after files are deleted)
    # Sort by depth (deepest first) to avoid deleting parent before child
    for dir_path in sorted(dirs_to_delete, key=lambda p: len(p.parts), reverse=True):
        try:
            if dir_path.exists():
                shutil.rmtree(dir_path)
                deleted_dirs.append(dir_path)
        except OSError as e:
            failed.append((dir_path, str(e)))

    # Update mkdocs.yml if removing all template files
    mkdocs_updated = False
    if mode == CleanupMode.ALL:
        mkdocs_updated = update_mkdocs_nav(root, dry_run=False)

    # Report results
    if deleted_files:
        Logger.success(f"Deleted {len(deleted_files)} files")
    if deleted_dirs:
        Logger.success(f"Deleted {len(deleted_dirs)} directories")
    if failed:
        Logger.warning(f"Failed to delete {len(failed)} items:")
        for path, error in failed:
            rel_path = path.relative_to(root) if path.is_relative_to(root) else path
            print(f"  - {rel_path}: {error}")

    return CleanupResult(deleted_files, deleted_dirs, failed, mkdocs_updated)


def prompt_cleanup(root: Path | None = None) -> CleanupMode | None:
    """Interactively prompt user for cleanup mode.

    Args:
        root: Project root directory (defaults to cwd)

    Returns:
        Selected CleanupMode, or None if user chose to keep all files
    """
    if root is None:
        root = Path.cwd()

    print()
    Logger.header("Template File Cleanup")
    print()
    print("Would you like to remove template-specific files?")
    print()
    print("  [1] Remove setup files only (keep update checking)")
    print("      Removes: bootstrap.py, setup_repo.py, migrate_existing_project.py")
    print("      Keeps: manage.py, check_template_updates.py (for future updates)")
    print()
    print("  [2] Remove all template files (no future update checking)")
    print("      Removes: All template tools and documentation")
    print("      Warning: You won't be able to check for template updates")
    print()
    print("  [3] Keep all files")
    print()

    while True:
        try:
            choice = input("Select option [1-3]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None

        if choice == "1":
            return CleanupMode.SETUP_ONLY
        elif choice == "2":
            return CleanupMode.ALL
        elif choice == "3":
            return None
        else:
            print("Invalid option. Please enter 1, 2, or 3.")


def main() -> int:
    """Main entry point for standalone usage."""
    import argparse

    parser = argparse.ArgumentParser(description="Remove template-specific files from the project.")
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Remove setup files only (keep update checking)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Remove all template files (no future update checking)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting",
    )

    args = parser.parse_args()

    # Determine mode
    if args.setup and args.all:
        Logger.error("Cannot specify both --setup and --all")
        return 1
    elif args.setup:
        mode = CleanupMode.SETUP_ONLY
    elif args.all:
        mode = CleanupMode.ALL
    else:
        # Interactive mode
        mode = prompt_cleanup()
        if mode is None:
            Logger.info("Keeping all template files")
            return 0

    # Perform cleanup
    result = cleanup_template_files(mode, dry_run=args.dry_run)

    if args.dry_run:
        Logger.info("Dry run complete. No files were deleted.")

    return 0 if not result.failed else 1


if __name__ == "__main__":
    sys.exit(main())

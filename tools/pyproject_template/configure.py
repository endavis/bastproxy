#!/usr/bin/env python3
"""Interactive/non-interactive script to configure the project template.

Modes:
- Interactive (default): prompts for values with defaults pulled from pyproject.toml.
- Auto: use values from pyproject.toml (and git remote) with no prompts (--auto).
Optional: skip final confirmation with --yes.
"""

import argparse
import shutil
import sys
from pathlib import Path

# Support running as script or as module
_script_dir = Path(__file__).parent
if str(_script_dir) not in sys.path:
    sys.path.insert(0, str(_script_dir))

# Import shared utilities
from utils import (  # noqa: E402
    FILES_TO_UPDATE,
    Logger,
    get_first_author,
    get_git_config,
    load_toml_file,
    parse_github_url,
    prompt,
    prompt_confirm,
    update_file,
    update_test_files,
    validate_email,
    validate_package_name,
    validate_pypi_name,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Configure the project template.")
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Use values from pyproject.toml (and git remote) without prompts.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt (useful with --auto).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes.",
    )
    return parser.parse_args(argv)


def find_backup_pyproject() -> Path | None:
    """Find the most recent backup pyproject.toml from migration helper (in tmp/)."""
    candidates = []
    for backup_dir in Path("tmp").glob("template-migration-backup-*"):
        pyproject = backup_dir / "pyproject.toml"
        if pyproject.exists():
            candidates.append(pyproject)
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def guess_github_user(pyproject_data: dict[str, object]) -> str:
    """Get GitHub user from pyproject data or git remote."""
    # First try from pyproject.toml repository URL
    project = pyproject_data.get("project", {})
    urls = project.get("urls", {}) if isinstance(project, dict) else {}
    repo_url = urls.get("Repository", "") if isinstance(urls, dict) else ""
    github_user: str
    github_user, _ = parse_github_url(str(repo_url))
    if github_user:
        return github_user

    # Fallback: try git remote origin
    remote_url = get_git_config("remote.origin.url")
    github_user, _ = parse_github_url(remote_url)
    return github_user


def read_readme_title(readme_path: Path) -> str:
    if not readme_path.exists():
        return ""
    for line in readme_path.read_text().splitlines():
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return ""


def load_defaults(pyproject_path: Path) -> dict[str, str]:
    data = load_toml_file(pyproject_path)
    project = data.get("project", {})
    project_name = project.get("name", "")
    package_name = validate_package_name(project_name) if project_name else ""
    pypi_name = validate_pypi_name(project_name) if project_name else ""
    description = project.get("description") or read_readme_title(Path("README.md"))
    author_name, author_email = get_first_author(data)
    github_user = guess_github_user(data)

    # If current pyproject still has template placeholders, try backup for real values
    backup_pyproject = find_backup_pyproject()
    if backup_pyproject:
        backup_data = load_toml_file(backup_pyproject)
        b_project = backup_data.get("project", {})

        def not_placeholder(val: str, placeholders: set[str]) -> bool:
            return bool(val) and val not in placeholders

        if not_placeholder(project_name, {"package_name", "Package Name", ""}):
            pass
        else:
            project_name = b_project.get("name", project_name)
            package_name = validate_package_name(project_name) if project_name else package_name
            pypi_name = validate_pypi_name(project_name) if project_name else pypi_name

        if not_placeholder(description, {"A short description of your package", ""}):
            pass
        else:
            description = b_project.get("description", description)

        b_author_name, b_author_email = get_first_author(backup_data)
        if not_placeholder(author_name, {"Your Name", ""}):
            pass
        else:
            author_name = b_author_name or author_name
        if not_placeholder(author_email, {"your.email@example.com", ""}):
            pass
        else:
            author_email = b_author_email or author_email

        if not_placeholder(github_user, {"username", ""}):
            pass
        else:
            github_user = guess_github_user(backup_data) or github_user

    return {
        "project_name": project_name,
        "package_name": package_name,
        "pypi_name": pypi_name,
        "description": description,
        "author_name": author_name,
        "author_email": author_email,
        "github_user": github_user,
    }


def require(value: str, label: str) -> str:
    if value:
        return value
    raise SystemExit(
        f"❌ Missing required value for {label} (supply in pyproject.toml or via prompt)."
    )


def run_configure(
    auto: bool = False,
    yes: bool = False,
    dry_run: bool = False,
    defaults: dict[str, str] | None = None,
) -> int:
    """Run the configuration wizard.

    Args:
        auto: Use values from pyproject.toml without prompts.
        yes: Skip confirmation prompt.
        dry_run: Show what would be done without making changes.
        defaults: Pre-loaded default values (if None, loads from pyproject.toml).

    Returns:
        Exit code (0 for success, non-zero for error).
    """
    # Ensure script is run from project root
    if not Path("pyproject.toml").exists():
        Logger.error("Please run this script from the project root directory.")
        return 1

    if defaults is None:
        defaults = load_defaults(Path("pyproject.toml"))

    Logger.header("Python Project Template Configuration")
    print("\nThis script will help you set up your new Python project.\n")

    # Gather project information
    Logger.step("Project Information")

    if auto:
        project_name = require(defaults["project_name"], "[project].name")
        package_name = require(defaults["package_name"], "package name")
        pypi_name = require(defaults["pypi_name"], "PyPI name")
        description = require(defaults["description"], "description")
        author_name = require(defaults["author_name"], "author name")
        author_email = require(defaults["author_email"], "author email")
        if not validate_email(author_email):
            raise SystemExit("❌ Invalid email format in pyproject.toml")
        github_user = require(
            defaults["github_user"],
            "GitHub user (from Repository URL or git remote)",
        )
        enable_dependabot = False
    else:
        project_name = prompt(
            "Project name (human-readable)",
            defaults["project_name"] or "My Awesome Project",
        )

        suggested_package = validate_package_name(project_name)
        suggested_pypi = validate_pypi_name(project_name)

        package_name = prompt("Python package name", defaults["package_name"] or suggested_package)
        package_name = validate_package_name(package_name)

        pypi_name = prompt("PyPI package name", defaults["pypi_name"] or suggested_pypi)
        pypi_name = validate_pypi_name(pypi_name)

        description = prompt(
            "Short description",
            defaults["description"] or "A short description of your package",
        )

        author_name = prompt("Author name", defaults["author_name"] or "Your Name")

        while True:
            author_email = prompt(
                "Author email",
                defaults["author_email"] or "your.email@example.com",
            )
            if validate_email(author_email):
                break
            Logger.warning("Invalid email format. Please try again.")

        github_user = prompt("GitHub username", defaults["github_user"] or "username")

    # Optional features
    if auto:
        enable_dependabot = False
    else:
        print()
        Logger.step("Optional Features")
        enable_dependabot = prompt_confirm("Enable Dependabot for automatic dependency updates?")

    # Confirm configuration
    Logger.header("Configuration Summary")
    print(f"Project Name:     {project_name}")
    print(f"Package Name:     {package_name}")
    print(f"PyPI Name:        {pypi_name}")
    print(f"Description:      {description}")
    print(f"Author:           {author_name} <{author_email}>")
    print(f"GitHub:           {github_user}")
    print(f"Dependabot:       {'Enabled' if enable_dependabot else 'Disabled'}")
    print("━" * 60)

    if not yes and not prompt_confirm("\nProceed with configuration?"):
        Logger.warning("Configuration cancelled.")
        return 1

    if dry_run:
        Logger.info("Dry run mode - no changes will be made")
        Logger.success("Configuration validated successfully (dry run)")
        return 0

    Logger.step("Configuring project...")

    # Define replacements
    # IMPORTANT: Longer/Specific replacements must come before shorter substrings
    replacements = {
        # URLs (Specific matches first)
        "https://github.com/username/package_name": f"https://github.com/{github_user}/{package_name}",
        "https://github.com/original-owner/package_name": f"https://github.com/{github_user}/{package_name}",
        "https://codecov.io/gh/username/package_name": f"https://codecov.io/gh/{github_user}/{package_name}",
        "https://codecov.io/gh/username/package_name/branch/main/graph/badge.svg": f"https://codecov.io/gh/{github_user}/{package_name}/branch/main/graph/badge.svg",
        "https://github.com/username/package_name/actions/workflows/ci.yml/badge.svg": f"https://github.com/{github_user}/{package_name}/actions/workflows/ci.yml/badge.svg",
        "https://github.com/username": f"https://github.com/{github_user}",
        # GitHub Pages URL (mkdocs.yml)
        "https://username.github.io/package_name": f"https://{github_user}.github.io/{package_name}",
        # Files and Paths
        "package-name.svg": f"{pypi_name}.svg",
        "package-name/": f"{pypi_name}/",
        # Repo name pattern (mkdocs.yml) - must come before general package_name
        "username/package_name": f"{github_user}/{package_name}",
        # General Placeholders (Substrings)
        "package_name": package_name,
        "package-name": pypi_name,
        "Package Name": project_name,
        "A short description of your package": description,
        "Your Name": author_name,
        "your.email@example.com": author_email,
        # GitHub template placeholders (for issue templates, etc.)
        "{owner}": github_user,
        "{repo}": package_name,
        # Contact email placeholders
        "security@example.com": author_email,
        "[INSERT CONTACT EMAIL]": author_email,
        # Note: "username" is NOT replaced globally to avoid breaking code
        # variables (e.g. in extensions.md)
    }

    # Update files (using shared constant from utils.py)
    for file_path in FILES_TO_UPDATE:
        path = Path(file_path)
        if path.exists():
            print(f"  ✓ Updating {file_path}")
            update_file(path, replacements)

    # Update docs directory
    docs_dir = Path("docs")
    if docs_dir.exists():
        print("  ✓ Updating documentation files")
        for md_file in docs_dir.rglob("*.md"):
            update_file(md_file, replacements)

    # Update issue/PR templates
    issue_template_dir = Path(".github/ISSUE_TEMPLATE")
    if issue_template_dir.exists():
        print("  ✓ Updating issue templates")
        for template_file in issue_template_dir.rglob("*"):
            if template_file.suffix in {".md", ".yml", ".yaml"}:
                update_file(template_file, replacements)

    # Update examples directory
    examples_dir = Path("examples")
    if examples_dir.exists():
        print("  ✓ Updating example files")
        for example_file in examples_dir.rglob("*"):
            if example_file.suffix in {".py", ".md"}:
                update_file(example_file, replacements)

    # Rename package directory
    old_package_dir = Path("src/package_name")
    new_package_dir = Path(f"src/{package_name}")

    if old_package_dir.exists() and old_package_dir != new_package_dir:
        if new_package_dir.exists():
            print(f"  ⚠️  src/{package_name} already exists; skipping rename of src/package_name")
        else:
            print(f"  ✓ Renaming src/package_name → src/{package_name}")
            shutil.move(str(old_package_dir), str(new_package_dir))
    elif not old_package_dir.exists():
        print("  ⚠️  src/package_name not found; assuming code already relocated")

    # Update imports in renamed package
    if new_package_dir.exists():
        for py_file in new_package_dir.rglob("*.py"):
            update_file(py_file, replacements)

    # Update test files (limited replacements to preserve test data)
    test_dir = Path("tests")
    if test_dir.exists():
        print("  ✓ Updating test files")
        update_test_files(test_dir, package_name)

    # Remove template tool tests (they're only for the template itself)
    tool_tests_dir = Path("tests/pyproject_template")
    if tool_tests_dir.exists():
        print("  ✓ Removing template tool tests (tests/pyproject_template/)")
        shutil.rmtree(tool_tests_dir)

    # Enable Dependabot if requested
    dependabot_example = Path(".github/dependabot.yml.example")
    dependabot_config = Path(".github/dependabot.yml")
    if enable_dependabot and dependabot_example.exists():
        print("  ✓ Enabling Dependabot")
        shutil.copy(dependabot_example, dependabot_config)

    Logger.success("Configuration complete!")
    Logger.header("Next Steps")
    print("1. Review the changes: git diff")
    print("2. Initialize git repository: git init")
    print("3. Install dependencies: uv sync --all-extras --dev")
    print("4. Install pre-commit hooks: uv run pre-commit install")
    print("5. Run tests: uv run pytest")
    print("6. Cut a prerelease (if desired): uv run doit release_dev")
    print("7. Start coding!")
    print("━" * 60)

    # Self-destruct
    print("\n🗑️  Removing configure.py (self-destruct)...")
    try:
        Path(__file__).unlink()
        Logger.success("configure.py removed")
    except Exception as e:
        Logger.warning(f"Could not remove configure.py: {e}")
        print("  → You can safely delete it manually")

    return 0


def main(argv: list[str] | None = None) -> int:
    """Main entry point for CLI usage."""
    args = parse_args(argv)
    return run_configure(
        auto=args.auto,
        yes=args.yes,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    print("This script should not be run directly.")
    print("Please use: python manage.py")
    sys.exit(1)

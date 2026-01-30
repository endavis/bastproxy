"""Architecture Decision Records (ADR) doit tasks."""

import os
import re
import subprocess  # nosec B404 - subprocess is required for doit tasks
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from doit.tools import title_with_actions
from rich.console import Console
from rich.panel import Panel

from tools.doit.templates import get_adr_required_sections, get_adr_template

if TYPE_CHECKING:
    from rich.console import Console as ConsoleType

ADR_DIR = Path("docs/decisions")


def _get_next_adr_number() -> int:
    """Get the next available ADR number.

    Scans existing ADR files and returns the next sequential number.

    Returns:
        Next ADR number (1 if no ADRs exist)
    """
    if not ADR_DIR.exists():
        return 1

    pattern = re.compile(r"^(\d{4})-.*\.md$")
    max_number = 0

    for file in ADR_DIR.iterdir():
        if file.name == "adr-template.md" or file.name == "README.md":
            continue
        match = pattern.match(file.name)
        if match:
            number = int(match.group(1))
            max_number = max(max_number, number)

    return max_number + 1


def _title_to_slug(title: str) -> str:
    """Convert a title to a kebab-case slug.

    Args:
        title: The ADR title

    Returns:
        Kebab-case slug suitable for filename
    """
    # Convert to lowercase
    slug = title.lower()
    # Replace spaces and underscores with hyphens
    slug = re.sub(r"[\s_]+", "-", slug)
    # Remove non-alphanumeric characters except hyphens
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    # Collapse multiple hyphens
    slug = re.sub(r"-+", "-", slug)
    # Trim hyphens from ends
    slug = slug.strip("-")
    return slug


def _get_editor() -> str:
    """Get the user's preferred editor."""
    return os.environ.get("EDITOR", os.environ.get("VISUAL", "vi"))


def _open_editor_with_template(template: str, suffix: str = ".md") -> str | None:
    """Open editor with template and return the edited content.

    Args:
        template: The template content to start with
        suffix: File suffix for the temp file

    Returns:
        The edited content, or None if aborted/unchanged
    """
    console = Console()
    editor = _get_editor()

    # Create temp file with template
    with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False) as f:
        f.write(template)
        temp_path = f.name

    try:
        # Open editor
        console.print(f"[dim]Opening {editor}...[/dim]")
        result = subprocess.run([editor, temp_path])

        if result.returncode != 0:
            console.print("[red]Editor exited with error.[/red]")
            return None

        # Read the edited content
        with open(temp_path) as f:
            content = f.read()

        # Remove HTML comments <!-- ... -->
        edited = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)

        # Clean up extra blank lines
        edited = re.sub(r"\n{3,}", "\n\n", edited).strip()

        return edited

    finally:
        # Clean up temp file
        if os.path.exists(temp_path):
            os.remove(temp_path)


def _read_body_file(file_path: str, console: "ConsoleType") -> str | None:
    """Read body content from a file.

    Args:
        file_path: Path to the file
        console: Rich console for output

    Returns:
        File content, or None if error
    """
    path = Path(file_path)
    if not path.exists():
        console.print(f"[red]File not found: {file_path}[/red]")
        return None

    try:
        return path.read_text()
    except Exception as e:
        console.print(f"[red]Error reading file: {e}[/red]")
        return None


def _validate_adr_content(content: str, console: "ConsoleType") -> bool:
    """Validate that ADR has required sections with content.

    Required sections are read from the ADR template file.

    Args:
        content: ADR markdown content
        console: Rich console for output

    Returns:
        True if valid, False otherwise
    """
    required_sections = get_adr_required_sections()

    for section in required_sections:
        # Look for ## Section header followed by content
        # Use MULTILINE so ^ matches start of line
        pattern = rf"^##\s+{re.escape(section)}\s*\n(.*?)(?=^##|\Z)"
        match = re.search(pattern, content, re.DOTALL | re.IGNORECASE | re.MULTILINE)

        if not match:
            console.print(f"[red]Missing required section: {section}[/red]")
            return False

        section_content = match.group(1).strip()
        if not section_content or _is_placeholder_content(section_content):
            console.print(
                f"[red]Section '{section}' is empty or contains only placeholder text.[/red]"
            )
            return False

    return True


def _is_placeholder_content(content: str) -> bool:
    """Check if content is just placeholder text from the template.

    Args:
        content: Section content to check

    Returns:
        True if content appears to be placeholder text
    """
    placeholder_patterns = [
        r"^brief summary",
        r"^why this decision",
        r"^issue #xx",
    ]
    content_lower = content.lower().strip()
    return any(re.match(pattern, content_lower) for pattern in placeholder_patterns)


def _prepare_editor_template(title: str, number: int, date: str) -> str:
    """Prepare the editor template with title, number, and date filled in.

    Args:
        title: ADR title
        number: ADR number
        date: Date string (YYYY-MM-DD format)

    Returns:
        Template content ready for editing
    """
    adr_template = get_adr_template()
    template = adr_template.editor_template

    # Replace placeholders
    template = template.replace("ADR-NNNN: Title", f"ADR-{number:04d}: {title}")
    template = template.replace("ADR-NNNN:", f"ADR-{number:04d}:")
    template = template.replace("YYYY-MM-DD", date)

    return template


def task_adr() -> dict[str, Any]:
    """Create a new Architecture Decision Record (ADR).

    Creates a new ADR file with the next sequential number.
    Required sections are determined by the ADR template file.

    Three modes:
    1. Interactive (default): Opens $EDITOR with template
    2. --body-file: Reads body from a file
    3. --title + --body: Provides content directly (for AI/scripts)

    Examples:
        Interactive:  doit adr --title="Use Redis for caching"
        From file:    doit adr --title="Use Redis" --body-file=adr.md
        Direct:       doit adr --title="Use Redis" --body="## Status\\nAccepted\\n..."
    """

    def create_adr(
        title: str | None = None,
        body: str | None = None,
        body_file: str | None = None,
    ) -> None:
        console = Console()
        console.print()
        console.print(
            Panel.fit(
                "[bold cyan]Creating Architecture Decision Record[/bold cyan]",
                border_style="cyan",
            )
        )
        console.print()

        # Ensure ADR directory exists
        ADR_DIR.mkdir(parents=True, exist_ok=True)

        # Get title if not provided
        if not title:
            console.print("[cyan]ADR title:[/cyan]")
            title = input("> ").strip()
            if not title:
                console.print("[red]Title is required.[/red]")
                sys.exit(1)

        # Generate filename and number
        number = _get_next_adr_number()
        slug = _title_to_slug(title)
        filename = f"{number:04d}-{slug}.md"
        adr_path = ADR_DIR / filename
        today = datetime.now().strftime("%Y-%m-%d")

        console.print(f"[dim]ADR number: {number:04d}[/dim]")
        console.print(f"[dim]Filename: {filename}[/dim]")

        # Show required sections
        required = get_adr_required_sections()
        console.print(f"[dim]Required sections: {', '.join(required)}[/dim]")

        # Determine body content
        if body_file:
            # Mode 2: Read from file
            body_content = _read_body_file(body_file, console)
            if body_content is None:
                sys.exit(1)
        elif body:
            # Mode 3: Direct body provided
            body_content = body
        else:
            # Mode 1: Interactive editor
            template = _prepare_editor_template(title, number, today)

            console.print(
                "[dim]Opening editor with ADR template. Fill in the sections, save, and exit.[/dim]"
            )
            body_content = _open_editor_with_template(template)
            if body_content is None:
                console.print("[yellow]Aborted.[/yellow]")
                sys.exit(0)

        # For non-interactive modes, ensure header is correct
        if body_file or body:
            # Check if content already has a header
            if not body_content.startswith("# ADR-"):
                # Prepend the header
                body_content = f"# ADR-{number:04d}: {title}\n\n{body_content}"
            else:
                # Replace the header with correct number
                body_content = re.sub(
                    r"^# ADR-\d+: .+",
                    f"# ADR-{number:04d}: {title}",
                    body_content,
                )

            # Ensure date is set
            if "YYYY-MM-DD" in body_content:
                body_content = body_content.replace("YYYY-MM-DD", today)

        # Validate content
        if not _validate_adr_content(body_content, console):
            console.print("[red]ADR content validation failed.[/red]")
            sys.exit(1)

        # Write ADR file
        adr_path.write_text(body_content + "\n")

        console.print()
        console.print(
            Panel.fit(
                f"[bold green]ADR created successfully![/bold green]\n\n{adr_path}",
                border_style="green",
            )
        )

    return {
        "actions": [create_adr],
        "params": [
            {
                "name": "title",
                "long": "title",
                "default": None,
                "help": "ADR title (e.g., 'Use Redis for caching')",
            },
            {
                "name": "body",
                "long": "body",
                "default": None,
                "help": "ADR body content (markdown)",
            },
            {
                "name": "body_file",
                "long": "body-file",
                "default": None,
                "help": "Read body from file",
            },
        ],
        "title": title_with_actions,
    }

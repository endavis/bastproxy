"""Architecture Decision Records (ADR) doit tasks."""

import json
import os
import re
import subprocess  # nosec B404  # subprocess is required for doit tasks
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from doit.tools import title_with_actions
from rich.console import Console
from rich.panel import Panel

from tools.doit.base import verbatim
from tools.doit.templates import (
    ADR_EDITOR_HEADER,
    FRONTMATTER_PATTERN,
    get_adr_required_sections,
    get_adr_template,
)

if TYPE_CHECKING:
    from rich.console import Console as ConsoleType

ADR_DIR = Path("docs/decisions")
TEMPLATE_SERIES_FLOOR = 9001


def _get_next_adr_number(template: bool = False) -> int:
    """Get the next available ADR number for the requested series.

    Scans existing ADR files in ``ADR_DIR`` and returns the next sequential
    number for the series. Both series share the same directory; they are
    distinguished by the numeric prefix:

    - Project series (``template=False``): 0XXX, starting at 1.
    - Template series (``template=True``): 9XXX, starting at
      ``TEMPLATE_SERIES_FLOOR`` (9001) when no template ADRs exist yet.

    Args:
        template: If True, scan only the template (9XXX) series. If False,
            scan only the project (0XXX) series.

    Returns:
        Next ADR number. For the project series: ``max + 1``, floor 1.
        For the template series: ``max + 1``, floor ``TEMPLATE_SERIES_FLOOR``.
    """
    if template:
        pattern = re.compile(r"^9\d{3}-.*\.md$")
        floor = TEMPLATE_SERIES_FLOOR
    else:
        pattern = re.compile(r"^0\d{3}-.*\.md$")
        floor = 1

    if not ADR_DIR.exists():
        return floor

    max_number = 0
    number_pattern = re.compile(r"^(\d{4})-.*\.md$")

    for file in ADR_DIR.iterdir():
        if file.name == "adr-template.md" or file.name == "README.md":
            continue
        if not pattern.match(file.name):
            continue
        match = number_pattern.match(file.name)
        if match:
            number = int(match.group(1))
            max_number = max(max_number, number)

    if max_number == 0:
        return floor

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
    with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, encoding="utf-8") as f:
        f.write(template)
        temp_path = f.name

    try:
        # Open editor
        console.print(verbatim(f"Opening {editor}...", "dim"))
        result = subprocess.run([editor, temp_path])

        if result.returncode != 0:
            console.print("[red]Editor exited with error.[/red]")
            return None

        # Read the edited content
        with open(temp_path, encoding="utf-8") as f:
            content = f.read()

        # Remove the editor instructions. Left in, they would sit above the
        # frontmatter, which only counts as frontmatter at the top (#841).
        header_lines = set(ADR_EDITOR_HEADER.splitlines()) - {""}
        content = "\n".join(line for line in content.split("\n") if line not in header_lines)

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
        console.print(verbatim(f"File not found: {file_path}", "red"))
        return None

    try:
        return path.read_text(encoding="utf-8")
    except Exception as e:
        console.print(verbatim(f"Error reading file: {e}", "red"))
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


def _set_frontmatter_title(content: str, heading: str) -> str:
    """Set the ``title`` in *content*'s frontmatter to *heading*, adding it if missing.

    The title is written double-quoted: every ADR heading holds a colon, which
    YAML reads as a mapping unless the scalar is quoted, and a JSON string is a
    valid YAML one whatever quotes or backslashes the title contains.

    Args:
        content: ADR markdown, with or without a frontmatter block
        heading: The ADR heading, e.g. ``ADR-0001: Use Redis``

    Returns:
        *content* with the title set, or unchanged if it has no frontmatter
    """
    match = FRONTMATTER_PATTERN.match(content)
    if not match:
        return content

    line = f"title: {json.dumps(heading, ensure_ascii=False)}"
    block, found = re.subn(r"^title:.*$", lambda _: line, match.group(0), count=1, flags=re.M)
    if not found:
        opening, rest = block.split("\n", 1)
        block = f"{opening}\n{line}\n{rest}"
    return block + content[match.end() :]


_NO_PROJECT_ADRS = "_(No project-level ADRs yet.)_"
_YAML_SPECIALS = re.compile(r"[:#\[\]{},&*!|>'\"%@`?]")


def _adr_status(content: str) -> str:
    """Return the first non-empty line of the ``## Status`` section, or ``Accepted``.

    Args:
        content: ADR markdown

    Returns:
        The status text
    """
    match = re.search(
        r"^##\s+Status\s*\n(.*?)(?=^##|\Z)", content, re.DOTALL | re.IGNORECASE | re.MULTILINE
    )
    if match:
        for line in match.group(1).splitlines():
            if line.strip():
                return line.strip()
    return "Accepted"


def _add_to_index(
    readme: Path, number: int, title: str, filename: str, status: str, template: bool
) -> bool:
    """Add a row for the ADR to the series table under ``## Index`` in *readme*.

    The file is left unchanged when it, the ``## Index`` section or the series
    table is missing. A row already linking *filename* is not added twice.

    Args:
        readme: Path of the ADR index file
        number: ADR number
        title: ADR title
        filename: ADR file name, used as the link target
        status: Status text for the row
        template: True for the template (9XXX) series table, False for the project one

    Returns:
        True if the index lists the ADR afterwards, False if it could not be placed
    """
    if not readme.is_file():
        return False
    lines = readme.read_text(encoding="utf-8").split("\n")

    index_at = next((i for i, line in enumerate(lines) if re.match(r"##\s+Index\s*$", line)), None)
    if index_at is None:
        return False
    series = r"\(9XXX\)" if template else r"\(0001\+\)"
    heading_at = next(
        (i for i in range(index_at + 1, len(lines)) if re.match(rf"###\s.*{series}\s*$", lines[i])),
        None,
    )
    if heading_at is None:
        return False
    end = next(
        (i for i in range(heading_at + 1, len(lines)) if lines[i].startswith("#")), len(lines)
    )
    table = [i for i in range(heading_at + 1, end) if lines[i].startswith("|")]
    if len(table) < 2:
        return False
    if any(f"]({filename})" in lines[i] for i in table):
        return True

    row = f"| [{number:04d}]({filename}) | {title.replace('|', chr(92) + '|')} | {status} |"
    lines.insert(table[-1] + 1, row)
    if not template:
        end += 1
        for i in range(table[-1] + 2, end):
            if lines[i].strip() == _NO_PROJECT_ADRS:
                after_blank = i + 1 >= len(lines) or not lines[i + 1].strip()
                del lines[i]
                if after_blank and lines[i - 1] == "":
                    del lines[i - 1]
                break
    readme.write_text("\n".join(lines), encoding="utf-8")
    return True


def _add_to_nav(mkdocs: Path, number: int, title: str, nav_path: str) -> bool:
    """Add the ADR to the ``- Decisions:`` list under ``nav:`` in *mkdocs*, in numeric order.

    The edit is text-based, so comments and layout in the file survive. The file
    is left unchanged when it or the list is missing. An entry already pointing
    at *nav_path* is not added twice.

    Args:
        mkdocs: Path of ``mkdocs.yml``
        number: ADR number
        title: ADR title
        nav_path: Path of the ADR relative to ``docs_dir``

    Returns:
        True if the nav lists the ADR afterwards, False if it could not be placed
    """
    if not mkdocs.is_file():
        return False
    lines = mkdocs.read_text(encoding="utf-8").split("\n")

    nav_at = next((i for i, line in enumerate(lines) if re.match(r"nav:\s*(#.*)?$", line)), None)
    if nav_at is None:
        return False
    decisions_at = next(
        (i for i in range(nav_at + 1, len(lines)) if re.match(r"\s*- Decisions:\s*$", lines[i])),
        None,
    )
    if decisions_at is None:
        return False
    base = len(lines[decisions_at]) - len(lines[decisions_at].lstrip())

    def indent(line: str) -> int:
        return len(line) - len(line.lstrip())

    child: int | None = None
    block_end = decisions_at + 1
    for i in range(decisions_at + 1, len(lines)):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if indent(line) <= base:
            break
        if child is None:
            child = indent(line)
        block_end = i + 1
    if child is None:
        return False

    items = [
        i
        for i in range(decisions_at + 1, block_end)
        if lines[i].strip() and indent(lines[i]) == child and lines[i].lstrip().startswith("- ")
    ]
    if any(lines[i].rstrip().endswith(f": {nav_path}") for i in items):
        return True

    label = f"ADR-{number:04d} {title}"
    if _YAML_SPECIALS.search(label):
        label = json.dumps(label, ensure_ascii=False)
    entry = f"{' ' * child}- {label}: {nav_path}"

    insert_at = items[-1] + 1
    for i in items:
        found = re.search(r"(\d{4})-[^/\s]*\.md\s*$", lines[i])
        if found and int(found.group(1)) > number:
            insert_at = i
            break
    lines.insert(insert_at, entry)
    mkdocs.write_text("\n".join(lines), encoding="utf-8")
    return True


def _register_adr(
    console: "ConsoleType",
    number: int,
    title: str,
    filename: str,
    content: str,
    template: bool,
) -> None:
    """Add the new ADR to the ADR index and the mkdocs nav, or say what to do by hand.

    Both paths derive from ``ADR_DIR``, never the working directory: the index is
    ``ADR_DIR/README.md`` and ``mkdocs.yml`` sits two levels above ``ADR_DIR``
    (``docs/decisions`` under the repository root).

    Args:
        console: Rich console for output
        number: ADR number
        title: ADR title
        filename: ADR file name
        content: The ADR text, read for its status
        template: Which series the ADR belongs to
    """
    readme = ADR_DIR / "README.md"
    mkdocs = ADR_DIR.parent.parent / "mkdocs.yml"
    nav_path = f"{ADR_DIR.name}/{filename}"
    label = f"ADR-{number:04d}: {title}"

    if _add_to_index(readme, number, title, filename, _adr_status(content), template):
        console.print(verbatim(f"Added to {readme}", "dim"))
    else:
        console.print(
            verbatim(f"Could not update the ADR index {readme}; add a row for {label}.", "yellow")
        )
    if _add_to_nav(mkdocs, number, title, nav_path):
        console.print(verbatim(f"Added to {mkdocs}", "dim"))
    else:
        console.print(
            verbatim(
                f"Could not update the nav in {mkdocs}; add {nav_path} under Decisions.", "yellow"
            )
        )


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

    # The frontmatter block is found only at the start, so set its title past the header.
    content = adr_template.editor_template.removeprefix(ADR_EDITOR_HEADER)
    template = ADR_EDITOR_HEADER + _set_frontmatter_title(content, f"ADR-{number:04d}: {title}")

    # Replace placeholders
    template = template.replace("ADR-NNNN: Title", f"ADR-{number:04d}: {title}")
    template = template.replace("ADR-NNNN:", f"ADR-{number:04d}:")
    template = template.replace("YYYY-MM-DD", date)

    return template


def task_adr() -> dict[str, Any]:
    """Create a new Architecture Decision Record (ADR).

    Creates a new ADR file with the next sequential number.
    Required sections are determined by the ADR template file.

    Two series live side-by-side in ``docs/decisions/``:

    - Project series (0XXX) — the default.
    - Template-meta series (9XXX) — pass ``--template``.

    Three input modes:
    1. Interactive (default): Opens $EDITOR with template
    2. --body-file: Reads body from a file
    3. --title + --body: Provides content directly (for AI/scripts)

    Examples:
        Project (0XXX):    doit adr --title="Use Redis for caching"
        From file:         doit adr --title="Use Redis" --body-file=adr.md
        Direct:            doit adr --title="Use Redis" --body="## Status\\nAccepted\\n..."
        Template (9XXX):   doit adr --title="Use some tool" --template
        Template w/ file:  doit adr --title="Use some tool" --template --body-file=adr.md
    """

    def create_adr(
        title: str | None = None,
        body: str | None = None,
        body_file: str | None = None,
        template: bool = False,
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
        number = _get_next_adr_number(template=template)
        slug = _title_to_slug(title)
        filename = f"{number:04d}-{slug}.md"
        adr_path = ADR_DIR / filename
        today = datetime.now().strftime("%Y-%m-%d")

        series_label = "template-meta (9XXX)" if template else "project (0XXX)"
        console.print(f"[dim]ADR number: {number:04d} ({series_label})[/dim]")
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
            editor_template = _prepare_editor_template(title, number, today)

            console.print(
                "[dim]Opening editor with ADR template. Fill in the sections, save, and exit.[/dim]"
            )
            body_content = _open_editor_with_template(editor_template)
            if body_content is None:
                console.print("[yellow]Aborted.[/yellow]")
                sys.exit(0)

        # For non-interactive modes, ensure frontmatter and header are correct
        if body_file or body:
            # Keep the body's own frontmatter, or start from the template's
            match = FRONTMATTER_PATTERN.match(body_content)
            if match:
                frontmatter = match.group(0)
                body_content = body_content[match.end() :].lstrip("\n")
            else:
                frontmatter = get_adr_template().frontmatter

            # Check if content already has a header
            if not body_content.startswith("# ADR-"):
                # Prepend the header
                body_content = f"# ADR-{number:04d}: {title}\n\n{body_content}"
            else:
                # Replace the header with correct number
                # Any first heading that starts "# ADR-": a number or the NNNN placeholder.
                # A function replacement keeps a backslash in the title literal.
                heading = f"# ADR-{number:04d}: {title}"
                body_content = re.sub(r"^# ADR-[^\n]*", lambda _: heading, body_content, count=1)

            if frontmatter:
                body_content = _set_frontmatter_title(
                    f"{frontmatter}\n{body_content}", f"ADR-{number:04d}: {title}"
                )

            # Ensure date is set
            if "YYYY-MM-DD" in body_content:
                body_content = body_content.replace("YYYY-MM-DD", today)

        # Validate content
        if not _validate_adr_content(body_content, console):
            console.print("[red]ADR content validation failed.[/red]")
            sys.exit(1)

        # Write ADR file. Exactly one final newline: a body file usually ends
        # with one already, and a second fails end-of-file-fixer (#859).
        adr_path.write_text(body_content.rstrip("\n") + "\n", encoding="utf-8")

        console.print()
        console.print(
            Panel.fit(
                f"[bold green]ADR created successfully![/bold green]\n\n{adr_path}",
                border_style="green",
            )
        )

        _register_adr(console, number, title, filename, body_content, template)

        # The table of contents lists the description next to the title (#841)
        placeholder = get_adr_template().placeholder_description
        if placeholder and placeholder in body_content:
            console.print(
                "[yellow]Replace the placeholder description in the ADR's frontmatter "
                "with one sentence that says what was decided.[/yellow]"
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
            {
                "name": "template",
                "long": "template",
                "type": bool,
                "default": False,
                "help": (
                    "Create a template-meta ADR (9XXX series) "
                    "instead of a project-level ADR (0XXX series)"
                ),
            },
        ],
        "title": title_with_actions,
    }

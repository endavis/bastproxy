"""Tests for adr.py doit tasks."""

import re
from datetime import date
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml
from rich.console import Console

from tools.doit import adr as adr_module
from tools.doit.adr import (
    TEMPLATE_SERIES_FLOOR,
    _get_next_adr_number,
    _is_placeholder_content,
    _open_editor_with_template,
    _read_body_file,
    _title_to_slug,
    _validate_adr_content,
)
from tools.doit.templates import FRONTMATTER_PATTERN, get_adr_template

# FORCE_COLOR makes Rich color captured output, and the codes split substrings such as `[x]`.
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


class TestTitleToSlug:
    """Tests for _title_to_slug function."""

    def test_simple_title(self) -> None:
        """Test conversion of simple title."""
        assert _title_to_slug("Use uv for package management") == "use-uv-for-package-management"

    def test_title_with_special_chars(self) -> None:
        """Test removal of special characters."""
        assert _title_to_slug("Use ruff (linting & formatting)") == "use-ruff-linting-formatting"

    def test_title_with_multiple_spaces(self) -> None:
        """Test collapsing of multiple spaces."""
        assert _title_to_slug("Use  doit   for   automation") == "use-doit-for-automation"

    def test_title_with_underscores(self) -> None:
        """Test conversion of underscores to hyphens."""
        assert _title_to_slug("use_redis_for_caching") == "use-redis-for-caching"

    def test_title_with_mixed_case(self) -> None:
        """Test conversion to lowercase."""
        assert _title_to_slug("Use PostgreSQL Database") == "use-postgresql-database"

    def test_title_with_numbers(self) -> None:
        """Test preservation of numbers."""
        assert _title_to_slug("Python 3.12 compatibility") == "python-312-compatibility"

    def test_title_with_leading_trailing_special(self) -> None:
        """Test trimming of leading/trailing special characters."""
        assert _title_to_slug("  --Use Redis--  ") == "use-redis"

    def test_empty_title(self) -> None:
        """Test handling of empty title."""
        assert _title_to_slug("") == ""

    def test_title_with_only_special_chars(self) -> None:
        """Test handling of title with only special characters."""
        assert _title_to_slug("!@#$%") == ""


class TestGetNextAdrNumber:
    """Tests for _get_next_adr_number function."""

    def test_returns_positive_integer(self) -> None:
        """Smoke test against the real ADR_DIR: returns a positive integer."""
        result = _get_next_adr_number()
        assert isinstance(result, int)
        assert result >= 1

    def test_project_series_returns_1_when_no_project_adrs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Project series starts at 1 when only template (9XXX) ADRs exist."""
        for n in range(9001, 9016):
            (tmp_path / f"{n}-example.md").write_text(f"# ADR-{n}", encoding="utf-8")

        monkeypatch.setattr(adr_module, "ADR_DIR", tmp_path)
        assert _get_next_adr_number(template=False) == 1

    def test_template_series_returns_9016_given_9015_max(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Template series returns max + 1 when template ADRs already exist."""
        for n in range(9001, 9016):
            (tmp_path / f"{n}-example.md").write_text(f"# ADR-{n}", encoding="utf-8")

        monkeypatch.setattr(adr_module, "ADR_DIR", tmp_path)
        assert _get_next_adr_number(template=True) == 9016

    def test_template_series_returns_floor_when_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Template series returns the floor (9001) when no template ADRs exist."""
        # Project ADRs present, but no template ADRs.
        (tmp_path / "0001-something.md").write_text("# ADR-0001", encoding="utf-8")

        monkeypatch.setattr(adr_module, "ADR_DIR", tmp_path)
        assert _get_next_adr_number(template=True) == TEMPLATE_SERIES_FLOOR

    def test_project_series_returns_max_plus_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Project series returns max + 1 when project ADRs already exist."""
        (tmp_path / "0001-first.md").write_text("# ADR-0001", encoding="utf-8")
        (tmp_path / "0002-second.md").write_text("# ADR-0002", encoding="utf-8")

        monkeypatch.setattr(adr_module, "ADR_DIR", tmp_path)
        assert _get_next_adr_number(template=False) == 3

    def test_series_isolation(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Template and project series are counted independently in the shared directory."""
        (tmp_path / "0001-first.md").write_text("# ADR-0001", encoding="utf-8")
        (tmp_path / "0002-second.md").write_text("# ADR-0002", encoding="utf-8")
        (tmp_path / "9001-a.md").write_text("# ADR-9001", encoding="utf-8")
        (tmp_path / "9015-b.md").write_text("# ADR-9015", encoding="utf-8")

        monkeypatch.setattr(adr_module, "ADR_DIR", tmp_path)
        assert _get_next_adr_number(template=False) == 3
        assert _get_next_adr_number(template=True) == 9016

    def test_readme_and_template_files_ignored(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """README.md and adr-template.md must not influence numbering."""
        (tmp_path / "README.md").write_text("# README", encoding="utf-8")
        (tmp_path / "adr-template.md").write_text("# ADR-NNNN", encoding="utf-8")

        monkeypatch.setattr(adr_module, "ADR_DIR", tmp_path)
        assert _get_next_adr_number(template=False) == 1
        assert _get_next_adr_number(template=True) == TEMPLATE_SERIES_FLOOR

    def test_missing_directory_returns_floor(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If ADR_DIR does not exist, both series return their floor."""
        missing = tmp_path / "does_not_exist"
        monkeypatch.setattr(adr_module, "ADR_DIR", missing)

        assert _get_next_adr_number(template=False) == 1
        assert _get_next_adr_number(template=True) == TEMPLATE_SERIES_FLOOR


class TestIsPlaceholderContent:
    """Tests for _is_placeholder_content function."""

    def test_placeholder_brief_summary(self) -> None:
        """Test detection of 'Brief summary' placeholder."""
        assert _is_placeholder_content("Brief summary of what was decided.") is True

    def test_placeholder_why_decision(self) -> None:
        """Test detection of 'Why this decision' placeholder."""
        assert _is_placeholder_content("Why this decision was made.") is True

    def test_placeholder_issue_xx(self) -> None:
        """Test detection of 'Issue #XX' placeholder."""
        assert _is_placeholder_content("Issue #XX: Description") is True

    def test_real_content(self) -> None:
        """Test that real content is not detected as placeholder."""
        assert _is_placeholder_content("Use Redis for caching to improve performance.") is False

    def test_real_issue_reference(self) -> None:
        """Test that real issue references are not detected as placeholder."""
        assert _is_placeholder_content("Issue #123: Add caching support") is False


class TestValidateAdrContent:
    """Tests for _validate_adr_content function."""

    def _mock_console(self) -> MagicMock:
        """Create a mock console for testing."""
        console = MagicMock()
        console.file = StringIO()
        return console

    @patch("tools.doit.adr.get_adr_required_sections")
    def test_valid_content(self, mock_get_sections: MagicMock) -> None:
        """Test validation of valid ADR content."""
        mock_get_sections.return_value = ["Status", "Decision", "Rationale"]
        content = """# ADR-0001: Test

## Status

Accepted

## Decision

Use Redis for caching.

## Rationale

Improves performance significantly.

## Related Issues

- Issue #42: Add caching
"""
        console = self._mock_console()
        assert _validate_adr_content(content, console) is True

    @patch("tools.doit.adr.get_adr_required_sections")
    def test_missing_decision_section(self, mock_get_sections: MagicMock) -> None:
        """Test validation fails when Decision section is missing."""
        mock_get_sections.return_value = ["Status", "Decision", "Rationale"]
        content = """# ADR-0001: Test

## Status

Accepted

## Rationale

Some rationale.
"""
        console = self._mock_console()
        assert _validate_adr_content(content, console) is False

    @patch("tools.doit.adr.get_adr_required_sections")
    def test_missing_rationale_section(self, mock_get_sections: MagicMock) -> None:
        """Test validation fails when Rationale section is missing."""
        mock_get_sections.return_value = ["Status", "Decision", "Rationale"]
        content = """# ADR-0001: Test

## Status

Accepted

## Decision

Use Redis.
"""
        console = self._mock_console()
        assert _validate_adr_content(content, console) is False

    @patch("tools.doit.adr.get_adr_required_sections")
    def test_empty_decision_section(self, mock_get_sections: MagicMock) -> None:
        """Test validation fails when Decision section is empty."""
        mock_get_sections.return_value = ["Status", "Decision", "Rationale"]
        content = """# ADR-0001: Test

## Status

Accepted

## Decision

## Rationale

Some rationale.
"""
        console = self._mock_console()
        assert _validate_adr_content(content, console) is False

    @patch("tools.doit.adr.get_adr_required_sections")
    def test_placeholder_content_rejected(self, mock_get_sections: MagicMock) -> None:
        """Test validation fails when section has placeholder content."""
        mock_get_sections.return_value = ["Status", "Decision", "Rationale"]
        content = """# ADR-0001: Test

## Status

Accepted

## Decision

Brief summary of what was decided.

## Rationale

Why this decision was made.
"""
        console = self._mock_console()
        assert _validate_adr_content(content, console) is False

    @patch("tools.doit.adr.get_adr_required_sections")
    def test_uses_template_required_sections(self, mock_get_sections: MagicMock) -> None:
        """Test that validation uses sections from template."""
        # Only require Status and Decision
        mock_get_sections.return_value = ["Status", "Decision"]
        content = """# ADR-0001: Test

## Status

Accepted

## Decision

Use Redis.
"""
        console = self._mock_console()
        assert _validate_adr_content(content, console) is True
        mock_get_sections.assert_called_once()


_VALID_BODY = (
    "## Status\nAccepted\n\n"
    "## Decision\nEnd every ADR with one newline.\n\n"
    "## Rationale\nend-of-file-fixer rewrites any other ending.\n"
)


class TestCreatedAdrEnding:
    """The ADR `doit adr` writes ends with exactly one newline (#859).

    `end-of-file-fixer` rewrites a file that ends with more, which fails the
    commit and makes the author stage and commit again.
    """

    @staticmethod
    def _create(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **source: str) -> str:
        """Run `doit adr --template` with *source* (body or body_file); return the ADR text."""
        adr_dir = tmp_path / "decisions"
        monkeypatch.setattr(adr_module, "ADR_DIR", adr_dir)
        action = adr_module.task_adr()["actions"][0]
        action(title="End with one newline", template=True, **source)
        (adr,) = adr_dir.glob("9*.md")
        return adr.read_text(encoding="utf-8")

    @pytest.mark.parametrize("ending", ["", "\n", "\n\n\n"], ids=["none", "one", "several"])
    def test_body_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ending: str) -> None:
        """Editors save with a final newline, so the usual body file already has one."""
        body_file = tmp_path / "body.md"
        body_file.write_text(_VALID_BODY.rstrip("\n") + ending, encoding="utf-8")

        text = self._create(tmp_path, monkeypatch, body_file=str(body_file))

        assert text.endswith("Rationale\nend-of-file-fixer rewrites any other ending.\n")

    def test_body_string_ending_in_a_newline(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        text = self._create(tmp_path, monkeypatch, body=_VALID_BODY + "\n")

        assert text.endswith("any other ending.\n")
        assert not text.endswith("\n\n")


class TestCreatedAdrFrontmatter:
    """The ADR `doit adr` writes starts with the template's frontmatter, filled in (#841).

    `docs/TABLE_OF_CONTENTS.md` is generated from each document's frontmatter,
    so an ADR without it is listed bare and reaches no audience section.
    """

    @staticmethod
    def _create(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, title: str = "Use Redis", **source: str
    ) -> str:
        """Run `doit adr --template` with *source* (body or body_file); return the ADR text."""
        adr_dir = tmp_path / "decisions"
        monkeypatch.setattr(adr_module, "ADR_DIR", adr_dir)
        action = adr_module.task_adr()["actions"][0]
        action(title=title, template=True, **source)
        (adr,) = adr_dir.glob("9*.md")
        return adr.read_text(encoding="utf-8")

    @staticmethod
    def _meta(text: str) -> dict[str, Any]:
        """Parse the frontmatter *text* starts with."""
        match = FRONTMATTER_PATTERN.match(text)
        assert match, "the ADR does not start with a frontmatter block"
        meta: dict[str, Any] = yaml.safe_load(match.group(1))
        return meta

    def test_body_gets_the_template_frontmatter(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        text = self._create(tmp_path, monkeypatch, body=_VALID_BODY)
        meta = self._meta(text)

        assert meta["title"] == "ADR-9001: Use Redis"
        assert isinstance(meta["date"], date)
        assert meta["audience"] == ["contributors"]
        assert meta["tags"] == ["adr"]
        assert "\n# ADR-9001: Use Redis\n" in text

    def test_title_with_quotes_and_backslashes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        title = 'Quote "this" and C:\\temp'

        text = self._create(tmp_path, monkeypatch, title=title, body=_VALID_BODY)

        assert self._meta(text)["title"] == f"ADR-9001: {title}"

    def test_body_frontmatter_is_kept_and_titled(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        body = "---\ndescription: Cache sessions in Redis\ntags:\n  - adr\n---\n\n" + _VALID_BODY

        text = self._create(tmp_path, monkeypatch, body=body)

        assert self._meta(text) == {
            "title": "ADR-9001: Use Redis",
            "description": "Cache sessions in Redis",
            "tags": ["adr"],
        }
        assert text.count("---\n") == 2

    def test_body_frontmatter_title_is_corrected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        body = '---\ntitle: "ADR-0042: Old name"\ndescription: Cache\n---\n' + _VALID_BODY

        text = self._create(tmp_path, monkeypatch, body=body)

        assert self._meta(text)["title"] == "ADR-9001: Use Redis"

    def test_warns_while_the_description_is_the_placeholder(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        text = self._create(tmp_path, monkeypatch, body=_VALID_BODY)

        assert self._meta(text)["description"] == get_adr_template().placeholder_description
        assert "Replace the placeholder description" in capsys.readouterr().out

    def test_no_warning_once_the_description_is_written(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        body = "---\ndescription: Cache sessions in Redis\n---\n" + _VALID_BODY

        self._create(tmp_path, monkeypatch, body=body)

        assert "Replace the placeholder description" not in capsys.readouterr().out

    def test_editor_instructions_stay_out_of_the_adr(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mock_subprocess: MagicMock
    ) -> None:
        """Left in, they sat above the frontmatter, so it no longer counted as frontmatter."""

        def edit(cmd: list[str]) -> MagicMock:
            path = Path(cmd[1])
            text = path.read_text(encoding="utf-8")
            text = text.replace("One sentence that says what was decided.", "Cache in Redis")
            text = text.replace("Brief summary of what was decided.", "Use Redis.")
            text = text.replace("Why this decision was made.", "It is fast.")
            path.write_text(text, encoding="utf-8")
            return MagicMock(returncode=0)

        monkeypatch.setenv("EDITOR", "stand-in-editor")
        mock_subprocess.register({("stand-in-editor",): edit})

        text = self._create(tmp_path, monkeypatch)

        assert text.startswith("---\n")
        assert "Lines starting with #" not in text
        meta = self._meta(text)
        assert meta["title"] == "ADR-9001: Use Redis"
        assert meta["description"] == "Cache in Redis"
        assert isinstance(meta["date"], date)


class TestReadBodyFile:
    """`doit adr --body-file` reads through its own `_read_body_file`."""

    @pytest.mark.parametrize("name", ["[x].md", "[/x].md", r"C:\notes\[1].md", ":memo:.md"])
    def test_missing_file_keeps_a_bracketed_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
    ) -> None:
        """The path is the user's `--body-file` value, text rather than markup (#907).

        Relative to tmp_path, so the only backslash before a `[` is the one a name spells out.
        A Windows path keeps it, and `:memo:` stays text (#914).
        """
        monkeypatch.chdir(tmp_path)
        # color_system=None: no ANSI codes, even when FORCE_COLOR is set.
        console = Console(file=StringIO(), soft_wrap=True, color_system=None)

        assert _read_body_file(name, console) is None
        assert f"File not found: {name}" in console.file.getvalue()  # type: ignore[attr-defined]


class TestOpenEditorWithTemplate:
    """The ADR editor."""

    @pytest.mark.parametrize(
        "editor", ["/opt/[x]/vi", "/opt/[/x]/vi", r"C:\tools\[1]\vi.exe", "/opt/:memo:/vi"]
    )
    def test_prints_the_editor_verbatim(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], editor: str
    ) -> None:
        """`$EDITOR` is the user's text, not markup (#920). It fails here, so nothing is read."""
        monkeypatch.setenv("COLUMNS", "1000")
        with (
            patch("tools.doit.adr._get_editor", return_value=editor),
            patch("tools.doit.adr.subprocess.run", return_value=MagicMock(returncode=1)),
        ):
            assert _open_editor_with_template("body") is None

        assert f"Opening {editor}..." in _ANSI.sub("", capsys.readouterr().out).splitlines()

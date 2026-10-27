"""Tests for tools/generate_doc_toc.py.

A frontmatter block that is present but does not parse used to read as no
block at all, so the generator's "without frontmatter" count gave no hint why
(#841). The usual cause is an unquoted colon, and every ADR title has one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools import generate_doc_toc as toc

UNQUOTED_COLON = "---\ntitle: ADR-0001: Use X\n---\n\n# ADR-0001: Use X\n"


def _doc(root: Path, text: str, name: str = "doc.md") -> Path:
    """Write *text* to *name* under *root* and return its path."""
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class TestExtractFrontmatter:
    """extract_frontmatter tells a malformed block from an absent one."""

    def test_no_block(self, tmp_path: Path) -> None:
        assert toc.extract_frontmatter(_doc(tmp_path, "# Title\n")) == {}

    def test_quoted_title_with_a_colon(self, tmp_path: Path) -> None:
        path = _doc(tmp_path, '---\ntitle: "ADR-0001: Use X"\ndescription: Why\n---\n')

        assert toc.extract_frontmatter(path) == {"title": "ADR-0001: Use X", "description": "Why"}

    def test_unquoted_colon_is_malformed(self, tmp_path: Path) -> None:
        path = _doc(tmp_path, UNQUOTED_COLON)

        with pytest.raises(toc.MalformedFrontmatterError) as excinfo:
            toc.extract_frontmatter(path)

        assert str(excinfo.value) == "mapping values are not allowed here (line 2)"

    def test_unclosed_block_is_malformed(self, tmp_path: Path) -> None:
        path = _doc(tmp_path, "---\ntitle: X\n\n# X\n")

        with pytest.raises(toc.MalformedFrontmatterError, match="no closing --- line"):
            toc.extract_frontmatter(path)

    def test_block_that_is_not_a_mapping_is_malformed(self, tmp_path: Path) -> None:
        path = _doc(tmp_path, "---\n- a\n- b\n---\n")

        with pytest.raises(toc.MalformedFrontmatterError, match="is a list, not a mapping"):
            toc.extract_frontmatter(path)

    def test_empty_block(self, tmp_path: Path) -> None:
        assert toc.extract_frontmatter(_doc(tmp_path, "---\n---\n\n# X\n")) == {}

    def test_dashes_inside_a_value_do_not_close_the_block(self, tmp_path: Path) -> None:
        path = _doc(tmp_path, "---\ndescription: before --- after\n---\n")

        assert toc.extract_frontmatter(path) == {"description": "before --- after"}


def test_title_skips_the_whole_block(tmp_path: Path) -> None:
    """A heading-like YAML comment after a `---` in a value is not the document's title."""
    path = _doc(tmp_path, "---\ndescription: before --- after\n# a comment\n---\n\n# Heading\n")

    assert toc.get_title(path, {}) == "Heading"


class TestCollectDocs:
    def test_malformed_files_are_listed_apart(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(toc, "DOCS_DIR", tmp_path)
        _doc(tmp_path, "---\ndescription: Fine\n---\n", "good.md")
        _doc(tmp_path, "# No frontmatter\n", "bare.md")
        _doc(tmp_path, UNQUOTED_COLON, "broken.md")

        docs, malformed = toc.collect_docs()

        assert [(path.name, meta) for path, meta in docs] == [
            ("bare.md", {}),
            ("broken.md", {}),
            ("good.md", {"description": "Fine"}),
        ]
        assert [(path.name, reason) for path, reason in malformed] == [
            ("broken.md", "mapping values are not allowed here (line 2)")
        ]

    def test_skips_the_toc_and_the_adr_template(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Exclusions are paths under docs/, so an unrelated file of the same name is kept."""
        monkeypatch.setattr(toc, "DOCS_DIR", tmp_path)
        names = [
            "TABLE_OF_CONTENTS.md",
            "decisions/adr-template.md",
            "decisions/0001-use-x.md",
            "examples/adr-template.md",
        ]
        for name in names:
            _doc(tmp_path, "---\ndescription: X\n---\n", name)

        docs, _ = toc.collect_docs()

        assert [path.relative_to(tmp_path).as_posix() for path, _ in docs] == [
            "decisions/0001-use-x.md",
            "examples/adr-template.md",
        ]


def test_main_names_each_malformed_file_and_why(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(toc, "DOCS_DIR", tmp_path)
    monkeypatch.setattr(toc, "TOC_FILE", tmp_path / "TABLE_OF_CONTENTS.md")
    _doc(tmp_path, "---\ndescription: Fine\n---\n", "good.md")
    _doc(tmp_path, "# No frontmatter\n", "bare.md")
    broken = _doc(tmp_path, UNQUOTED_COLON, "broken.md")

    toc.main()

    out = capsys.readouterr().out
    assert "  - 1 with frontmatter\n" in out
    assert "  - 1 without frontmatter\n" in out
    assert "  - 1 with frontmatter that does not parse\n" in out
    assert f"{broken}: mapping values are not allowed here (line 2)\n" in out

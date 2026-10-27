"""Every document under docs/ carries frontmatter that parses (#841).

`tools/generate_doc_toc.py` builds `docs/TABLE_OF_CONTENTS.md` from each
document's frontmatter: the audience sections from `audience`, and every entry
from `title` and `description`. A document with no block, or with one that does
not parse, is listed bare and reaches no audience section. Nothing checked
this, and the ADRs were among the documents that went without.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.generate_doc_toc import MalformedFrontmatterError, extract_frontmatter

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = REPO_ROOT / "docs"
ADR_TEMPLATE = DOCS_DIR / "decisions" / "adr-template.md"

# Generated from the other documents' frontmatter, so it has none to check.
GENERATED = {DOCS_DIR / "TABLE_OF_CONTENTS.md"}
DOCS = sorted(set(DOCS_DIR.rglob("*.md")) - GENERATED)
ADRS = sorted(DOCS_DIR.glob("decisions/[0-9]*.md"))


def _frontmatter(path: Path) -> dict:
    """Return *path*'s frontmatter, failing the test with the reason if it does not parse."""
    try:
        return extract_frontmatter(path)
    except MalformedFrontmatterError as e:
        pytest.fail(f"frontmatter does not parse: {e}")


@pytest.mark.parametrize("path", DOCS, ids=lambda p: p.relative_to(DOCS_DIR).as_posix())
def test_doc_has_frontmatter_with_a_description(path: Path) -> None:
    meta = _frontmatter(path)

    assert meta, "no frontmatter"
    assert meta.get("description"), "no description in the frontmatter"


@pytest.mark.parametrize("path", ADRS, ids=lambda p: p.name)
def test_adr_replaces_the_template_description(path: Path) -> None:
    """`doit adr` copies the template's placeholder in; the author writes the real one."""
    placeholder = _frontmatter(ADR_TEMPLATE)["description"]

    assert _frontmatter(path).get("description") != placeholder

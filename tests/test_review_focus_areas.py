"""The review-focus-areas doc is the single source for the focus-area checklists (#956).

Every review and adversarial-review surface — self-action and cross-agent bridge alike —
carries one pointer sentence to `docs/development/ai/review-focus-areas.md` rather than a
copy of the checklist text (enforced in `tests/test_cross_agent_contract.py`). This module
checks the doc itself has the shape that contract depends on: it exists, parses as a normal
docs page, and has exactly the four non-empty sections the pointer sentence promises.
"""

from __future__ import annotations

import re
from pathlib import Path

from tools.generate_doc_toc import extract_frontmatter

REPO_ROOT = Path(__file__).resolve().parents[1]
DOC = REPO_ROOT / "docs" / "development" / "ai" / "review-focus-areas.md"

# The four focus areas the pointer sentence in every review/adversarial-review surface
# names verbatim: `errors`, `tests`, `types`, `comments` (tests/test_cross_agent_contract.py's
# REVIEW_FOCUS_AREAS_SENTENCE). Each must be its own `##` section.
FOCUS_AREAS = ("errors", "tests", "types", "comments")

_SECTION_RE = re.compile(r"^## (.+)$", re.MULTILINE)


def _sections(text: str) -> dict[str, str]:
    """Return {heading: body} for every `##` section in *text*."""
    matches = list(_SECTION_RE.finditer(text))
    sections = {}
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[match.group(1).strip()] = text[start:end].strip()
    return sections


def test_doc_exists() -> None:
    assert DOC.is_file(), f"missing {DOC.relative_to(REPO_ROOT)}"


def test_doc_has_frontmatter() -> None:
    meta = extract_frontmatter(DOC)
    assert meta.get("title")
    assert meta.get("description")


def test_doc_has_exactly_the_four_focus_area_sections() -> None:
    sections = _sections(DOC.read_text(encoding="utf-8"))
    found = {heading for heading in sections if heading in FOCUS_AREAS}

    assert found == set(FOCUS_AREAS), (
        f"expected exactly the sections {sorted(FOCUS_AREAS)}, found {sorted(found)} "
        f"among {sorted(sections)}"
    )


def test_no_focus_area_section_is_empty() -> None:
    sections = _sections(DOC.read_text(encoding="utf-8"))

    empty = [area for area in FOCUS_AREAS if not sections.get(area, "").strip()]
    assert not empty, f"these focus-area sections have no content: {empty}"

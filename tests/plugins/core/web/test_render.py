"""Page rendering (#424)."""

from html.parser import HTMLParser

import pytest

from bastproxy.plugins.core.web.libs._render import (
    render_index,
    render_page,
    render_table,
    render_table_page,
)

from .conftest import to_html


def test_every_rendered_page_declares_its_language() -> None:
    documents = [
        render_page("t", "a\nb", to_html),
        render_index({}),
        render_table_page("t", "", "<table></table>", to_html),
    ]
    for document in documents:
        assert "<html lang='en'>" in document


def test_title_and_lines_are_escaped() -> None:
    document = render_page("<b>t</b>", ["<script>alert(1)</script>", "@rred"], to_html)
    assert "<title>&lt;b&gt;t&lt;/b&gt;</title>" in document
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in document
    assert "<script" not in document
    assert "<span style='color:#cd0000'>red</span>" in document


def test_a_string_is_accepted() -> None:
    assert "a\nb" in render_page("t", "a\nb", to_html)


# ---- link cells (#766) ----


def _table(rows: list[list[object]]) -> str:
    from bastproxy.plugins.core.web.libs._table import Column, TableQuery

    return render_table(
        [Column("a", "A"), Column("b", "B")],
        rows,
        query=TableQuery(),
        total=len(rows),
        base_path="/t",
        to_html=to_html,
    )


class _Anchors(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str | None, str]] = []
        self._href: str | None = None
        self._text = ""
        self._inside = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a" and any(name == "href" for name, _ in attrs):
            self._inside = True
            self._text = ""
            self._href = dict(attrs)["href"]

    def handle_data(self, data: str) -> None:
        if self._inside:
            self._text += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._inside:
            self.links.append((self._href, self._text))
            self._inside = False


def _anchors(document: str) -> list[tuple[str | None, str]]:
    parser = _Anchors()
    parser.feed(document)
    return parser.links


def test_a_link_cell_renders_an_anchor_with_escaped_text_and_href() -> None:
    document = _table([[{"text": "<b>x</b> & @rred", "href": "/c/m/room?uid=a%27b&x=1"}, "plain"]])
    links = _anchors(document)
    assert ("/c/m/room?uid=a%27b&x=1", "<b>x</b> & red") in links
    assert "<b>x</b>" not in document
    assert "&amp;x=1" in document


@pytest.mark.parametrize(
    "href",
    [
        "javascript:alert(1)",
        "//evil.example/x",
        "http://x.example/",
        "/a\\b",
        "/a b",
        "/a\nb",
        "/a\tb",
        "",
    ],
)
def test_a_link_cell_with_a_bad_href_raises(href: str) -> None:
    with pytest.raises(ValueError, match="link"):
        _table([[{"text": "t", "href": href}, "x"]])


@pytest.mark.parametrize(
    "cell",
    [
        {"text": "t"},
        {"href": "/x"},
        {"text": "t", "href": "/x", "z": 1},
        {"text": 1, "href": "/x"},
        {},
    ],
)
def test_a_malformed_link_cell_raises(cell: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="link cell"):
        _table([[cell, "x"]])


def test_a_non_string_href_raises() -> None:
    with pytest.raises(ValueError, match="same-origin"):
        _table([[{"text": "t", "href": 5}, "x"]])

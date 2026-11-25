"""Page rendering (#424)."""

from bastproxy.plugins.core.web.libs._render import render_page

from .conftest import to_html


def test_title_and_lines_are_escaped() -> None:
    document = render_page("<b>t</b>", ["<script>alert(1)</script>", "@rred"], to_html)
    assert "<title>&lt;b&gt;t&lt;/b&gt;</title>" in document
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in document
    assert "<script" not in document
    assert "<span style='color:#cd0000'>red</span>" in document


def test_a_string_is_accepted() -> None:
    assert "a\nb" in render_page("t", "a\nb", to_html)

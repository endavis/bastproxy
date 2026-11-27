"""Colour codes become spans built only on the tokenizer (#841)."""

from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins.core.colors.plugin._colors import ColorsPlugin


def spans(text: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = ColorsPlugin._api_colorcode_to_spans(MagicMock(), text)
    return result


def ansi_spans(text: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = ColorsPlugin._api_ansicode_to_spans(MagicMock(), text)
    return result


def span(
    text: str, fg: int | None = None, bg: int | None = None, bold: bool = False
) -> dict[str, Any]:
    return {"text": text, "fg": fg, "bg": bg, "bold": bold}


def test_empty_gives_no_spans() -> None:
    assert spans("") == []


def test_plain_text_is_one_default_span() -> None:
    assert spans("plain") == [span("plain")]


def test_dict_keys() -> None:
    assert set(spans("x")[0]) == {"text", "fg", "bg", "bold"}


def test_lowercase_letter() -> None:
    assert spans("@rred") == [span("red", fg=1)]


def test_uppercase_letter_is_bold() -> None:
    assert spans("@Rred") == [span("red", fg=9, bold=True)]


def test_xterm_foreground_and_background() -> None:
    assert spans("@x075a@z010b") == [span("a", fg=75), span("b", fg=75, bg=10)]


def test_xterm_foreground_clears_bold() -> None:
    assert spans("@R@x8t") == [span("t", fg=8)]


def test_reset_clears_everything() -> None:
    assert spans("@R@z010a@wb") == [span("a", fg=9, bg=10, bold=True), span("b")]


def test_adjacent_codes_split_spans_even_when_style_is_unchanged() -> None:
    assert spans("a@rb@rc") == [span("a"), span("b", fg=1), span("c", fg=1)]


def test_codes_without_text_make_no_span() -> None:
    assert spans("@r@g") == []


def test_escapes_show_one_character() -> None:
    assert spans("a@@b@-c") == [span("a@b~c")]


def test_invalid_and_sgr_do_not_split() -> None:
    assert spans("a@!b") == [span("ab")]
    assert spans("a\x1b[31mb") == [span("ab")]


def test_lines_reset_colour_and_are_joined_by_a_newline_span() -> None:
    assert spans("@rone\ntwo") == [span("one", fg=1), span("\n"), span("two")]


def test_text_is_not_html_escaped() -> None:
    assert spans("<b>&") == [span("<b>&")]


def test_ansi_basic_colour() -> None:
    assert ansi_spans("\x1b[31mred\x1b[0m") == [span("red", fg=1)]


def test_ansi_bold_colour() -> None:
    assert ansi_spans("\x1b[1;31mred") == [span("red", fg=9, bold=True)]


def test_ansi_xterm_foreground_and_background() -> None:
    assert ansi_spans("\x1b[38;5;75ma") == [span("a", fg=75)]
    assert ansi_spans("\x1b[48;5;10mb") == [span("b", bg=10)]


def test_ansi_literal_at_and_no_escapes() -> None:
    assert ansi_spans("a@b") == [span("a@b")]
    assert ansi_spans("plain") == [span("plain")]

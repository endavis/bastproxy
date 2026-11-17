"""Display width is measured in terminal columns with wcwidth (#528)."""

import string

import pytest
import wcwidth

from bastproxy.libs.textwidth import display_width, text_units

ZWJ_FAMILY = "👨‍👩‍👧"
CORPUS = [
    "plain",
    "日本語",
    ZWJ_FAMILY,
    "é",
    "❤️",
    "🇺🇸",
    "a​b",
    "́a",
    "ｱｲｳ",
    "a\x07b",
    "a\tb",
    "\x1b",
    "x\x1b[2Jy",
    "a\x1b]8;;http://x\x1b\\link\x1b]8;;\x1b\\",
    "",
]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("hello", 5),
        ("日本語", 6),
        (ZWJ_FAMILY, 2),
        ("é", 1),
        ("❤️", 2),
        ("🇺🇸", 2),
        ("a​b", 2),
    ],
)
def test_display_width(text: str, expected: int) -> None:
    assert display_width(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [("a\x07b", 2), ("a\tb", 2), ("\x1b", 0), ("x\x1b[2Jy", 2)],
)
def test_control_characters_count_zero_and_never_go_negative(text: str, expected: int) -> None:
    assert display_width(text) == expected


def test_ascii_fast_path_matches_wcwidth() -> None:
    samples = [
        string.printable.strip("\t\n\r\x0b\x0c"),
        string.ascii_letters,
        "  spaced  out  ",
        "",
        "@@ literal",
    ]
    for sample in samples:
        assert display_width(sample) == wcwidth.width(sample, control_codes="ignore")


@pytest.mark.parametrize("text", CORPUS)
def test_units_sum_to_display_width_and_join_back(text: str) -> None:
    units = text_units(text)

    assert sum(width for _, width in units) == display_width(text)
    assert "".join(unit for unit, _ in units) == text
    assert all(width >= 0 for _, width in units)


def test_text_units_keeps_graphemes_whole() -> None:
    assert text_units(ZWJ_FAMILY) == [(ZWJ_FAMILY, 2)]
    assert text_units("é") == [("é", 1)]
    assert text_units("日本") == [("日", 2), ("本", 2)]


def test_text_units_ascii() -> None:
    assert text_units("ab") == [("a", 1), ("b", 1)]
    assert text_units("") == []


def test_escape_sequence_is_one_zero_width_unit() -> None:
    assert text_units("x\x1b[2Jy") == [("x", 1), ("\x1b[2J", 0), ("y", 1)]

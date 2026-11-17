"""Tests for fit_column_widths and wrap_cell, the pure helpers of table.format (#421)."""

import pytest

from bastproxy.plugins.core.utils.plugin._utils import fit_column_widths, wrap_cell
from tests.plugins.core.utils.test_utils_output_table import make_utils_stub

_TOKENIZE = make_utils_stub().api("plugins.core.colors:colorcode.to.tokens")


_STRIP = make_utils_stub().api("plugins.core.colors:colorcode.strip")


def strip(text: str) -> str:
    result: str = _STRIP(text)
    return result


def tokenize(text: str) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = _TOKENIZE(text)
    return result


def test_fit_unchanged_when_it_fits() -> None:
    assert fit_column_widths([5, 10], [3, 4], [2, 2], 20) == [5, 10]


def test_fit_shrinks_only_the_column_with_spaces() -> None:
    # column 0 cannot go under its longest word (8); column 1 can go to 3
    assert fit_column_widths([8, 20], [8, 3], [2, 2], 18) == [8, 10]


def test_fit_tie_shrinks_the_rightmost() -> None:
    assert fit_column_widths([10, 10], [1, 1], [1, 1], 19) == [10, 9]


def test_fit_phase_two_splits_words_when_it_can_reach() -> None:
    assert fit_column_widths([10, 10], [10, 10], [2, 2], 12) == [6, 6]


def test_fit_headers_wrap_at_spaces_before_words_split() -> None:
    # headers "aaaa bbbb" (9, longest word 4) cannot fit in 10 together; words stay whole
    assert fit_column_widths([9, 9], [9, 9], [9, 9], 10, [4, 4]) == [5, 5]
    assert fit_column_widths([9, 9], [9, 9], [9, 9], 8, [4, 4]) == [4, 4]


def test_fit_header_words_split_down_to_one_column() -> None:
    assert fit_column_widths([9, 9], [9, 9], [9, 9], 6, [4, 4]) == [3, 3]
    assert fit_column_widths([9, 9], [9, 9], [9, 9], 1, [4, 4]) == [1, 1]


def test_fit_fitting_headers_are_not_touched_by_header_phases() -> None:
    assert fit_column_widths([10, 10], [6, 6], [4, 4], 12, [2, 2]) == [6, 6]


def test_wrap_split_word_breaks_after_punctuation() -> None:
    assert wrap_cell("plugins.core.clients", 13, tokenize) == ["plugins.core.", "clients"]


@pytest.mark.parametrize("char", [".", "/", "_", "-"])
def test_wrap_split_word_prefers_each_punctuation_char(char: str) -> None:
    assert wrap_cell(f"abc{char}defghijkl", 8, tokenize) == [f"abc{char}", "defghijk", "l"]


def test_wrap_split_without_punctuation_is_hard() -> None:
    assert wrap_cell("abcdefghij", 4, tokenize) == ["abcd", "efgh", "ij"]


def test_wrap_fitting_cell_is_unchanged() -> None:
    assert wrap_cell("hello there", 20, tokenize) == ["hello there"]


def test_wrap_at_spaces() -> None:
    assert wrap_cell("aaa bbb ccc", 7, tokenize) == ["aaa bbb", "ccc"]


def test_wrap_hard_splits_a_word_with_no_spaces() -> None:
    assert wrap_cell("abcdefghij", 4, tokenize) == ["abcd", "efgh", "ij"]


def test_wrap_mixes_long_and_short_words() -> None:
    lines = wrap_cell("ab abcdefghijkl cd", 5, tokenize)
    assert lines == ["ab ab", "cdefg", "hijkl", "cd"]


def test_wrap_carries_color_onto_continuation_lines() -> None:
    lines = wrap_cell("@Raaa bbb ccc@w", 7, tokenize)
    assert lines == ["@Raaa bbb", "@Rccc@w"]


def test_wrap_keeps_a_color_change_in_the_middle() -> None:
    lines = wrap_cell("aaa @Rbbb ccc", 3, tokenize)
    assert [strip(line) for line in lines] == ["aaa", "bbb", "ccc"]
    assert lines[1] == "@Rbbb"
    assert lines[2] == "@Rccc"


def test_wrap_at_sign_counts_as_one_character() -> None:
    lines = wrap_cell("@@" * 6, 3, tokenize)
    assert lines == ["@@@@@@", "@@@@@@"]


def test_wrap_empty_cell() -> None:
    assert wrap_cell("", 5, tokenize) == [""]


@pytest.mark.parametrize("width", [1, 2, 3, 5, 8])
def test_wrap_lines_never_exceed_width(width: int) -> None:
    text = "@x075one two@w three-four-five  @Gsix sevenseveneight"
    for line in wrap_cell(text, width, tokenize):
        assert len(strip(line)) <= width

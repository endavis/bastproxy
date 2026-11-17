"""Tables, wrapping and centering measure display columns, not code points (#528)."""

from typing import Any

import pytest

from bastproxy.libs.textwidth import display_width
from bastproxy.plugins.core.utils.plugin._utils import UtilsPlugin, fit_column_widths, wrap_cell
from tests.plugins.core.utils.test_utils_center_colored import _stub as center_stub
from tests.plugins.core.utils.test_utils_output_table import LINELEN, make_utils_stub

_STUB = make_utils_stub()
_TOKENIZE = _STUB.api("plugins.core.colors:colorcode.to.tokens")
_STRIP = _STUB.api("plugins.core.colors:colorcode.strip")
ZWJ = "👨‍👩‍👧"


def _width(line: str) -> int:
    return display_width(_STRIP(line))


def test_cjk_wraps_at_spaces() -> None:
    assert wrap_cell("日本語 テスト", 6, _TOKENIZE) == ["日本語", "テスト"]


def test_cjk_hard_split_never_cuts_a_character() -> None:
    lines = wrap_cell("日本語テスト", 5, _TOKENIZE)

    assert all(_width(line) <= 5 for line in lines)
    assert [_width(line) for line in lines[:-1]] == [4] * (len(lines) - 1)
    assert "".join(lines) == "日本語テスト"


def test_zwj_sequence_is_never_split() -> None:
    lines = wrap_cell(f"{ZWJ} {ZWJ} {ZWJ}ab{ZWJ}", 3, _TOKENIZE)

    assert all(_width(line) <= 3 for line in lines)
    assert all(line.count("‍") % 2 == 0 for line in lines)
    assert "".join(lines).count(ZWJ) == 4


def test_combining_mark_stays_with_its_base() -> None:
    text = "é" * 8
    lines = wrap_cell(text, 3, _TOKENIZE)

    assert all(_width(line) <= 3 for line in lines)
    assert not any(line.startswith("́") for line in lines)
    assert "".join(lines) == text


def test_colour_code_before_cjk_is_carried_to_the_continuation_line() -> None:
    lines = wrap_cell("@R日本語テスト", 4, _TOKENIZE)

    assert lines[0].startswith("@R")
    assert lines[1].startswith("@R")


def test_wide_grapheme_in_a_one_column_width_terminates() -> None:
    lines = wrap_cell("日本語", 1, _TOKENIZE)

    assert lines == ["日", "本", "語"]


@pytest.mark.parametrize("width", [2, 3, 5, 8])
def test_wrapped_lines_fit_and_keep_the_text(width: int) -> None:
    text = "日本語 abc @x075colour éé mail@@host 👨‍👩 テスト.sub-word"
    lines = wrap_cell(text, width, _TOKENIZE)

    assert all(_width(line) <= width for line in lines)
    original = _STRIP(text).replace(" ", "")
    assert "".join(_STRIP(line) for line in lines).replace(" ", "") == original


def test_unit_mins_floor_stops_column_shrinking() -> None:
    assert fit_column_widths([8, 8], [2, 2], [2, 2], 1, unit_mins=[2, 2]) == [2, 2]
    assert fit_column_widths([8, 8], [2, 2], [2, 2], 1) == [1, 1]


def _render(data: list[dict[str, Any]], columns: list[dict[str, Any]]) -> list[str]:
    lines = UtilsPlugin._api_table_format(_STUB, "T", data, columns)
    return [_STRIP(line) for line in lines[1:]]


def test_table_with_wide_cells_keeps_borders_aligned() -> None:
    columns: list[dict[str, Any]] = [{"name": "Name", "key": "n"}, {"name": "Info", "key": "i"}]
    data = [
        {"n": "日本語", "i": "plain"},
        {"n": ZWJ, "i": "éé"},
        {"n": "@R日本@w", "i": "x"},
    ]

    plain = _render(data, columns)

    assert all(display_width(line) == LINELEN for line in plain)
    assert columns[0]["width"] == display_width("日本語")


def test_long_cjk_cell_wraps_inside_its_column() -> None:
    columns: list[dict[str, Any]] = [{"name": "Name", "key": "n"}, {"name": "Info", "key": "i"}]
    data = [{"n": "a", "i": "日本語テスト" * 12}]

    plain = _render(data, columns)

    assert len(plain) > 4
    assert all(display_width(line) == LINELEN for line in plain)
    bars = {
        tuple(display_width(line[:i]) for i, char in enumerate(line) if char == "|")
        for line in plain
        if line.startswith("|")
    }
    assert len(bars) == 1


@pytest.mark.parametrize("endcaps", [False, True])
def test_center_colored_pads_to_display_width(endcaps: bool) -> None:
    out = UtilsPlugin._api_string_center_colored(
        center_stub(), "日本語", "-", length=40, endcaps=endcaps
    )

    assert display_width(out) == 40


def test_line_cap_pads_to_display_width() -> None:
    out = UtilsPlugin._api_line_cap(_STUB, "日本語", line_length=20)

    assert display_width(_STRIP(out)) == 20

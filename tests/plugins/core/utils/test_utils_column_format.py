"""Tests for column.format (#654)."""

import math
from typing import Any

import pytest

from bastproxy.libs.textwidth import display_width
from bastproxy.plugins.core.utils.plugin._utils import UtilsPlugin
from tests.plugins.core.utils.test_utils_output_table import make_utils_stub


def _format(items: list[Any], **kwargs: Any) -> list[str]:
    result: list[str] = UtilsPlugin._api_column_format(make_utils_stub(), items, **kwargs)
    return result


def _legacy(obj: list[Any], cols: int = 4, columnwise: bool = True, gap: int = 4) -> list[str]:
    """The ljust implementation before #654."""
    strings = [str(item) for item in obj]
    number_of_columns = min(cols, len(strings))
    max_len = max(len(item) for item in strings)
    if columnwise:
        number_of_columns = math.ceil(float(len(strings)) / float(number_of_columns))
    plist = [strings[i : i + number_of_columns] for i in range(0, len(strings), number_of_columns)]
    rows: Any = plist
    if columnwise:
        if len(plist[-1]) != number_of_columns:
            plist[-1].extend([""] * (len(strings) - len(plist[-1])))
        rows = zip(*plist, strict=False)
    return ["".join([c.ljust(max_len + gap) for c in p]) for p in rows]


@pytest.mark.parametrize("columnwise", [True, False])
def test_empty_list(columnwise: bool) -> None:
    assert _format([], columnwise=columnwise) == []


@pytest.mark.parametrize("cols", [0, -2])
@pytest.mark.parametrize("columnwise", [True, False])
def test_cols_below_one_equals_one(cols: int, columnwise: bool) -> None:
    items = ["a", "bb", "ccc"]
    assert _format(items, cols=cols, columnwise=columnwise) == _format(
        items, cols=1, columnwise=columnwise
    )


@pytest.mark.parametrize("columnwise", [True, False])
@pytest.mark.parametrize(
    "items", [["a"], list("abcdef"), list("abcdefg"), [str(n * 111) for n in range(1, 11)]]
)
@pytest.mark.parametrize("cols", [1, 3, 4])
@pytest.mark.parametrize("gap", [0, 2, 6])
def test_ascii_matches_legacy(items: list[str], cols: int, columnwise: bool, gap: int) -> None:
    assert _format(items, cols=cols, columnwise=columnwise, gap=gap) == _legacy(
        items, cols=cols, columnwise=columnwise, gap=gap
    )


@pytest.mark.parametrize("items", [["@Rab@w", "cd", "e", "@Gfgh@w"], ["日本語", "ab", "c", "日"]])
def test_columns_align_by_display_width(items: list[str]) -> None:
    strip = make_utils_stub().api("plugins.core.colors:colorcode.strip")
    lines = _format(items, cols=2, columnwise=False, gap=3)
    widest = max(display_width(strip(i)) for i in items)
    for line in lines:
        assert display_width(strip(line)) == 2 * (widest + 3)

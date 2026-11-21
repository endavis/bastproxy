"""Tests for table.format inputs: any iterable, and column dicts left unchanged (#655)."""

import copy
from collections.abc import Iterable
from typing import Any

from bastproxy.plugins.core.utils.plugin._utils import UtilsPlugin
from tests.plugins.core.utils.test_utils_output_table import _column_widths, make_utils_stub


def _columns() -> list[dict[str, Any]]:
    return [{"name": "Name", "key": "n"}, {"name": "Vers", "key": "v"}]


def _data() -> list[dict[str, Any]]:
    return [{"n": "alpha", "v": "1"}, {"n": "beta", "v": "2"}]


def _render(data: Iterable[Any], columns: list[dict[str, Any]]) -> list[str]:
    result: list[str] = UtilsPlugin._api_table_format(make_utils_stub(), "T", data, columns)
    return result


def test_generator_iter_and_tuple_match_list() -> None:
    expected = _render(_data(), _columns())
    assert _render((row for row in _data()), _columns()) == expected
    assert _render(iter(_data()), _columns()) == expected
    assert _render(tuple(_data()), _columns()) == expected


def test_generator_data_is_not_lost() -> None:
    lines = _render((row for row in _data()), _columns())
    assert any("alpha" in line for line in lines)
    assert any("beta" in line for line in lines)


def test_empty_columns_give_nothing() -> None:
    assert _render(_data(), []) == []
    assert _render([], []) == []


def test_column_dicts_are_unchanged() -> None:
    columns = _columns()
    before = copy.deepcopy(columns)
    _render(_data(), columns)
    assert columns == before


def test_caller_supplied_width_is_ignored_and_kept() -> None:
    columns = [{**column, "width": 40} for column in _columns()]
    before = copy.deepcopy(columns)
    result = _render(_data(), columns)
    assert columns == before
    assert result == _render(_data(), _columns())


def test_column_widths_helper() -> None:
    assert _column_widths("| Name  | Vers          |") == [5, 4]

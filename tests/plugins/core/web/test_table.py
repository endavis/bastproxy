"""Table columns and the table query parser (#424)."""

from typing import Any

import pytest

from bastproxy.plugins.core.web.libs._http import HttpError
from bastproxy.plugins.core.web.libs._store import RouteTable
from bastproxy.plugins.core.web.libs._table import (
    Column,
    TableQuery,
    make_columns,
    parse_table_query,
)

COLUMNS = (
    Column("name", "Name", "text"),
    Column("level", "Level", "int"),
    Column("ratio", "Ratio", "float"),
)


def noop(request: Any) -> dict[str, Any]:
    return {"kind": "json", "data": 1}


def test_defaults() -> None:
    query = parse_table_query({}, COLUMNS)
    assert query == TableQuery(None, False, {}, 1, 50)
    assert query.offset == 0


def test_sort_filters_and_paging_are_typed() -> None:
    query = parse_table_query(
        {"sort": "level", "dir": "desc", "f_name": "ab", "f_level": "7", "f_ratio": "1.5",
         "page": "3", "count": "20", "other": "kept"},
        COLUMNS,
    )  # fmt: skip
    assert query.sort == "level"
    assert query.descending
    assert query.filters == {"name": "ab", "level": 7, "ratio": 1.5}
    assert isinstance(query.filters["level"], int)
    assert (query.page, query.count, query.offset) == (3, 20, 40)


def test_blank_form_values_mean_not_given() -> None:
    query = parse_table_query(
        {"sort": "", "dir": "", "f_name": "", "page": "", "count": ""}, COLUMNS
    )
    assert query == TableQuery()


@pytest.mark.parametrize(
    "query",
    [
        {"sort": "nope"},
        {"sort": "name; DROP TABLE x"},
        {"f_nope": "x"},
        {"f_": "x"},
        {"dir": "up"},
        {"page": "0"},
        {"page": "-1"},
        {"page": "x"},
        {"page": "1.5"},
        {"page": "99999999999999999999"},
        {"count": "0"},
        {"count": "501"},
        {"count": "9999"},
        {"count": "x"},
        {"f_level": "abc"},
        {"f_level": "1.5"},
        {"f_level": str(2**63)},
        {"f_ratio": "abc"},
        {"f_ratio": "nan"},
        {"f_ratio": "inf"},
        {"f_name": "x" * 201},
    ],
)
def test_bad_values_are_400(query: dict[str, str]) -> None:
    with pytest.raises(HttpError) as info:
        parse_table_query(query, COLUMNS)
    assert info.value.status == 400


def test_limits_are_accepted() -> None:
    query = parse_table_query({"count": "500", "f_name": "x" * 200}, COLUMNS)
    assert query.count == 500
    assert len(str(query.filters["name"])) == 200


def test_make_columns_validates() -> None:
    columns = make_columns(
        [{"name": "a_1", "label": "A", "type": "int"}, {"name": "b", "label": "B"}]
    )
    assert [c.type for c in columns] == ["int", "text"]


@pytest.mark.parametrize(
    "columns",
    [
        [],
        [{"name": "A", "label": "A", "type": "text"}],
        [{"name": "a-b", "label": "A", "type": "text"}],
        [{"name": "", "label": "A", "type": "text"}],
        [{"label": "A", "type": "text"}],
        [{"name": "a", "label": "A", "type": "blob"}],
        [{"name": "a", "type": "text"}],
        [{"name": "a", "label": "A", "type": "text"}, {"name": "a", "label": "B", "type": "int"}],
    ],
)
def test_bad_columns_are_refused_when_the_route_is_added(columns: list[dict[str, str]]) -> None:
    table = RouteTable()
    with pytest.raises(ValueError):
        table.add("plugins.test.web", "t", noop, "T", columns)
    assert table.count() == 0


def test_columns_are_stored_on_the_route() -> None:
    table = RouteTable()
    table.add("plugins.test.web", "t", noop, "T", [{"name": "a", "label": "A", "type": "int"}])
    route = table.match("/test/web/t")
    assert route is not None
    assert route.columns == (Column("a", "A", "int"),)
    table.add("plugins.test.web", "plain", noop, "P")
    plain = table.match("/test/web/plain")
    assert plain is not None
    assert plain.columns is None

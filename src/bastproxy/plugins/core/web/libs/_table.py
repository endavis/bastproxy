# Project: bastproxy
# Filename: plugins/core/web/libs/_table.py
#
# File Description: table column declarations and the table query parser
#
# By: Bast
"""Columns a table route declares, and the validated query a handler receives."""

# Standard Library
import math
import re
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Any

from ._http import HttpError

CANRELOAD = False

COLUMN_TYPES = ("text", "int", "float")
COLUMN_NAME_RE = re.compile(r"^[a-z0-9_]+$")
DEFAULT_COUNT = 50
MAX_COUNT = 500
MAX_PAGE = 10_000_000
MAX_TEXT_FILTER = 200
INT64_LIMIT = 2**63
FILTER_PREFIX = "f_"
TABLE_KEYS = frozenset({"sort", "dir", "page", "count"})


@dataclass(frozen=True)
class Column:
    """One declared column: ``name`` selects it, ``label`` is the header text."""

    name: str
    label: str
    type: str = "text"


@dataclass(frozen=True)
class TableQuery:
    """The validated sort, filters and page of a table request."""

    sort: str | None = None
    descending: bool = False
    filters: dict[str, str | int | float] = field(default_factory=dict)
    page: int = 1
    count: int = DEFAULT_COUNT

    @property
    def offset(self) -> int:
        """The number of rows before the first row of this page."""
        return (self.page - 1) * self.count


def make_columns(columns: Sequence[Mapping[str, Any]]) -> tuple[Column, ...]:
    """Validate column declarations (dicts with name, label and type) into ``Column`` objects.

    Raises:
        ValueError: A declaration is malformed, a name is repeated or not ``[a-z0-9_]+``,
            or a type is not text, int or float.

    """
    result: list[Column] = []
    seen: set[str] = set()
    for item in columns:
        name = item.get("name")
        label = item.get("label")
        kind = item.get("type", "text")
        if not isinstance(name, str) or not COLUMN_NAME_RE.fullmatch(name):
            msg = f"invalid column name {name!r}: use lower case letters, digits and _"
            raise ValueError(msg)
        if name in seen:
            msg = f"duplicate column name {name!r}"
            raise ValueError(msg)
        if not isinstance(label, str):
            msg = f"column {name!r} needs a text label"
            raise ValueError(msg)
        if kind not in COLUMN_TYPES:
            msg = f"column {name!r} has unknown type {kind!r}: use one of {COLUMN_TYPES}"
            raise ValueError(msg)
        seen.add(name)
        result.append(Column(name, label, kind))
    if not result:
        msg = "a table needs at least one column"
        raise ValueError(msg)
    return tuple(result)


def _bad_request() -> HttpError:
    return HttpError(HTTPStatus.BAD_REQUEST)


def _parse_int(value: str, low: int, high: int) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise _bad_request() from exc
    if not low <= number <= high:
        raise _bad_request()
    return number


def _parse_filter(column: Column, value: str) -> str | int | float:
    if column.type == "int":
        return _parse_int(value, -INT64_LIMIT, INT64_LIMIT - 1)
    if column.type == "float":
        try:
            number = float(value)
        except ValueError as exc:
            raise _bad_request() from exc
        if not math.isfinite(number):
            raise _bad_request()
        return number
    if len(value) > MAX_TEXT_FILTER:
        raise _bad_request()
    return value


def parse_table_query(query: Mapping[str, str], columns: Sequence[Column]) -> TableQuery:
    """Validate the table keys of a query against the declared columns.

    The keys are ``sort``, ``dir`` (asc or desc), ``page`` (1 or more), ``count`` (1 to 500,
    default 50) and ``f_<column>``. An empty value means the key was not given, as a GET
    form sends every box. Other keys are ignored here and stay in ``Request.query``.

    Raises:
        HttpError: 400 for an unknown column, a bad dir, page, count or filter value.

    """
    by_name = {column.name: column for column in columns}
    sort = query.get("sort") or None
    if sort is not None and sort not in by_name:
        raise _bad_request()
    direction = query.get("dir") or "asc"
    if direction not in ("asc", "desc"):
        raise _bad_request()
    page = _parse_int(query["page"], 1, MAX_PAGE) if query.get("page") else 1
    count = _parse_int(query["count"], 1, MAX_COUNT) if query.get("count") else DEFAULT_COUNT
    filters: dict[str, str | int | float] = {}
    for key, value in query.items():
        if not key.startswith(FILTER_PREFIX):
            continue
        name = key[len(FILTER_PREFIX) :]
        if name not in by_name:
            raise _bad_request()
        if value:
            filters[name] = _parse_filter(by_name[name], value)
    return TableQuery(sort, direction == "desc", filters, page, count)


def _cell_text(cell: Any) -> str:
    if isinstance(cell, Mapping):
        return str(cell["text"])
    return "" if cell is None else str(cell)


def _number(cell: Any) -> float | None:
    try:
        number = float(_cell_text(cell))
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def page_rows(
    rows: Sequence[Sequence[Any]], columns: Sequence[Column], query: TableQuery
) -> tuple[list[Sequence[Any]], int]:
    """Filter, sort and page ``rows`` the way a table request asks.

    A text filter matches a case-insensitive part of the cell text (the text of a link cell),
    an int or float filter matches an equal number. A text sort ignores case, a number sort
    puts cells without a number last. Returns the page and the number of rows that matched.
    """
    index = {column.name: i for i, column in enumerate(columns)}
    kinds = {column.name: column.type for column in columns}
    kept: list[Sequence[Any]] = []
    for row in rows:
        for name, wanted in query.filters.items():
            if name not in index:
                continue
            cell = row[index[name]]
            if kinds[name] == "text":
                if str(wanted).casefold() not in _cell_text(cell).casefold():
                    break
            elif _number(cell) != float(wanted):
                break
        else:
            kept.append(row)
    if query.sort is not None and query.sort in index:
        position = index[query.sort]
        if kinds[query.sort] == "text":
            kept.sort(key=lambda r: _cell_text(r[position]).casefold(), reverse=query.descending)
        else:
            numbered = [r for r in kept if _number(r[position]) is not None]
            blank = [r for r in kept if _number(r[position]) is None]
            numbered.sort(key=lambda r: _number(r[position]) or 0.0, reverse=query.descending)
            kept = numbered + blank
    return kept[query.offset : query.offset + query.count], len(kept)


def escape_cells(
    rows: Sequence[Sequence[Any]],
    escape: Callable[[str], str],
    *,
    raw: Collection[int] = (),
) -> list[list[Any]]:
    """Return the rows with the text of every cell colour-code escaped.

    The web plugin converts cell text with the colour converter, so provider text must be
    escaped first. Numbers and ``None`` pass through; a link cell keeps its href. The cells at
    the column indexes in ``raw`` keep their text unescaped, so colour codes in it are converted.
    """
    result: list[list[Any]] = []
    for row in rows:
        cells: list[Any] = []
        for position, cell in enumerate(row):
            keep = position in raw
            if isinstance(cell, Mapping):
                text = str(cell["text"])
                cells.append({"text": text if keep else escape(text), "href": cell["href"]})
            elif isinstance(cell, str):
                cells.append(cell if keep else escape(cell))
            else:
                cells.append(cell)
        result.append(cells)
    return result

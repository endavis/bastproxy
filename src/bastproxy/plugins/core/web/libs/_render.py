# Project: bastproxy
# Filename: plugins/core/web/libs/_render.py
#
# File Description: html builders for the web plugin
#
# By: Bast
"""Build html documents. The colour conversion is injected (the colors API)."""

# Standard Library
import html
import math
from collections.abc import Callable, Mapping, Sequence
from typing import Any
from urllib.parse import urlencode

from ._table import Column, TableQuery

CANRELOAD = False

_STYLE = (
    "body{background:#000;color:#ccc;font-family:monospace;margin:1em}"
    "h1{font-size:1.2em}pre{white-space:pre-wrap;word-break:break-word}"
)
_TABLE_STYLE = (
    "table{border-collapse:collapse}th,td{border:1px solid #444;padding:2px 8px;text-align:left}"
    "th a{color:#6cf;text-decoration:none}form{margin:1em 0}input{background:#111;color:#ccc;"
    "border:1px solid #444;font-family:monospace}a{color:#6cf}"
)
TABLE_SCRIPT_TAG = '<script src="/static/table.js" defer></script>'


def render_page(title: str, lines: list[str] | str, to_html: Callable[[str], str]) -> str:
    """Build a page: the escaped title and the colour-converted lines in a pre element."""
    text = lines if isinstance(lines, str) else "\n".join(lines)
    safe_title = html.escape(title)
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{safe_title}</title><style>{_STYLE}</style></head>"
        f"<body><h1>{safe_title}</h1><pre>{to_html(text)}</pre></body></html>"
    )


def render_index(routes_by_owner: Mapping[str, Sequence[Any]]) -> str:
    """Build the index of listed routes by owner; each has ``path``, ``title`` and ``listed``."""
    parts = []
    for owner in sorted(routes_by_owner):
        listed = [route for route in routes_by_owner[owner] if route.listed]
        if not listed:
            continue
        items = "".join(
            f"<li><a href='{html.escape(route.path, quote=True)}'>"
            f"{html.escape(route.title)}</a></li>"
            for route in listed
        )
        parts.append(f"<h2>{html.escape(owner)}</h2><ul>{items}</ul>")
    body = "".join(parts) or "<p>No pages are registered.</p>"
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>bastproxy</title><style>{_STYLE}a{{color:#6cf}}</style></head>"
        f"<body><h1>bastproxy</h1>{body}</body></html>"
    )


def _link(base_path: str, query: TableQuery, extra: Mapping[str, str], **changes: Any) -> str:
    """An escaped url for the table at ``base_path`` with the query's state plus changes."""
    params: dict[str, str] = dict(extra)
    if query.sort is not None:
        params["sort"] = query.sort
        params["dir"] = "desc" if query.descending else "asc"
    params["count"] = str(query.count)
    for name, value in query.filters.items():
        params[f"f_{name}"] = str(value)
    params.update({key: str(value) for key, value in changes.items()})
    return html.escape(f"{base_path}?{urlencode(params)}", quote=True)


def _safe_href(href: Any) -> str:
    """Return ``href`` when it is a same-origin absolute path, else raise.

    Raises:
        ValueError: The href is not a string, does not start with ``/``, starts with ``//``,
            or has a backslash, whitespace or a control character.

    """
    if not isinstance(href, str) or not href.startswith("/") or href.startswith("//"):
        msg = f"a link must be a same-origin absolute path, got {href!r}"
        raise ValueError(msg)
    if any(char == "\\" or char.isspace() or not char.isprintable() for char in href):
        msg = f"a link must not have a backslash, whitespace or control character: {href!r}"
        raise ValueError(msg)
    return href


def _cell_html(cell: Any, to_html: Callable[[str], str]) -> str:
    """Build the inner html of one cell: text, or a link for a ``{"text", "href"}`` dict.

    Raises:
        ValueError: A dict cell has no ``text`` and ``href`` or its href is not allowed.

    """
    if isinstance(cell, Mapping):
        if set(cell) != {"text", "href"} or not isinstance(cell["text"], str):
            msg = f"a link cell needs exactly a text string and an href, got {sorted(cell)}"
            raise ValueError(msg)
        href = html.escape(_safe_href(cell["href"]), quote=True)
        return f"<a href='{href}'>{to_html(cell['text'])}</a>"
    return to_html("" if cell is None else str(cell))


def render_table(
    columns: Sequence[Column],
    rows: Sequence[Sequence[Any]],
    *,
    query: TableQuery,
    total: int,
    base_path: str,
    to_html: Callable[[str], str],
    extra: Mapping[str, str] | None = None,
) -> str:
    """Build the filter form, the table and the paging links (an html fragment).

    ``extra`` holds the query keys that are not table keys; every link and the form keep them.

    Raises:
        ValueError: A row does not have one cell per column, or a link cell is malformed or
            its href is not a same-origin absolute path (see ``_safe_href``).

    """
    keep = extra or {}
    pages = max(1, math.ceil(total / query.count))
    safe_path = html.escape(base_path, quote=True)
    form = [f"<form method='get' action='{safe_path}'>"]
    for key, value in keep.items():
        form.append(
            f"<input type='hidden' name='{html.escape(key, quote=True)}' "
            f"value='{html.escape(value, quote=True)}'>"
        )
    if query.sort is not None:
        form.append(f"<input type='hidden' name='sort' value='{html.escape(query.sort)}'>")
        direction = "desc" if query.descending else "asc"
        form.append(f"<input type='hidden' name='dir' value='{direction}'>")
    form.append(f"<input type='hidden' name='count' value='{query.count}'>")
    for column in columns:
        value = html.escape(str(query.filters.get(column.name, "")), quote=True)
        form.append(
            f"<label>{html.escape(column.label)} "
            f"<input type='text' name='f_{column.name}' value='{value}'></label> "
        )
    form.append("<button type='submit'>Filter</button></form>")
    heads = []
    for column in columns:
        toggled = "desc" if query.sort == column.name and not query.descending else "asc"
        href = _link(base_path, query, keep, sort=column.name, dir=toggled, page=1)
        heads.append(
            f"<th data-type='{column.type}'><a href='{href}'>{html.escape(column.label)}</a></th>"
        )
    body = []
    for row in rows:
        if len(row) != len(columns):
            msg = f"a row has {len(row)} cells for {len(columns)} columns"
            raise ValueError(msg)
        cells = "".join(f"<td>{_cell_html(cell, to_html)}</td>" for cell in row)
        body.append(f"<tr>{cells}</tr>")
    nav = [f"<p>Page {query.page} of {pages}, {total} rows. "]
    if query.page > 1:
        nav.append(f"<a href='{_link(base_path, query, keep, page=query.page - 1)}'>previous</a> ")
    if query.page < pages:
        nav.append(f"<a href='{_link(base_path, query, keep, page=query.page + 1)}'>next</a>")
    nav.append("</p>")
    return (
        "".join(form)
        + f"<table data-pages='{pages}'><thead><tr>{''.join(heads)}</tr></thead>"
        + f"<tbody>{''.join(body)}</tbody></table>"
        + "".join(nav)
    )


def render_table_page(
    title: str,
    lines: list[str] | str,
    table: str,
    to_html: Callable[[str], str],
) -> str:
    """Build a page around a rendered table; it is the only page that loads the script."""
    text = lines if isinstance(lines, str) else "\n".join(lines)
    safe_title = html.escape(title)
    intro = f"<pre>{to_html(text)}</pre>" if text else ""
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{safe_title}</title><style>{_STYLE}{_TABLE_STYLE}</style>"
        f"{TABLE_SCRIPT_TAG}</head>"
        f"<body><h1>{safe_title}</h1>{intro}{table}</body></html>"
    )

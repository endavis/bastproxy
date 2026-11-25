# Project: bastproxy
# Filename: plugins/core/web/libs/_render.py
#
# File Description: html builders for the web plugin
#
# By: Bast
"""Build html documents. The colour conversion is injected (the colors API)."""

# Standard Library
import html
from collections.abc import Callable

CANRELOAD = False

_STYLE = (
    "body{background:#000;color:#ccc;font-family:monospace;margin:1em}"
    "h1{font-size:1.2em}pre{white-space:pre-wrap;word-break:break-word}"
)


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

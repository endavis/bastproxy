# Project: bastproxy
# Filename: plugins/core/web/libs/_client.py
#
# File Description: read one file of the web client bundle
#
# By: Bast
"""Resolve a request path to a file of the configured web client directory."""

# Standard Library
import re
from pathlib import Path

from bastproxy.libs.logger import get_logger

from ._tls import LOGGER_NAME

CANRELOAD = False

CLIENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".woff2": "font/woff2",
}
MAX_CLIENT_FILE = 8 * 1024 * 1024
SEGMENT_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]*$")
INDEX_FILE = "index.html"


def _content_type(name: str) -> str | None:
    return CLIENT_TYPES.get(Path(name).suffix.lower())


def read_client_file(base: Path, rest: str) -> tuple[bytes, str] | None:
    """Return the bytes and content type of ``rest`` under ``base``, or None to refuse.

    ``rest`` is the already decoded request path after the prefix; empty means the index.
    Every segment must be a plain name, the suffix must be an allowed type, and the resolved
    file must stay inside ``base`` (a symlink that leaves it is refused).
    """
    rel = rest or INDEX_FILE
    segments = rel.split("/")
    if not all(SEGMENT_RE.fullmatch(segment) for segment in segments):
        return None
    if _content_type(rel) is None:
        return None
    try:
        root = base.resolve(strict=True)
        if not root.is_dir():
            return None
        target = root.joinpath(*segments).resolve(strict=True)
        content_type = _content_type(target.name)
        if content_type is None or not target.is_relative_to(root) or not target.is_file():
            return None
        with target.open("rb") as handle:
            data = handle.read(MAX_CLIENT_FILE + 1)
    except (OSError, ValueError):
        return None
    if len(data) > MAX_CLIENT_FILE:
        get_logger(LOGGER_NAME).warning("web client file %s is larger than the limit", rel)
        return None
    return data, content_type

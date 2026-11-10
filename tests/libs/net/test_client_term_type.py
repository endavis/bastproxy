"""Tests for ClientConnection.term_type (#307)."""

from unittest.mock import MagicMock

import pytest

from bastproxy.libs.net.client import ClientConnection


def _client(term: object) -> ClientConnection:
    conn = object.__new__(ClientConnection)
    writer = MagicMock()
    writer.get_extra_info = lambda key: term if key == "TERM" else "unknown"
    conn.writer = writer
    return conn


@pytest.mark.parametrize(
    ("term", "expected"),
    [
        ("xterm", "xterm"),
        (None, "-"),
        ("", "-"),
        ("xterm-256color", "xterm-256color"),
        ("xterm\x1b[31m", "xterm31m"),
        ("@Rxterm@@", "Rxterm"),
        ("x" * 100, "x" * 32),
        ("\x1b\x07 @@", "-"),
    ],
)
def test_term_type(term: object, expected: str) -> None:
    assert _client(term).term_type == expected


def test_term_type_has_no_escape_or_marker() -> None:
    result = _client("a\x1b[31m@Rb").term_type
    assert "\x1b" not in result
    assert "@" not in result

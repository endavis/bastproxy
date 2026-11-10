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


@pytest.mark.parametrize(("term", "expected"), [("xterm", "xterm"), (None, "-"), ("", "-")])
def test_term_type(term: object, expected: str) -> None:
    assert _client(term).term_type == expected

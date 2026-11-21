"""Tests for string.dedent (#653)."""

from unittest.mock import MagicMock

from bastproxy.plugins.core.utils.plugin._utils import UtilsPlugin


def _dedent(lines: list[str]) -> list[str]:
    result: list[str] = UtilsPlugin._api_string_dedent(MagicMock(), lines)
    return result


def test_common_indentation_removed() -> None:
    assert _dedent(["    a", "  b", "      c"]) == ["  a", "b", "    c"]


def test_uniform_indentation_stripped() -> None:
    assert _dedent(["  a", "  b"]) == ["a", "b"]


def test_unindented_line_removes_nothing() -> None:
    assert _dedent(["a", "  b"]) == ["a", "  b"]


def test_blank_lines_ignored_for_common_and_emptied() -> None:
    assert _dedent(["    a", "  ", "", "    b"]) == ["a", "", "", "b"]


def test_empty_list() -> None:
    assert _dedent([]) == []


def test_all_blank() -> None:
    assert _dedent(["  ", ""]) == ["", ""]


def test_input_not_modified() -> None:
    lines = ["    a", "  b"]
    result = _dedent(lines)
    assert lines == ["    a", "  b"]
    assert result is not lines

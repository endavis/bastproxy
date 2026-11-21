"""Tests for string.match.in.list (#656)."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.plugins.core.utils.plugin._utils import UtilsPlugin


def _match(arg: Any, items: list[Any]) -> list[str]:
    result: list[str] = UtilsPlugin._api_string_match_in_list(MagicMock(), arg, items)
    return result


@pytest.mark.parametrize(
    ("arg", "items", "expected"),
    [
        ("*", ["abc", "def"], []),
        ("*", ["a*b", "x"], ["a*b"]),
        ("?", ["abc", "x"], []),
        ("?", ["a?b", "x"], ["a?b"]),
        ("[a]", ["a", "b"], []),
        ("[a]", ["x[a]y"], ["x[a]y"]),
    ],
)
def test_wildcards_are_literal(arg: str, items: list[Any], expected: list[str]) -> None:
    assert _match(arg, items) == expected


def test_non_str_items_are_skipped() -> None:
    assert _match("a", ["abc", 5, None]) == ["abc"]


def test_exact_match_wins() -> None:
    assert _match("ab", ["ab", "abc"]) == ["ab"]


def test_prefix_wins_over_substring() -> None:
    assert _match("ab", ["xab", "abc"]) == ["abc"]


def test_substring_only() -> None:
    assert _match("b", ["abc", "xbz"]) == ["abc", "xbz"]


def test_no_match() -> None:
    assert _match("q", ["abc", "xbz"]) == []


def test_non_str_arg_goes_through_str() -> None:
    assert _match(12, ["a12", "b"]) == ["a12"]
    assert _match(12, ["123", "a12"]) == ["123"]

"""Tests for the miltime value type and string.center.colored filler fitting (#658)."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs.textwidth import display_width
from bastproxy.plugins.core.utils.plugin import _utils
from bastproxy.plugins.core.utils.plugin._utils import UtilsPlugin
from tests.plugins.core.utils.test_utils_center_colored import _stub as _center_stub


def _verify_miltime(value: Any) -> Any:
    return UtilsPlugin.verify_miltime(MagicMock(), value)


@pytest.mark.parametrize("value", ["0000", "0830", "2359"])
def test_miltime_accepts(value: str) -> None:
    assert _verify_miltime(value) == value


@pytest.mark.parametrize(
    "value",
    ["830", "08300", "2400", "0860", " 0830", "08:30", "", "abcd", "٠٨٣٠", 830],
)
def test_miltime_rejects(value: Any) -> None:
    with pytest.raises(ValueError):
        _verify_miltime(value)


def _center(text: str, filler: str, **kwargs: Any) -> str:
    result: str = UtilsPlugin._api_string_center_colored(_center_stub(), text, filler, **kwargs)
    return result


@pytest.mark.parametrize("length", [20, 21, 30, 7])
def test_multi_char_filler_fills_exactly(length: int) -> None:
    out = _center("hi", "-=", length=length)
    assert display_width(out) == max(length, 6)


def test_multi_char_filler_with_endcaps_fills_exactly() -> None:
    assert display_width(_center("hi", "-=", length=30, endcaps=True)) == 30


def test_single_char_filler_unchanged() -> None:
    assert _center("hi", "-", length=12) == "---  hi  ---"
    assert _center("hi", "-", length=13) == "---  hi  ----"


def test_single_char_filler_with_color_unchanged() -> None:
    assert _center("hi", "-", length=12, filler_color="@R") == "@R---@w  hi  @R---@w"
    assert _center("hi", "-", length=13, filler_color="@R") == "@R---@w  hi  @R----@w"


@pytest.mark.parametrize(
    ("filler", "width", "expected"),
    [("-=", 5, "-=-=-"), ("", 5, ""), ("-", 0, ""), ("日", 3, "日 ")],
)
def test_fill_to_width(filler: str, width: int, expected: str) -> None:
    assert _utils._fill_to_width(filler, width) == expected

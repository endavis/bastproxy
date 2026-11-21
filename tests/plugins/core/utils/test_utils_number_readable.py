"""Tests for number.to.readable (#657)."""

from unittest.mock import MagicMock

import pytest

from bastproxy.plugins.core.utils.plugin._utils import UtilsPlugin


def _readable(num: float, places: int = 2) -> str:
    result: str = UtilsPlugin._api_number_to_readable(MagicMock(), num, places)
    return result


@pytest.mark.parametrize("value", [0, 0.0, 5, 999.5, 1000, -5, 1e15])
def test_result_is_str(value: float) -> None:
    assert isinstance(_readable(value), str)


@pytest.mark.parametrize(("value", "expected"), [(0, "0"), (5, "5"), (999.5, "999.5"), (-5, "-5")])
def test_under_a_thousand(value: float, expected: str) -> None:
    assert _readable(value) == expected


@pytest.mark.parametrize(
    ("value", "places", "expected"),
    [
        (1000, 2, "1.00 K"),
        (1500000, 2, "1.50 M"),
        (2e9, 2, "2.00 B"),
        (3e12, 2, "3.00 T"),
        (1500, 0, "2 K"),
        (1500, 1, "1.5 K"),
        (-5000, 2, "-5.00 K"),
        (-999999, 2, "-1.00 M"),
    ],
)
def test_scaled(value: float, places: int, expected: str) -> None:
    assert _readable(value, places) == expected


@pytest.mark.parametrize(
    ("value", "places", "expected"),
    [
        (999999, 2, "1.00 M"),
        (999999999, 2, "1.00 B"),
        (999500, 0, "1 M"),
        (1e15, 2, "1000.00 T"),
    ],
)
def test_carry_to_next_unit(value: float, places: int, expected: str) -> None:
    assert _readable(value, places) == expected

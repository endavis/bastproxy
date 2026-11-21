"""Tests for seconds.to.dhms, timelength.format and timedelta.to.string (#652)."""

import datetime
from unittest.mock import MagicMock

import pytest

from bastproxy.plugins.core.utils.plugin._utils import UtilsPlugin


def _stub() -> MagicMock:
    stub = MagicMock()
    stub.plugin_id = "plugins.core.utils"
    stub.api = lambda name: lambda v: UtilsPlugin._api_seconds_to_dhms(stub, v)
    return stub


def _dhms(seconds: float) -> dict[str, int]:
    result: dict[str, int] = UtilsPlugin._api_seconds_to_dhms(_stub(), seconds)
    return result


def _fmt(length: float, nosec: bool = False) -> str:
    result: str = UtilsPlugin._api_timelength_format(_stub(), length, nosec)
    return result


def _delta(start: object, end: object, nosec: bool = False) -> str:
    result: str = UtilsPlugin._api_timedelta_to_string(_stub(), start, end, nosec=nosec)
    return result


def test_dhms_negative_small() -> None:
    assert _dhms(-5) == {"years": 0, "days": 0, "hours": 0, "mins": 0, "secs": -5}


def test_dhms_negative_parts() -> None:
    parts = _dhms(-3700)
    assert (parts["hours"], parts["mins"], parts["secs"]) == (-1, -1, -40)


@pytest.mark.parametrize(
    "value", [-40000000, -86401, -3700, -60, -1, 0, 1, 59, 3700, 93784, 40000000]
)
def test_dhms_parts_add_up(value: int) -> None:
    p = _dhms(value)
    total = (
        p["years"] * 365 * 86400
        + p["days"] * 86400
        + p["hours"] * 3600
        + p["mins"] * 60
        + p["secs"]
    )
    assert total == value


def test_dhms_positive_unchanged() -> None:
    assert _dhms(93784) == {"years": 0, "days": 1, "hours": 2, "mins": 3, "secs": 4}
    assert _dhms(0) == {"years": 0, "days": 0, "hours": 0, "mins": 0, "secs": 0}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (-5, "-05s"),
        (-3700, "-01h:01m:40s"),
        (0, "00s"),
        (5, "05s"),
        (3700, "01h:01m:40s"),
        (93784, "01d:02h:03m:04s"),
        (365 * 86400 + 1, "1y:01s"),
    ],
)
def test_format(value: int, expected: str) -> None:
    assert _fmt(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"), [(30, "00m"), (0, "00m"), (90, "01m"), (-30, "-00m")]
)
def test_format_nosec(value: int, expected: str) -> None:
    assert _fmt(value, nosec=True) == expected


def test_timedelta_nosec_under_a_minute() -> None:
    assert _delta(0, 30, nosec=True) == "00m"


def test_timedelta_pinned_outputs() -> None:
    assert _delta(0, 30) == "30s"
    assert _delta(0, 3700) == "01h:01m:40s"
    assert _delta(3700, 0) == "01h:01m:40s"
    start = datetime.datetime(2024, 1, 1, 0, 0, 0)
    assert _delta(start, start + datetime.timedelta(seconds=3700)) == "01h:01m:40s"

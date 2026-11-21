"""Tests for parse_timelength and the timelength value type (#651)."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.plugins.core.utils.plugin._utils import UtilsPlugin, parse_timelength


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1d", 86400),
        ("1h", 3600),
        ("30m", 1800),
        ("5s", 5),
        ("2h30m", 9000),
        ("1d2h3m4s", 93784),
        ("1d:2h:3m:4s", 93784),
        ("1h:30s", 3630),
        ("1h:", 3600),
        ("  1h30m  ", 5400),
        ("1.5h", 5400),
        (".5d", 43200),
        ("0.5s", 1),
        ("1.4s", 1),
        ("0.25m", 15),
    ],
)
def test_parse_timelength_accepts(text: str, expected: int) -> None:
    assert parse_timelength(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "-5m",
        "5",
        "abc",
        "5x",
        "1h1h",
        "30m1h",
        "1h::2m",
        ":1h",
        ":",
        "1.",
        "1h junk",
        "9" * 400 + "d",
        None,
        5,
    ],
)
def test_parse_timelength_rejects(text: Any) -> None:
    assert parse_timelength(text) is None


def _stub() -> MagicMock:
    stub = MagicMock()
    stub.plugin_id = "plugins.core.utils"
    stub.verify_timelength = lambda v: UtilsPlugin.verify_timelength(stub, v)
    stub.api = lambda name: lambda v: UtilsPlugin._api_timelength_to_seconds(stub, v)
    return stub


def _verify(value: Any) -> Any:
    return UtilsPlugin._api_value_verify(_stub(), value, "timelength")


@pytest.mark.parametrize(
    ("value", "expected"),
    [("30", 30), ("0", 0), ("30s", 30), ("1.5h", 5400), ("2h30m", 9000)],
)
def test_value_verify_timelength_accepts(value: str, expected: int) -> None:
    assert _verify(value) == expected


@pytest.mark.parametrize("value", ["-5", "-5m", "", "garbage"])
def test_value_verify_timelength_rejects(value: str) -> None:
    with pytest.raises(ValueError):
        _verify(value)

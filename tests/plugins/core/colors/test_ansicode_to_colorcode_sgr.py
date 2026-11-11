"""Unmapped SGR codes are dropped without an ERROR log (#335)."""

import logging
from unittest.mock import MagicMock

import pytest

from bastproxy.plugins.core.colors.plugin._colors import ColorsPlugin


def _convert(text: str) -> str:
    result = ColorsPlugin._api_ansicode_to_colorcode(MagicMock(), text)
    assert isinstance(result, str)
    return result


@pytest.mark.parametrize(
    ("text", "expected"),
    [("\x1b[22m\x1b[32mtext", "@gtext"), ("\x1b[1m\x1b[31mx", "@rx")],
)
def test_unmapped_sgr_code_is_dropped_without_error(
    caplog: pytest.LogCaptureFixture, text: str, expected: str
) -> None:
    with caplog.at_level(logging.DEBUG):
        assert _convert(text) == expected
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_mapped_code_still_converts() -> None:
    assert _convert("\x1b[0;31m") == "@r"

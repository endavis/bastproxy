"""The match debug log only builds ``colorcoded`` when DEBUG is enabled (#335)."""

import logging
from typing import Any

import pytest

from .conftest import Harness


class _Line:
    """A line whose ``colorcoded`` property counts accesses."""

    internal = False
    send = True

    def __init__(self) -> None:
        self.reads = 0
        self.noansi = "abc"

    @property
    def colorcoded(self) -> str:
        self.reads += 1
        return "abc"


def _process(harness: Harness, line: _Line) -> None:
    harness.add("t", r"^abc")
    harness.current_record = {"line": line}
    harness._eventcb_check_trigger()


def _logger(level: int) -> logging.Logger:
    log = logging.getLogger("test_335_lazy")
    log.setLevel(level)
    return log


def test_colorcoded_not_read_when_debug_is_off(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "bastproxy.plugins.core.triggers.plugin._triggers.get_logger",
        lambda _name: _logger(logging.INFO),
    )
    line = _Line()
    _process(harness, line)
    assert line.reads == 0


def test_colorcoded_logged_when_debug_is_on(
    harness: Harness, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(
        "bastproxy.plugins.core.triggers.plugin._triggers.get_logger",
        lambda _name: _logger(logging.DEBUG),
    )
    line = _Line()
    with caplog.at_level(logging.DEBUG, logger="test_335_lazy"):
        _process(harness, line)
    assert line.reads == 1
    records: list[Any] = caplog.records
    assert any("matched trigger" in r.getMessage() for r in records)

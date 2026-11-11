"""The match debug log only builds ``colorcoded`` when DEBUG is enabled (#335)."""

import logging
from unittest.mock import MagicMock

import pytest

from bastproxy.plugins.core.triggers.plugin._triggers import TriggersPlugin


class _Line:
    """A line whose ``colorcoded`` property counts accesses."""

    def __init__(self) -> None:
        self.reads = 0
        self.noansi = "abc"

    @property
    def colorcoded(self) -> str:
        self.reads += 1
        return "abc"


def _process(line: _Line) -> None:
    stub = MagicMock()
    stub.plugin_id = "plugins.core.triggers"
    stub.regexes = {}
    TriggersPlugin.process_match(stub, line, ["missing"])


def test_colorcoded_not_read_when_debug_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "bastproxy.plugins.core.triggers.plugin._triggers.get_logger",
        lambda _name: _logger(logging.INFO),
    )
    line = _Line()
    _process(line)
    assert line.reads == 0


def test_colorcoded_logged_when_debug_is_on(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(
        "bastproxy.plugins.core.triggers.plugin._triggers.get_logger",
        lambda _name: _logger(logging.DEBUG),
    )
    line = _Line()
    with caplog.at_level(logging.DEBUG, logger="test_335_lazy"):
        _process(line)
    assert line.reads == 1
    assert any("matched the following regexes" in r.getMessage() for r in caplog.records)


def _logger(level: int) -> logging.Logger:
    log = logging.getLogger("test_335_lazy")
    log.setLevel(level)
    return log

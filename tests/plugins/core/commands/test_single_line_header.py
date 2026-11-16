"""Tests for the single-line output header path (#507)."""

from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins.core.commands.plugin._commands import CommandsPlugin

WIDTH = 30
CENTERED = "----- Proxy Info -----"


def _stub(multiline: bool) -> MagicMock:
    stub = MagicMock()
    values: dict[str, Any] = {
        "plugins.core.proxy:line.length.get": lambda: WIDTH,
        "plugins.core.settings:setting.get": lambda _pid, key: (
            multiline if key == "multiline_headers" else "@B"
        ),
        # the real api returns a str, not a list
        "plugins.core.utils:string.center.colored": lambda *_a, **_k: CENTERED,
    }
    stub.api = lambda name: values[name]
    return stub


def test_single_line_header_is_one_line() -> None:
    result = CommandsPlugin._format_output_header(_stub(False), "Proxy Info", "@B", WIDTH)

    assert result == [CENTERED]

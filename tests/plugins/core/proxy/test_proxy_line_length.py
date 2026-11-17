"""Tests for the line.length.get API of the proxy plugin (#421)."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs.context import output_to_client
from bastproxy.plugins.core.proxy.plugin._proxy import ProxyPlugin
from tests.plugins.core.utils.test_utils_output_table import make_utils_stub


def _length(
    linelen: int, cols: int | None, preamble: str = "#BP", client: str | None = "c1"
) -> int:
    strip = make_utils_stub().api("plugins.core.colors:colorcode.strip")
    stub = MagicMock()
    stub.plugin_id = "plugins.core.proxy"

    def api(name: str) -> Any:
        values: dict[str, Any] = {
            "plugins.core.settings:setting.get": lambda _pid, _setting: linelen,
            "plugins.core.clients:client.width.get": lambda _uuid: cols,
            "plugins.core.proxy:preamble.get": lambda: preamble,
            "plugins.core.colors:colorcode.strip": strip,
        }
        return values[name]

    stub.api = api
    with output_to_client(client):
        result: int = ProxyPlugin._api_line_length_get(stub)
    return result


def test_no_target_client_is_linelen() -> None:
    assert _length(80, 120, client=None) == 80


def test_client_without_width_is_linelen() -> None:
    assert _length(80, None) == 80


def test_wide_client_is_capped_at_linelen() -> None:
    assert _length(80, 120) == 80


def test_narrow_client_loses_the_prefix() -> None:
    assert _length(80, 60) == 55


def test_very_narrow_client_gets_the_floor() -> None:
    assert _length(80, 30) == 40


def test_cap_beats_floor() -> None:
    assert _length(30, 100) == 30


def test_longer_preamble_is_subtracted() -> None:
    assert _length(80, 60, preamble="#PROXY") == 52


def test_colored_preamble_ignores_the_codes() -> None:
    assert _length(80, 60, preamble="@R#BP") == 55


@pytest.mark.parametrize("cols", [41, 45, 100])
def test_never_above_linelen(cols: int) -> None:
    assert _length(50, cols) <= 50


def test_wide_preamble_is_subtracted_by_display_width() -> None:
    # two wide characters take four columns
    assert _length(80, 60, preamble="日本") == 54

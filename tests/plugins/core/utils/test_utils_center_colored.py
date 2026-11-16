"""`string.center.colored` defaults its width to the client's line length (#421)."""

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins.core.utils.plugin._utils import UtilsPlugin

WIDTH = 50


def _stub(width: Callable[[], int] | None = None) -> MagicMock:
    stub = MagicMock()
    stub.plugin_id = "plugins.core.utils"

    table: dict[str, Callable[..., Any]] = {
        "plugins.core.colors:colorcode.to.ansicode": lambda text: text,
        "plugins.core.colors:ansicode.strip": lambda text: text,
        "plugins.core.colors:colorcode.strip": lambda text: text,
        "plugins.core.proxy:line.length.get": width or (lambda: WIDTH),
        "plugins.core.utils:line.cap": lambda *a, **k: UtilsPlugin._api_line_cap(stub, *a, **k),
    }
    stub.api = lambda name: table[name]
    return stub


def test_default_length_is_the_client_width() -> None:
    out = UtilsPlugin._api_string_center_colored(_stub(), "hi", "-")

    assert len(out) == WIDTH


def test_default_length_with_endcaps_is_the_client_width() -> None:
    out = UtilsPlugin._api_string_center_colored(_stub(), "hi", "-", endcaps=True)

    assert len(out) == WIDTH


def test_explicit_length_keyword_is_unchanged() -> None:
    out = UtilsPlugin._api_string_center_colored(_stub(), "hi", "-", length=80)

    assert len(out) == 80


def test_explicit_positional_length_is_unchanged() -> None:
    out = UtilsPlugin._api_string_center_colored(_stub(), "hi", "-", 30)

    assert len(out) == 30


def test_explicit_length_never_reads_the_client_width() -> None:
    def boom() -> int:
        raise AssertionError("line.length.get must not be called")

    out = UtilsPlugin._api_string_center_colored(_stub(boom), "hi", "-", 30)

    assert len(out) == 30

"""Behaviour pins for log.level.color.get (#621)."""

import logging
from collections.abc import Callable
from typing import Any

import pytest

from bastproxy.plugins.core.log.plugin._log import LogPlugin

DEFAULTS = {
    "error": ("color_error", "@x136"),
    "warning": ("color_warning", "@y"),
    "info": ("color_info", "@w"),
    "debug": ("color_debug", "@x246"),
    "critical": ("color_critical", "@r"),
}
NUMBERS = {
    "error": logging.ERROR,
    "warning": logging.WARNING,
    "info": logging.INFO,
    "debug": logging.DEBUG,
    "critical": logging.CRITICAL,
}


class _StubLog:
    """Just enough of LogPlugin for _api_log_level_color_get."""

    plugin_id = "plugins.core.log"

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[Any, ...]] = []

    def api(self, name: str) -> Callable[..., Any]:
        assert name == "plugins.core.settings:setting.get"

        def _get(plugin_id: str, setting: str) -> str:
            self.calls.append((plugin_id, setting))
            if self.fail:
                raise RuntimeError("no setting")
            return f"stored-{setting}"

        return _get


def _color(stub: _StubLog, level: int | str) -> str:
    result: str = LogPlugin._api_log_level_color_get(stub, level)
    return result


@pytest.mark.parametrize(("name", "expected"), DEFAULTS.items())
def test_name_returns_setting_value(name: str, expected: tuple[str, str]) -> None:
    stub = _StubLog()
    assert _color(stub, name) == f"stored-{expected[0]}"
    assert stub.calls == [("plugins.core.log", expected[0])]


@pytest.mark.parametrize(("name", "number"), NUMBERS.items())
def test_standard_number_matches_name(name: str, number: int) -> None:
    assert _color(_StubLog(), number) == f"stored-{DEFAULTS[name][0]}"


@pytest.mark.parametrize(("name", "expected"), DEFAULTS.items())
def test_setting_exception_gives_default(name: str, expected: tuple[str, str]) -> None:
    assert _color(_StubLog(fail=True), name) == expected[1]
    assert _color(_StubLog(fail=True), NUMBERS[name]) == expected[1]


@pytest.mark.parametrize("level", ["bogus", "", 7, 0, 55])
def test_unknown_level_gives_empty_string(level: int | str) -> None:
    stub = _StubLog()
    assert _color(stub, level) == ""
    assert stub.calls == []

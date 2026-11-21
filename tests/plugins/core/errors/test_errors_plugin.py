"""Tests for the errors plugin as a view over the logger's error buffer (#672)."""

import logging
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs.logger import ERROR_BUFFER, add_error, clear_errors, get_errors
from bastproxy.plugins.core.commands import CommandResult
from bastproxy.plugins.core.errors.plugin._errors import ErrorPlugin, format_errors


@pytest.fixture(autouse=True)
def _clean_errors() -> Iterator[None]:
    clear_errors()
    yield
    clear_errors()


def _stub(args: dict[str, Any] | None = None) -> Any:
    apis: dict[str, Any] = {
        "plugins.core.errors:error.list": get_errors,
        "plugins.core.errors:error.clear": clear_errors,
        "plugins.core.commands:command.current.args.get": lambda: args,
    }
    stub = MagicMock()
    stub.plugin_id = "plugins.core.errors"
    stub.api = lambda name: apis[name]
    return stub


def _add(n: int) -> None:
    for i in range(n):
        add_error(f"t{i}", f"msg{i}", "ERROR", "src")


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.seen: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.seen.append(record)


@pytest.fixture
def capture() -> Iterator[_Capture]:
    """Route the root logger to a capture handler and the error buffer."""
    root = logging.getLogger()
    saved = list(root.handlers)
    saved_level = root.level
    handler = _Capture()
    root.handlers = [handler, ERROR_BUFFER]
    root.setLevel(logging.DEBUG)
    yield handler
    root.handlers = saved
    root.setLevel(saved_level)


def test_apis_round_trip_through_the_libs_buffer() -> None:
    stub = _stub()
    ErrorPlugin._api_error_add(stub, "now", "boom")
    assert ErrorPlugin._api_error_list(stub) == get_errors()
    assert get_errors()[0]["msg"] == "boom"
    ErrorPlugin._api_error_clear(stub)
    assert ErrorPlugin._api_error_list(stub) == []


def test_show_all_lists_every_error_in_one_format() -> None:
    _add(3)
    result = ErrorPlugin._command_show(_stub({"number": "-1"}))
    assert result == CommandResult(True, format_errors(get_errors()))
    lines = format_errors(get_errors())
    assert sum(1 for line in lines if line.startswith("Time   : ")) == 3
    assert "Level  : ERROR" in lines
    assert "Source : src" in lines


def test_show_one_lists_the_last_error_in_the_same_format() -> None:
    _add(3)
    result = ErrorPlugin._command_show(_stub({"number": "1"}))
    assert result == CommandResult(True, format_errors(get_errors()[-1:]))
    assert "Error  : msg2" in format_errors(get_errors()[-1:])
    assert "Error  : msg1" not in format_errors(get_errors()[-1:])


def test_show_with_no_errors() -> None:
    assert ErrorPlugin._command_show(_stub({"number": "-1"})) == CommandResult(
        True, ["There are no errors"]
    )


def test_show_refuses_a_non_number() -> None:
    assert ErrorPlugin._command_show(_stub({"number": "abc"})) == CommandResult(
        False, ["Please specify a number"]
    )


def test_startup_summary_is_emitted_once_and_not_collected(capture: _Capture) -> None:
    _add(1)
    ErrorPlugin._eventcb_proxy_ready(_stub())
    assert len(capture.seen) == 1
    assert capture.seen[0].levelno == logging.ERROR
    assert "The following errors happened during startup:" in capture.seen[0].getMessage()
    assert len(get_errors()) == 1


def test_startup_summary_logs_nothing_without_errors(capture: _Capture) -> None:
    ErrorPlugin._eventcb_proxy_ready(_stub())
    assert capture.seen == []

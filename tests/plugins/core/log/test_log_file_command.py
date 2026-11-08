"""Regression tests for the log file command's logtype argument (#185)."""

import argparse
from collections.abc import Callable
from typing import Any

import pytest

from bastproxy.plugins.core.log.plugin._log import LogPlugin


class _Handlers(dict[str, str]):
    """A dict standing in for the persistent file handler settings."""

    def sync(self) -> None:
        """Mirror PersistentDict.sync."""


class _StubLog:
    """Just enough of LogPlugin for _command_file."""

    plugin_id = "plugins.core.log"
    logtype_col_length = 20

    def __init__(self, logtypes: list[str], handlers: dict[str, str] | None = None) -> None:
        self.handlers = {"file": _Handlers(handlers or {})}
        self.set_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self._args = {"logtype": logtypes}

    def api(self, name: str) -> Callable[..., Any]:
        if name.endswith("command.current.args.get"):
            return lambda: self._args
        if name.endswith("logger.file.level.set"):

            def _set(*args: Any, **kwargs: Any) -> None:
                self.set_calls.append((args, kwargs))

            return _set
        raise AssertionError(name)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    for arg in LogPlugin._command_file.command_data.arguments:
        parser.add_argument(*arg["args"], **arg["kwargs"])
    return parser


def test_parser_no_args_gives_empty_list() -> None:
    assert _parser().parse_args([]).logtype == []


def test_parser_one_arg_gives_one_item() -> None:
    assert _parser().parse_args(["mudproxy"]).logtype == ["mudproxy"]


def test_parser_two_args_give_two_items() -> None:
    assert _parser().parse_args(["a", "b"]).logtype == ["a", "b"]


def test_no_logtype_lists_and_toggles_nothing() -> None:
    stub = _StubLog([], {"mudproxy": "debug"})
    ok, msgs = LogPlugin._command_file(stub)
    assert ok
    assert "Current types going to file" in msgs
    assert stub.set_calls == []
    assert stub.handlers["file"] == {"mudproxy": "debug"}


def test_one_logtype_toggles_once_without_character_keys() -> None:
    stub = _StubLog(["mudproxy"])
    ok, _msgs = LogPlugin._command_file(stub)
    assert ok
    assert stub.set_calls == [(("mudproxy",), {"level": "debug"})]
    assert [k for k in stub.handlers["file"] if len(k) == 1] == []


@pytest.mark.parametrize("names", [["a", "b"]])
def test_two_logtypes_toggle_each(names: list[str]) -> None:
    stub = _StubLog(names)
    LogPlugin._command_file(stub)
    assert [c[0][0] for c in stub.set_calls] == names

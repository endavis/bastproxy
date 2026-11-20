"""The log console and file commands: --level, no --notimestamp (#621)."""

import argparse
from collections.abc import Callable
from typing import Any

import pytest

from bastproxy.plugins.core.log.plugin._log import LogPlugin


class _Handlers(dict[str, str]):
    """A dict standing in for the persistent handler settings."""

    def sync(self) -> None:
        """Mirror PersistentDict.sync."""


class _StubLog:
    """Just enough of LogPlugin for the console and file commands."""

    plugin_id = "plugins.core.log"
    logtype_col_length = 20

    def __init__(self, kind: str, args: dict[str, Any], handlers: dict[str, str] | None = None):
        self.kind = kind
        self.handlers = {kind: _Handlers(handlers or {})}
        self._args = args

    def api(self, name: str) -> Callable[..., Any]:
        if name.endswith("command.current.args.get"):
            return lambda: self._args
        if name.endswith(f"logger.{self.kind}.level.set"):

            def _set(logtype: str, level: str = "info") -> bool:
                self.handlers[self.kind][logtype] = level
                return True

            return _set
        raise AssertionError(name)


def _command(kind: str) -> Any:
    return getattr(LogPlugin, f"_command_{kind}")


def _parser(kind: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    for arg in _command(kind).command_data.arguments:
        parser.add_argument(*arg["args"], **arg["kwargs"])
    return parser


def test_file_command_has_no_notimestamp() -> None:
    flags = [a for arg in _command("file").command_data.arguments for a in arg["args"]]
    assert "-n" not in flags
    assert "--notimestamp" not in flags


def test_file_help_names_the_real_log_file() -> None:
    description = _command("file").command_data.argparse["kwargs"]["description"]
    assert "bastproxy.log" in description
    assert "data/logs/<logtype>" not in description


@pytest.mark.parametrize("kind", ["console", "file"])
def test_level_defaults_to_none_and_rejects_unknown(kind: str) -> None:
    assert _parser(kind).parse_args(["foo"]).level is None
    assert _parser(kind).parse_args(["foo", "-l", "warning"]).level == "warning"
    with pytest.raises(SystemExit):
        _parser(kind).parse_args(["foo", "--level", "loud"])


@pytest.mark.parametrize("kind", ["console", "file"])
def test_level_option_stores_that_level(kind: str) -> None:
    stub = _StubLog(kind, {"logtype": ["foo"], "level": "warning"})
    result = _command(kind)(stub)
    assert result.success
    assert stub.handlers[kind] == {"foo": "warning"}
    assert "warning" in result.message[0]


@pytest.mark.parametrize("kind", ["console", "file"])
def test_level_option_overrides_a_stored_level(kind: str) -> None:
    stub = _StubLog(kind, {"logtype": ["foo"], "level": "info"}, {"foo": "warning"})
    _command(kind)(stub)
    assert stub.handlers[kind] == {"foo": "info"}


@pytest.mark.parametrize("kind", ["console", "file"])
def test_without_level_still_toggles(kind: str) -> None:
    stub = _StubLog(kind, {"logtype": ["foo"], "level": None})
    _command(kind)(stub)
    assert stub.handlers[kind] == {"foo": "debug"}
    _command(kind)(stub)
    assert stub.handlers[kind] == {"foo": "info"}

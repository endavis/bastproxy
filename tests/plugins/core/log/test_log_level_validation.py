"""Tests for refusing unknown log levels in the level set APIs (#620)."""

import logging
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from bastproxy.libs import logger as logger_module
from bastproxy.plugins.core.log.plugin._log import LogPlugin, _normalize_level


class _Handlers(dict[str, str]):
    """A dict standing in for a PersistentDict."""

    def sync(self) -> None:
        """Mirror PersistentDict.sync."""


class _StubLog:
    """Just enough of LogPlugin for the level set APIs."""

    plugin_id = "plugins.core.log"

    def __init__(self) -> None:
        self.handlers = {k: _Handlers() for k in ("client", "console", "file")}
        self.type_counts: dict[str, dict[str, int]] = {}
        self.synced: list[str] = []

    def _sync_threshold(self, name: str) -> None:
        self.synced.append(name)


def _client(stub: _StubLog, level: Any, flag: bool = True) -> bool:
    return bool(LogPlugin._api_logger_client_level_set(stub, "t620.a", level, flag))


def _console(stub: _StubLog, level: Any) -> bool:
    return bool(LogPlugin._api_logger_console_level_set(stub, "t620.a", level))


def _file(stub: _StubLog, level: Any) -> bool:
    return bool(LogPlugin._api_logger_file_level_set(stub, "t620.a", level))


_SETTERS: list[tuple[str, Callable[[_StubLog, Any], bool]]] = [
    ("client", _client),
    ("console", _console),
    ("file", _file),
]


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    saved = dict(logger_module._thresholds)
    yield
    logger_module._thresholds.clear()
    logger_module._thresholds.update(saved)


@pytest.mark.parametrize(
    ("level", "expected"),
    [
        ("debug", "debug"),
        ("WARNING", "warning"),
        ("Info", "info"),
        (logging.ERROR, "error"),
        (logging.CRITICAL, "critical"),
        ("verbose", None),
        ("", None),
        (None, None),
        (True, None),
        (False, None),
        (7, None),
        (0, None),
        (logging.NOTSET, None),
        (1.5, None),
    ],
)
def test_normalize_level(level: object, expected: str | None) -> None:
    assert _normalize_level(level) == expected


@pytest.mark.parametrize(("kind", "setter"), _SETTERS)
@pytest.mark.parametrize("bad", ["verbose", "", None, True, False, 7, 0])
def test_unknown_level_refused_and_nothing_stored(
    kind: str, setter: Callable[[_StubLog, Any], bool], bad: Any
) -> None:
    stub = _StubLog()
    assert setter(stub, bad) is False
    assert stub.handlers[kind] == {}
    assert stub.synced == []


@pytest.mark.parametrize(("kind", "setter"), _SETTERS)
def test_refusal_keeps_existing_level(kind: str, setter: Callable[[_StubLog, Any], bool]) -> None:
    stub = _StubLog()
    assert setter(stub, "debug") is True
    assert setter(stub, "bogus") is False
    assert stub.handlers[kind] == {"t620.a": "debug"}


@pytest.mark.parametrize(("kind", "setter"), _SETTERS)
@pytest.mark.parametrize(("level", "stored"), [("WARNING", "warning"), (logging.ERROR, "error")])
def test_valid_level_stored_lowercase(
    kind: str, setter: Callable[[_StubLog, Any], bool], level: Any, stored: str
) -> None:
    stub = _StubLog()
    assert setter(stub, level) is True
    assert stub.handlers[kind] == {"t620.a": stored}
    assert stub.synced == ["t620.a"]


def test_client_removal_ignores_level() -> None:
    stub = _StubLog()
    stub.handlers["client"]["t620.a"] = "info"
    assert _client(stub, "bogus", flag=False) is True
    assert stub.handlers["client"] == {}


def test_client_removal_of_unknown_type_returns_true() -> None:
    stub = _StubLog()
    assert _client(stub, None, flag=False) is True

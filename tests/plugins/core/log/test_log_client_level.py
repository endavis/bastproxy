"""Tests for changing the client log level of an existing log type (#617)."""

import logging
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from bastproxy.libs import logger as logger_module
from bastproxy.libs.logger import get_logger
from bastproxy.plugins.core.log.plugin._log import LogPlugin


class _Handlers(dict[str, str]):
    """A dict standing in for a PersistentDict."""

    def sync(self) -> None:
        """Mirror PersistentDict.sync."""


class _StubLog:
    """Just enough of LogPlugin for the client level API and command."""

    plugin_id = "plugins.core.log"
    logtype_col_length = 20

    def __init__(self, args: dict[str, Any] | None = None) -> None:
        self.handlers = {k: _Handlers() for k in ("client", "console", "file")}
        self.type_counts: dict[str, dict[str, int]] = {}
        self.args = args or {}

    def _sync_threshold(self, name: str) -> None:
        LogPlugin._sync_threshold(self, name)  # type: ignore[arg-type]

    def set_level(self, logtype: str, level: str = "info", flag: bool = True) -> None:
        LogPlugin._api_logger_client_level_set(self, logtype, level, flag)

    def api(self, name: str) -> Callable[..., Any]:
        if name.endswith("command.current.args.get"):
            return lambda: self.args
        if name.endswith("logger.client.level.set"):
            return self.set_level
        if name.endswith("logger.console.is.enabled") or name.endswith("logger.file.is.enabled"):
            return lambda logtype, level: False
        if name.endswith("logger.client.is.enabled"):
            return lambda logtype, level: logtype in self.handlers["client"]
        raise AssertionError(name)


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    saved = dict(logger_module._thresholds)
    yield
    logger_module._thresholds.clear()
    logger_module._thresholds.update(saved)
    for name in list(logging.root.manager.loggerDict):
        if name.startswith("t617"):
            logging.getLogger(name).setLevel(logging.NOTSET)


def test_level_replaced_for_existing_type_and_threshold_resynced() -> None:
    stub = _StubLog()
    stub.set_level("t617.a", "info")
    assert not get_logger("t617.a").isEnabledFor(logging.DEBUG)
    stub.set_level("t617.a", "debug")
    assert stub.handlers["client"] == {"t617.a": "debug"}
    assert get_logger("t617.a").isEnabledFor(logging.DEBUG)


def test_command_reports_the_stored_level() -> None:
    stub = _StubLog({"logtype": ["t617.b"], "level": "info", "remove": False})
    stub.handlers["client"]["t617.b"] = "debug"
    result = LogPlugin._command_client(stub)
    assert result.success
    assert stub.handlers["client"] == {"t617.b": "info"}
    assert result.message == ["setting t617.b to log to client at level info"]


def test_removal_still_works() -> None:
    stub = _StubLog()
    stub.set_level("t617.c", "debug")
    stub.set_level("t617.c", flag=False)
    assert stub.handlers["client"] == {}


def test_command_remove_still_works() -> None:
    stub = _StubLog({"logtype": ["t617.d"], "level": "info", "remove": True})
    stub.handlers["client"]["t617.d"] = "debug"
    result = LogPlugin._command_client(stub)
    assert result.success
    assert stub.handlers["client"] == {}
    assert result.message == ["no longer sending t617.d to client"]

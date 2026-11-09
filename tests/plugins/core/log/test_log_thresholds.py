"""Tests for the logger thresholds the log plugin sets from its handler settings (#247)."""

import itertools
import logging
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from bastproxy.libs import logger as logger_module
from bastproxy.libs.logger import LEVELS, get_logger
from bastproxy.plugins.core.log.plugin._log import LogPlugin


class _Handlers(dict[str, str]):
    """A dict standing in for a PersistentDict."""

    def sync(self) -> None:
        """Mirror PersistentDict.sync."""


class _StubLog:
    """Just enough of LogPlugin for the threshold code."""

    plugin_id = "plugins.core.log"

    def __init__(self) -> None:
        self.handlers = {k: _Handlers() for k in ("client", "console", "file")}
        self.type_counts: dict[str, dict[str, int]] = {}
        self.synced: list[str] = []
        self.api = _StubApi()

    def _sync_threshold(self, name: str) -> None:
        LogPlugin._sync_threshold(self, name)  # type: ignore[arg-type]
        self.synced.append(name)


class _StubApi:
    def __init__(self) -> None:
        self.quiet_mode = False
        self.startup = False
        self.enabled = {"console": True, "file": False, "client": False}
        self.args: dict[str, str] = {}

    def __call__(self, name: str) -> Callable[..., Any]:
        if name.endswith("logger.console.is.enabled"):
            return lambda logtype, level: self.enabled["console"]
        if name.endswith("logger.file.is.enabled"):
            return lambda logtype, level: self.enabled["file"]
        if name.endswith("logger.client.is.enabled"):
            return lambda logtype, level: self.enabled["client"]
        if name.endswith("command.current.args.get"):
            return lambda: self.args
        raise AssertionError(name)


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    saved = dict(logger_module._thresholds)
    yield
    logger_module._thresholds.clear()
    logger_module._thresholds.update(saved)
    for name in list(logging.root.manager.loggerDict):
        if name.startswith("t247"):
            logging.getLogger(name).setLevel(logging.NOTSET)


def test_debug_in_any_handler_sets_a_debug_threshold() -> None:
    stub = _StubLog()
    stub.handlers["file"]["t247.a"] = "debug"
    LogPlugin._sync_threshold(stub, "t247.a")  # type: ignore[arg-type]
    assert get_logger("t247.a").isEnabledFor(logging.DEBUG)


def test_no_debug_handler_resets_to_info() -> None:
    stub = _StubLog()
    stub.handlers["file"]["t247.b"] = "debug"
    LogPlugin._sync_threshold(stub, "t247.b")  # type: ignore[arg-type]
    stub.handlers["file"]["t247.b"] = "info"
    LogPlugin._sync_threshold(stub, "t247.b")  # type: ignore[arg-type]
    assert not get_logger("t247.b").isEnabledFor(logging.DEBUG)
    assert get_logger("t247.b").isEnabledFor(logging.INFO)


def test_suffixed_names_use_the_toplevel() -> None:
    stub = _StubLog()
    stub.handlers["console"]["t247.c"] = "debug"
    LogPlugin._sync_threshold(stub, "t247.c:owner")  # type: ignore[arg-type]
    assert get_logger("t247.c:owner").isEnabledFor(logging.DEBUG)


_SETTINGS = (None, "debug", "info", "warning", "error")


@pytest.mark.parametrize(
    ("console", "file", "client"), list(itertools.product(_SETTINGS, repeat=3))
)
def test_invariant_threshold_never_above_a_level_a_handler_accepts(
    console: str | None, file: str | None, client: str | None
) -> None:
    """If a handler would accept (name, level), the logger is enabled for that level."""
    stub = _StubLog()
    name = f"t247.inv.{console}.{file}.{client}"
    for handler, setting in (("console", console), ("file", file), ("client", client)):
        if setting is not None:
            stub.handlers[handler][name] = setting
    LogPlugin._sync_threshold(stub, name)  # type: ignore[arg-type]
    logger = get_logger(name)
    for setting in (console, file, client):
        if setting is None:
            continue
        accepted_from = LEVELS[setting]
        for level in LEVELS.values():
            if level >= accepted_from:
                assert logger.isEnabledFor(level)


@pytest.mark.parametrize(
    ("method", "handler"),
    [
        ("_api_logger_client_level_set", "client"),
        ("_api_logger_console_level_set", "console"),
        ("_api_logger_file_level_set", "file"),
    ],
)
def test_level_set_apis_update_the_threshold(method: str, handler: str) -> None:
    stub = _StubLog()
    name = f"t247.set.{handler}"
    getattr(LogPlugin, method)(stub, name, "debug")
    assert get_logger(name).isEnabledFor(logging.DEBUG)
    assert name in stub.synced


def test_client_level_set_remove_resets_the_threshold() -> None:
    stub = _StubLog()
    LogPlugin._api_logger_client_level_set(stub, "t247.rm", "debug")
    assert get_logger("t247.rm").isEnabledFor(logging.DEBUG)
    LogPlugin._api_logger_client_level_set(stub, "t247.rm", "debug", flag=False)
    assert not get_logger("t247.rm").isEnabledFor(logging.DEBUG)


def test_type_clean_resets_the_threshold_of_removed_types() -> None:
    stub = _StubLog()
    stub.handlers["file"]["t247.clean"] = "debug"
    LogPlugin._sync_threshold(stub, "t247.clean")  # type: ignore[arg-type]
    assert get_logger("t247.clean").isEnabledFor(logging.DEBUG)
    removed = LogPlugin._api_logger_type_clean(stub)
    assert "t247.clean" in removed
    assert not get_logger("t247.clean").isEnabledFor(logging.DEBUG)


def test_command_test_reports_the_handler_flags(caplog: pytest.LogCaptureFixture) -> None:
    stub = _StubLog()
    stub.api.args = {"logtype": "t247.cmd", "message": "hello", "loglevel": "info"}
    stub.api.enabled = {"console": True, "file": False, "client": False}
    with caplog.at_level(logging.DEBUG):
        ok, msgs = LogPlugin._command_test(stub)
    assert ok
    assert "Console: True" in msgs
    assert "File: False" in msgs
    assert "Client: False" in msgs
    assert any(r.name == "t247.cmd" and r.getMessage() == "hello" for r in caplog.records)


def test_command_test_client_flag_true_for_errors() -> None:
    stub = _StubLog()
    stub.api.args = {"logtype": "t247.cmd2", "message": "bad", "loglevel": "error"}
    stub.api.enabled = {"console": False, "file": False, "client": False}
    _ok, msgs = LogPlugin._command_test(stub)
    assert "Client: True" in msgs
    assert "Console: False" in msgs


def test_command_test_flags_follow_quiet_mode_and_startup() -> None:
    stub = _StubLog()
    stub.api.args = {"logtype": "t247.cmd3", "message": "x", "loglevel": "error"}
    stub.api.enabled = {"console": True, "file": True, "client": True}
    stub.api.quiet_mode = True
    stub.api.startup = True
    try:
        _ok, msgs = LogPlugin._command_test(stub)
    finally:
        stub.api.quiet_mode = False
        stub.api.startup = False
    assert "Console: False" in msgs
    assert "File: True" in msgs
    assert "Client: False" in msgs

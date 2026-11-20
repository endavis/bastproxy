"""Cleaning drops only default-level entries and is.enabled stores nothing (#618)."""

import logging
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from bastproxy.libs import logger as logger_module
from bastproxy.plugins.core.log.plugin._log import LogPlugin


class _Handlers(dict[str, str]):
    """A dict standing in for a PersistentDict."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.syncs = 0

    def sync(self) -> None:
        """Mirror PersistentDict.sync, counting calls."""
        self.syncs += 1


class _StubLog:
    """Just enough of LogPlugin for the clean and toggle code."""

    plugin_id = "plugins.core.log"
    logtype_col_length = 20

    def __init__(self) -> None:
        self.handlers = {k: _Handlers() for k in ("client", "console", "file")}
        self.type_counts: dict[str, dict[str, int]] = {}
        self.synced: list[str] = []
        self.set_calls: list[tuple[str, str, str]] = []
        self.args: dict[str, Any] = {"logtype": []}

    def _sync_threshold(self, name: str) -> None:
        LogPlugin._sync_threshold(self, name)  # type: ignore[arg-type]
        self.synced.append(name)

    def api(self, name: str) -> Callable[..., Any]:
        if name.endswith("command.current.args.get"):
            return lambda: self.args
        for handler in ("console", "file"):
            if name.endswith(f"logger.{handler}.level.set"):
                return lambda logtype, level, h=handler: self.set_calls.append((h, logtype, level))
        if name.endswith("logger.type.clean"):
            return lambda: LogPlugin._api_logger_type_clean(self)
        raise AssertionError(name)


@pytest.fixture(autouse=True)
def _restore() -> Iterator[None]:
    saved = dict(logger_module._thresholds)
    yield
    logger_module._thresholds.clear()
    logger_module._thresholds.update(saved)


def test_non_default_levels_survive_clean_with_no_counts() -> None:
    stub = _StubLog()
    stub.handlers["file"]["t618.a"] = "debug"
    stub.handlers["console"]["t618.b"] = "warning"
    stub.handlers["client"]["t618.c"] = "info"
    removed = LogPlugin._api_logger_type_clean(stub)
    assert removed == []
    assert stub.handlers["file"] == {"t618.a": "debug"}
    assert stub.handlers["console"] == {"t618.b": "warning"}
    assert stub.handlers["client"] == {"t618.c": "info"}


def test_default_entries_are_removed_and_threshold_resynced() -> None:
    stub = _StubLog()
    stub.handlers["file"]["t618.d"] = "info"
    stub.handlers["console"]["t618.d"] = "INFO"
    stub.handlers["console"]["t618.e"] = "debug"
    stub.handlers["file"]["t618.f"] = "info"
    stub.handlers["console"]["t618.f"] = "debug"
    removed = LogPlugin._api_logger_type_clean(stub)
    assert removed == ["t618.d", "t618.f"]
    assert stub.handlers["console"] == {"t618.e": "debug", "t618.f": "debug"}
    assert stub.handlers["file"] == {}
    assert stub.synced == ["t618.d", "t618.f"]


def test_shutdown_keeps_a_configured_level() -> None:
    stub = _StubLog()
    stub.handlers["file"]["t618.notloaded"] = "debug"
    LogPlugin._eventcb_proxy_shutdown(stub)
    assert stub.handlers["file"] == {"t618.notloaded": "debug"}


def test_clean_command_lists_removed() -> None:
    stub = _StubLog()
    stub.handlers["file"]["t618.g"] = "info"
    result = LogPlugin._command_clean(stub)
    assert result.success
    assert "t618.g" in result.message


@pytest.mark.parametrize("handler", ["console", "file"])
def test_is_enabled_defaults_to_info_without_storing(handler: str) -> None:
    stub = _StubLog()
    method = getattr(LogPlugin, f"_api_logger_{handler}_is_enabled")
    assert method(stub, "t618.unseen", logging.INFO) is True
    assert method(stub, "t618.unseen", logging.DEBUG) is False
    assert stub.handlers[handler] == {}
    assert stub.handlers[handler].syncs == 0


@pytest.mark.parametrize("handler", ["console", "file"])
def test_is_enabled_uses_a_stored_level(handler: str) -> None:
    stub = _StubLog()
    stub.handlers[handler]["t618.x"] = "debug"
    method = getattr(LogPlugin, f"_api_logger_{handler}_is_enabled")
    assert method(stub, "t618.x", logging.DEBUG) is True


@pytest.mark.parametrize("handler", ["console", "file"])
def test_toggle_unseen_name_goes_to_debug_without_storing(handler: str) -> None:
    stub = _StubLog()
    stub.args = {"logtype": ["t618.new"]}
    getattr(LogPlugin, f"_command_{handler}")(stub)
    assert stub.set_calls == [(handler, "t618.new", "debug")]
    assert stub.handlers[handler] == {}


@pytest.mark.parametrize("handler", ["console", "file"])
def test_toggle_debug_goes_back_to_info(handler: str) -> None:
    stub = _StubLog()
    stub.handlers[handler]["t618.new"] = "debug"
    stub.args = {"logtype": ["t618.new"]}
    getattr(LogPlugin, f"_command_{handler}")(stub)
    assert stub.set_calls == [(handler, "t618.new", "info")]


def _types_stub() -> _StubLog:
    stub = _StubLog()
    stub.args = {"match": ""}
    stub.api = lambda name: (  # type: ignore[method-assign]
        (lambda: 80) if name.endswith("line.length.get") else (lambda: stub.args)
    )
    return stub


def test_types_lists_counted_names_without_a_setting_and_settings_without_counts() -> None:
    stub = _types_stub()
    stub.type_counts["t618.counted"] = {
        "debug": 1,
        "info": 2,
        "warning": 3,
        "error": 4,
        "critical": 5,
    }
    stub.handlers["file"]["t618.setonly"] = "debug"
    result = LogPlugin._command_types(stub)
    lines = {line.split(" : ")[0].strip(): line for line in result.message if " : " in line}
    assert lines["t618.counted"].split(" : ")[1].split() == ["1", "2", "3", "4", "5"]
    assert lines["t618.setonly"].split(" : ")[1].split() == ["0", "0", "0", "0", "0"]

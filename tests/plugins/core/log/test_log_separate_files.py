"""Tests for log types written to their own file (#779)."""

import argparse
import logging
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from bastproxy.libs.logger import RecordContextFilter, RenderFilter, log_to
from bastproxy.plugins.core.log.libs import _custom_logger
from bastproxy.plugins.core.log.libs._custom_logger import TypeFileHandler
from bastproxy.plugins.core.log.plugin._log import LogPlugin


class _StubAPI:
    def __init__(self, table: dict[str, Callable[..., Any]]) -> None:
        self.table = table

    def __call__(self, name: str) -> Callable[..., Any]:
        if name == "libs.api:api.exists":
            return lambda api_name: api_name in self.table
        return self.table[name]


class _Rig:
    def __init__(self, base: Path) -> None:
        self.separate: dict[str, dict[str, bool]] = {}
        self.file_ok = True
        self.handler = TypeFileHandler(base)
        self.handler.api = _StubAPI(  # type: ignore[assignment]
            {
                "plugins.core.log:logger.file.separate.get": lambda t: self.separate.get(t),
                "plugins.core.log:logger.file.is.enabled": lambda n, lvl: (
                    self.file_ok and lvl >= logging.INFO
                ),
            }
        )
        self.handler.addFilter(RenderFilter())
        self.handler.addFilter(RecordContextFilter())
        logging.getLogger().addHandler(self.handler)

    def text(self, base: Path, top: str) -> str:
        self.handler.files[top].flush()
        return (base / top / f"{top}.log").read_text()


@pytest.fixture
def rig(tmp_path: Path) -> Iterator[_Rig]:
    r = _Rig(tmp_path)
    yield r
    logging.getLogger().removeHandler(r.handler)
    r.handler.close()


def test_type_with_own_file_is_written_with_timestamp(rig: _Rig, tmp_path: Path) -> None:
    rig.separate["t779"] = {"timestamp": True}
    log_to(["t779"], logging.INFO, "hello")
    text = rig.text(tmp_path, "t779")
    assert text.endswith("INFO      - hello\n")
    assert len(text.splitlines()[0]) > len("INFO      - hello")


def test_no_timestamp_writes_the_message_only(rig: _Rig, tmp_path: Path) -> None:
    rig.separate["t779"] = {"timestamp": False}
    log_to(["t779"], logging.INFO, "hello")
    assert rig.text(tmp_path, "t779") == "hello\n"


def test_type_without_own_file_creates_nothing(rig: _Rig, tmp_path: Path) -> None:
    log_to(["t779"], logging.INFO, "hello")
    assert not (tmp_path / "t779").exists()


def test_file_level_filter_applies(rig: _Rig, tmp_path: Path) -> None:
    rig.separate["t779"] = {"timestamp": False}
    log_to(["t779"], logging.DEBUG, "quiet")
    log_to(["t779"], logging.INFO, "loud")
    assert rig.text(tmp_path, "t779") == "loud\n"


def test_two_separate_sources_write_once_to_each(rig: _Rig, tmp_path: Path) -> None:
    rig.separate["t779a"] = {"timestamp": False}
    rig.separate["t779b"] = {"timestamp": False}
    log_to(["t779a", "t779b"], logging.INFO, "both")
    assert rig.text(tmp_path, "t779a") == "both\n"
    assert rig.text(tmp_path, "t779b") == "both\n"


def test_only_the_separate_source_is_written(rig: _Rig, tmp_path: Path) -> None:
    rig.separate["t779b"] = {"timestamp": False}
    log_to(["t779a", "t779b"], logging.INFO, "one")
    assert not (tmp_path / "t779a").exists()
    assert rig.text(tmp_path, "t779b") == "one\n"


def test_invalid_top_name_is_never_written(rig: _Rig, tmp_path: Path) -> None:
    rig.separate["../x"] = {"timestamp": False}
    log_to(["../x"], logging.INFO, "no")
    assert rig.handler.files == {}
    assert not (tmp_path.parent / "x").exists()


# --- the API and the command ---


class _Persist(dict[str, Any]):
    def sync(self) -> None:
        """Mirror PersistentDict.sync."""


class _Handler:
    def __init__(self) -> None:
        self.closed: list[str] = []

    def close_type(self, top: str) -> None:
        self.closed.append(top)

    def path_for(self, top: str) -> Path:
        return Path("types") / top / f"{top}.log"


class _StubLog:
    plugin_id = "plugins.core.log"
    logtype_col_length = 20

    def __init__(self, args: dict[str, Any] | None = None) -> None:
        self.separate_files = _Persist()
        self.handlers = {"file": _Persist()}
        self._args = args or {}
        self.level_calls: list[tuple[str, str]] = []

    def api(self, name: str) -> Callable[..., Any]:
        if name.endswith("command.current.args.get"):
            return lambda: self._args
        if name.endswith("logger.file.separate.set"):
            return lambda *a, **k: LogPlugin._api_logger_file_separate_set(self, *a, **k)
        if name.endswith("logger.file.level.set"):

            def _level(t: str, level: str = "info") -> bool:
                self.level_calls.append((t, level))
                return True

            return _level
        raise AssertionError(name)

    def _file_separate_messages(self, args: dict[str, Any]) -> Any:
        return LogPlugin._file_separate_messages(self, args)  # type: ignore[arg-type]  # reason: stub stands in for the plugin


@pytest.fixture
def handler(monkeypatch: pytest.MonkeyPatch) -> _Handler:
    h = _Handler()
    monkeypatch.setattr("bastproxy.plugins.core.log.plugin._log.type_file_handler", lambda: h)
    return h


def test_api_set_get_and_remove(handler: _Handler) -> None:
    stub = _StubLog()
    assert LogPlugin._api_logger_file_separate_set(stub, "t779", True, False)
    assert LogPlugin._api_logger_file_separate_get(stub, "t779") == {"timestamp": False}
    assert LogPlugin._api_logger_file_separate_set(stub, "t779", False)
    assert LogPlugin._api_logger_file_separate_get(stub, "t779") is None
    assert handler.closed == ["t779"]


@pytest.mark.parametrize("name", ["../x", "a/b", ".hidden", "", "a..b"])
def test_api_refuses_invalid_names(handler: _Handler, name: str) -> None:
    stub = _StubLog()
    assert not LogPlugin._api_logger_file_separate_set(stub, name)
    assert dict(stub.separate_files) == {}


def test_command_notimestamp_is_read_and_toggles_off(handler: _Handler) -> None:
    stub = _StubLog({"logtype": ["t779"], "separate": True, "notimestamp": True})
    result = LogPlugin._command_file(stub)
    assert stub.separate_files["t779"] == {"timestamp": False}
    assert "t779 now logs to" in result.message[0]
    result = LogPlugin._command_file(stub)
    assert "t779" not in stub.separate_files
    assert result.message == ["t779 no longer logs to its own file"]
    assert handler.closed == ["t779"]


def test_command_default_has_timestamp_and_level(handler: _Handler) -> None:
    stub = _StubLog({"logtype": ["t779"], "separate": True, "level": "debug"})
    LogPlugin._command_file(stub)
    assert stub.separate_files["t779"] == {"timestamp": True}
    assert stub.level_calls == [("t779", "debug")]


def test_command_lists_types_with_own_file(handler: _Handler) -> None:
    stub = _StubLog({"logtype": [], "separate": True})
    stub.separate_files["t779"] = {"timestamp": True}
    result = LogPlugin._command_file(stub)
    assert any(line.startswith("t779") for line in result.message)


def test_command_refusal_is_reported(handler: _Handler) -> None:
    stub = _StubLog({"logtype": ["a/b"], "separate": True})
    result = LogPlugin._command_file(stub)
    assert result.message == ["could not set a/b to log to its own file"]


def test_parser_accepts_separate_and_notimestamp() -> None:
    parser = argparse.ArgumentParser()
    for arg in LogPlugin._command_file.command_data.arguments:
        parser.add_argument(*arg["args"], **arg["kwargs"])
    ns = parser.parse_args(["t", "-s", "-n"])
    assert ns.logtype == ["t"]
    assert ns.separate
    assert ns.notimestamp


def test_module_accessor_is_none_before_setup() -> None:
    assert _custom_logger.type_file_handler() is _custom_logger.TYPE_FILE_HANDLER

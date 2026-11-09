"""Tests for the log handlers that route records by ``log_sources`` (#247)."""

import io
import logging
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from bastproxy.libs.logger import (
    RECORD_LOG_BUFFER,
    RecordContextFilter,
    RenderFilter,
    clear_record_logs,
    get_logger,
    get_record_logs,
    log_to,
    set_threshold,
)
from bastproxy.plugins.core.log.libs import _custom_logger
from bastproxy.plugins.core.log.libs._custom_logger import (
    CustomClientHandler,
    CustomColorFormatter,
    CustomConsoleHandler,
    CustomRotatingFileHandler,
    type_counts,
)

FMT = "%(levelname)s - %(name)s - %(message)s"
ANSI = re.compile(r"\x1b\[[0-9;]*m")


class _StubAPI:
    """Stands in for API on the handlers: a table of callables by api name."""

    def __init__(self, table: dict[str, Callable[..., Any]]) -> None:
        self.table = table
        self.quiet_mode = False
        self.startup = False

    def __call__(self, name: str) -> Callable[..., Any]:
        if name == "libs.api:api.exists":
            return lambda api_name: api_name in self.table
        return self.table[name]


class _Rig:
    """Three handlers on the root logger, with a table of allowed names for each."""

    def __init__(self, tmp_path: Path) -> None:
        self.allowed: dict[str, set[str]] = {"console": set(), "file": set(), "client": set()}
        self.stream = io.StringIO()
        self.logfile = tmp_path / "unit.log"
        self.sent: list[Any] = []
        self.stub = _StubAPI(
            {
                "plugins.core.log:logger.console.is.enabled": lambda n, lvl: (
                    n in self.allowed["console"]
                ),
                "plugins.core.log:logger.file.is.enabled": lambda n, lvl: n in self.allowed["file"],
                "plugins.core.log:logger.client.is.enabled": lambda n, lvl: (
                    n in self.allowed["client"]
                ),
                "plugins.core.log:log.level.color.get": lambda lvl: "@x136",
            }
        )
        self.console = CustomConsoleHandler(stream=self.stream)
        self.console.formatter = CustomColorFormatter(FMT)
        self.file = CustomRotatingFileHandler(filename=self.logfile)
        self.file.formatter = logging.Formatter(FMT)
        self.client = CustomClientHandler()
        self.client.formatter = CustomColorFormatter(FMT)
        for handler in (self.file, self.console, self.client):
            handler.api = self.stub  # type: ignore[assignment]
            handler.addFilter(RenderFilter())
            handler.addFilter(RecordContextFilter())
            logging.getLogger().addHandler(handler)

    def close(self) -> None:
        for handler in (self.file, self.console, self.client):
            logging.getLogger().removeHandler(handler)
        self.file.close()

    @property
    def file_text(self) -> str:
        self.file.flush()
        return self.logfile.read_text()


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[_Rig]:
    rigs = _Rig(tmp_path)

    def fake_send(message: Any) -> Callable[[], None]:
        rigs.sent.append(message)
        return lambda: None

    monkeypatch.setattr(_custom_logger, "SendDataDirectlyToClient", fake_send)
    saved = {k: dict(v) for k, v in type_counts.items()}
    yield rigs
    rigs.close()
    type_counts.clear()
    type_counts.update(saved)
    for name in list(logging.root.manager.loggerDict):
        if name.startswith("t247"):
            set_threshold(name, None)


def _lines(rig: _Rig) -> list[str]:
    return [line.line for message in rig.sent for line in message]


def test_two_sources_console_and_file_emit_once_under_first_enabled(rig: _Rig) -> None:
    rig.allowed["console"] = {"t247.b"}
    rig.allowed["file"] = {"t247.a", "t247.b"}
    log_to(["t247.a", "t247.b"], logging.INFO, "hello")
    assert rig.stream.getvalue().count("hello") == 1
    assert "INFO - t247.b - hello" in ANSI.sub("", rig.stream.getvalue())
    assert rig.file_text.count("hello") == 1
    assert "INFO - t247.a - hello" in rig.file_text


def test_nothing_is_emitted_for_a_handler_that_allows_no_source(rig: _Rig) -> None:
    log_to(["t247.a", "t247.b"], logging.INFO, "hidden")
    assert rig.stream.getvalue() == ""
    assert rig.file_text == ""
    assert rig.sent == []


def test_client_delivers_error_when_no_source_is_enabled_under_first_source(rig: _Rig) -> None:
    log_to(["t247.a", "t247.b"], logging.ERROR, "bad thing")
    lines = _lines(rig)
    assert len(lines) == 1
    assert "ERROR - t247.a - bad thing" in ANSI.sub("", lines[0])


def test_client_does_not_deliver_info_when_no_source_is_enabled(rig: _Rig) -> None:
    log_to(["t247.a"], logging.INFO, "quiet")
    assert rig.sent == []


def test_client_sends_a_line_per_line_with_the_level_colour(rig: _Rig) -> None:
    rig.allowed["client"] = {"t247.c"}
    get_logger("t247.c").warning("first\r\nsecond")
    assert len(rig.sent) == 1
    lines = list(rig.sent[0])
    assert [ANSI.sub("", line.line) for line in lines] == [
        "WARNING - t247.c - first",
        "second",
    ]
    assert len(lines) == 2
    assert {line.color for line in lines} == {"@x136"}


def test_client_is_silent_at_startup_and_without_the_api(rig: _Rig) -> None:
    rig.allowed["client"] = {"t247.c"}
    rig.stub.startup = True
    get_logger("t247.c").error("early")
    assert rig.sent == []
    rig.stub.startup = False
    del rig.stub.table["plugins.core.log:logger.client.is.enabled"]
    get_logger("t247.c").error("early")
    assert rig.sent == []


def test_quiet_mode_suppresses_the_console_only(rig: _Rig) -> None:
    rig.allowed["console"] = {"t247.q"}
    rig.allowed["file"] = {"t247.q"}
    rig.stub.quiet_mode = True
    get_logger("t247.q").info("shh")
    assert rig.stream.getvalue() == ""
    assert "shh" in rig.file_text


def test_traceback_is_appended_as_separate_lines_and_file_has_no_ansi(rig: _Rig) -> None:
    rig.allowed["console"] = {"t247.e"}
    rig.allowed["file"] = {"t247.e"}
    rig.allowed["client"] = {"t247.e"}
    try:
        raise ValueError("kaboom")
    except ValueError:
        get_logger("t247.e").error("failed", exc_info=True)
    console = ANSI.sub("", rig.stream.getvalue()).splitlines()
    assert console[0].endswith("failed")
    assert any(line.startswith("ValueError: kaboom") for line in console[1:])
    assert not ANSI.search(rig.file_text)
    assert "ValueError: kaboom" in rig.file_text
    assert any("ValueError: kaboom" in line for line in _lines(rig))


def test_console_output_keeps_the_level_colour_wrap(rig: _Rig) -> None:
    rig.allowed["console"] = {"t247.w"}
    get_logger("t247.w").info("coloured")
    assert ANSI.search(rig.stream.getvalue())


def test_type_counts_increment_per_source(rig: _Rig) -> None:
    rig.allowed["file"] = {"t247.n1"}
    type_counts.pop("t247.n1", None)
    type_counts.pop("t247.n2", None)
    log_to(["t247.n1", "t247.n2"], logging.INFO, "counted")
    # the file handler and the (silent) client handler: the client skips counting
    # without its api, the console handler counts too
    assert type_counts["t247.n1"]["info"] >= 1
    assert type_counts["t247.n2"]["info"] >= 1
    assert type_counts["t247.n1"]["info"] == type_counts["t247.n2"]["info"]


def test_render_filter_runs_once_across_three_handlers(rig: _Rig) -> None:
    rig.allowed["console"] = {"t247.r"}
    rig.allowed["file"] = {"t247.r"}
    get_logger("t247.r").info("100%% sure %s", "x\r\ny")
    assert "100% sure x" in rig.file_text
    assert "100% sure x" in ANSI.sub("", rig.stream.getvalue())


def test_record_id_is_set_by_the_handler_filters(
    rig: _Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bastproxy.libs.records import RMANAGER

    class _Rec:
        uuid = "u-1"

    monkeypatch.setattr(RMANAGER, "get_latest_record", lambda: _Rec())
    seen: list[Any] = []

    class _Spy(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            seen.append(getattr(record, "record_id", "missing"))

    spy = _Spy()
    spy.addFilter(RecordContextFilter())
    logging.getLogger().addHandler(spy)
    try:
        get_logger("t247.id").info("x")
    finally:
        logging.getLogger().removeHandler(spy)
    assert seen == ["u-1"]


# --- setup_loggers wiring of the per-record buffer and file format (#247) ---


@pytest.fixture
def wired(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    from bastproxy.libs.api import API

    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_filters = list(root.filters)
    saved_level = root.level
    data_logger = logging.getLogger("data")
    saved_data = (list(data_logger.handlers), data_logger.level, data_logger.propagate)
    monkeypatch.setattr(API, "BASEDATALOGPATH", tmp_path)
    monkeypatch.setattr(API, "LOG_IN_UTC_TZ", False, raising=False)
    monkeypatch.setattr(logging.Formatter, "formatTime", logging.Formatter.formatTime)
    root.handlers = []
    _custom_logger.setup_loggers(logging.DEBUG)
    clear_record_logs()
    yield tmp_path
    for handler in list(root.handlers) + list(data_logger.handlers):
        handler.close()
    root.handlers = saved_handlers
    root.filters = saved_filters
    root.setLevel(saved_level)
    data_logger.handlers, data_logger.level, data_logger.propagate = saved_data
    RECORD_LOG_BUFFER.filters.clear()
    clear_record_logs()
    for name in list(logging.root.manager.loggerDict):
        if name.startswith("t247"):
            set_threshold(name, None)


def test_setup_adds_the_buffer_as_a_root_handler_with_both_filters(wired: Path) -> None:
    root = logging.getLogger()
    assert RECORD_LOG_BUFFER in root.handlers
    kinds = {type(f) for f in RECORD_LOG_BUFFER.filters}
    assert kinds == {RenderFilter, RecordContextFilter}
    # a second setup does not stack filters on the module-level buffer
    _custom_logger.setup_loggers(logging.DEBUG)
    assert len(RECORD_LOG_BUFFER.filters) == 2
    assert root.handlers.count(RECORD_LOG_BUFFER) == 1


def test_reset_logging_removes_every_root_handler(wired: Path) -> None:
    _custom_logger.reset_logging()
    assert logging.getLogger().handlers == []


def test_setup_buffers_a_logged_message_under_the_active_record(
    wired: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bastproxy.libs.records import RMANAGER

    class _Rec:
        uuid = "wired-1"

    monkeypatch.setattr(RMANAGER, "get_latest_record", lambda: _Rec())
    set_threshold("t247.wired", logging.DEBUG)
    get_logger("t247.wired").debug("seen")
    assert [line.rsplit(" - ", 1)[1] for line in get_record_logs("wired-1")] == ["seen"]


def test_data_logger_messages_are_not_buffered(
    wired: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bastproxy.libs.records import RMANAGER

    class _Rec:
        uuid = "wired-data"

    monkeypatch.setattr(RMANAGER, "get_latest_record", lambda: _Rec())
    assert logging.getLogger("data").propagate is False
    logging.getLogger("data.mud").info("raw mud bytes")
    assert get_record_logs("wired-data") == []


def test_file_log_shows_the_record_id_or_a_dash(
    wired: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bastproxy.libs.records import RMANAGER

    class _Rec:
        uuid = "file-id-1"

    set_threshold("t247.file", logging.INFO)
    monkeypatch.setattr(RMANAGER, "get_latest_record", lambda: _Rec())
    get_logger("t247.file").info("with id")
    monkeypatch.setattr(RMANAGER, "get_latest_record", lambda: None)
    get_logger("t247.file").info("no id")
    for handler in logging.getLogger().handlers:
        handler.flush()
    text = "\n".join(p.read_text() for p in wired.rglob("*.log") if p.is_file())
    with_id = next(line for line in text.splitlines() if line.endswith("with id"))
    no_id = next(line for line in text.splitlines() if line.endswith("no id"))
    assert " - file-id-1 - with id" in with_id
    assert " - - - no id" in no_id

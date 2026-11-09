"""Tests for the stdlib logging helpers in bastproxy.libs.logger (#247)."""

import logging
import pathlib
from collections.abc import Iterator

import pytest

from bastproxy.libs import logger as logger_module
from bastproxy.libs.logger import (
    LEVELS,
    MAX_LINES_PER_RECORD,
    MAX_RECORDS,
    RECORD_LOG_BUFFER,
    RecordContextFilter,
    RecordIdFormatter,
    RecordLogBuffer,
    RenderFilter,
    clear_record_logs,
    get_logger,
    get_record_logs,
    get_toplevel,
    log_to,
    set_threshold,
)


@pytest.fixture(autouse=True)
def _clean_thresholds() -> Iterator[None]:
    """Restore the thresholds and the test loggers' levels."""
    saved = dict(logger_module._thresholds)
    yield
    logger_module._thresholds.clear()
    logger_module._thresholds.update(saved)
    for name in list(logging.root.manager.loggerDict):
        if name.startswith("t247"):
            logging.getLogger(name).setLevel(logging.NOTSET)


class _Counter:
    """An argument that counts how often it is turned into a string."""

    def __init__(self) -> None:
        self.calls = 0

    def __str__(self) -> str:
        self.calls += 1
        return "counted"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("mudproxy", "mudproxy"),
        ("plugins.core.log", "plugins.core.log"),
        ("plugins.core.log:CustomClientHandler", "plugins.core.log"),
        ("a:b:c", "a"),
        ("", ""),
    ],
)
def test_get_toplevel(name: str, expected: str) -> None:
    assert get_toplevel(name) == expected


def test_get_logger_defaults_to_explicit_info() -> None:
    logger = get_logger("t247.default")
    assert logger.level == logging.INFO
    assert logger.name == "t247.default"
    assert get_logger("t247.default") is logger


def test_set_threshold_debug_then_reset() -> None:
    set_threshold("t247.thr", logging.DEBUG)
    assert get_logger("t247.thr").level == logging.DEBUG
    set_threshold("t247.thr", None)
    assert get_logger("t247.thr").level == logging.INFO


def test_set_threshold_updates_existing_loggers_including_suffixed() -> None:
    plain = get_logger("t247.same")
    suffixed = get_logger("t247.same:owner")
    other = get_logger("t247.other")
    set_threshold("t247.same", logging.DEBUG)
    assert plain.level == logging.DEBUG
    assert suffixed.level == logging.DEBUG
    assert other.level == logging.INFO
    # a logger created afterwards starts at the threshold
    assert get_logger("t247.same:later").level == logging.DEBUG


def test_set_threshold_from_suffixed_name_applies_to_toplevel() -> None:
    set_threshold("t247.top:suffix", logging.DEBUG)
    assert get_logger("t247.top").level == logging.DEBUG


def test_disabled_level_never_formats_the_message() -> None:
    counter = _Counter()
    get_logger("t247.lazy").debug("value %s", counter)
    assert counter.calls == 0


def test_enabled_level_formats_the_message(caplog: pytest.LogCaptureFixture) -> None:
    counter = _Counter()
    with caplog.at_level(logging.DEBUG):
        get_logger("t247.lazy2").info("value %s", counter)
    assert counter.calls >= 1
    assert "value counted" in caplog.text


def test_log_to_picks_first_enabled_source(caplog: pytest.LogCaptureFixture) -> None:
    set_threshold("t247.second", logging.DEBUG)
    get_logger("t247.first")
    with caplog.at_level(logging.DEBUG):
        log_to(["t247.first", "t247.second"], logging.DEBUG, "hello %s", "there")
    records = [r for r in caplog.records if r.name.startswith("t247")]
    assert len(records) == 1
    assert records[0].name == "t247.second"
    assert records[0].getMessage() == "hello there"
    assert records[0].log_sources == ("t247.first", "t247.second")  # type: ignore[attr-defined]


def test_log_to_emits_exactly_one_record_for_two_enabled_sources(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG):
        log_to(["t247.a", "t247.b"], logging.INFO, "one")
    assert len([r for r in caplog.records if r.name.startswith("t247")]) == 1
    assert [r.name for r in caplog.records if r.name.startswith("t247")] == ["t247.a"]


def test_log_to_emits_nothing_when_no_source_is_enabled(
    caplog: pytest.LogCaptureFixture,
) -> None:
    counter = _Counter()
    with caplog.at_level(logging.DEBUG):
        log_to(["t247.x", "t247.y"], logging.DEBUG, "nope %s", counter)
    assert [r for r in caplog.records if r.name.startswith("t247")] == []
    assert counter.calls == 0


def test_log_to_skips_empty_sources(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG):
        log_to(["", "t247.z"], logging.INFO, "msg")
    records = [r for r in caplog.records if r.name.startswith("t247")]
    assert [r.name for r in records] == ["t247.z"]
    assert records[0].log_sources == ("t247.z",)  # type: ignore[attr-defined]


def test_log_to_passes_exc_info_and_stack_info(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG):
        try:
            raise ValueError("boom")
        except ValueError:
            log_to(["t247.exc"], logging.ERROR, "failed", exc_info=True, stack_info=True)
    record = next(r for r in caplog.records if r.name == "t247.exc")
    assert record.exc_info is not None
    assert record.exc_info[0] is ValueError
    assert record.stack_info


def test_log_to_funcname_is_the_callers() -> None:
    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Capture()
    logging.getLogger().addHandler(handler)
    try:
        log_to(["t247.func"], logging.INFO, "where")
    finally:
        logging.getLogger().removeHandler(handler)
    assert [r.funcName for r in records if r.name == "t247.func"] == [
        "test_log_to_funcname_is_the_callers"
    ]


def test_levels_maps_names_to_ints() -> None:
    assert LEVELS == {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
        "critical": logging.CRITICAL,
    }


def _record(msg: object, *args: object) -> logging.LogRecord:
    return logging.LogRecord("t247.r", logging.INFO, __file__, 1, msg, args or None, None)


def test_render_filter_splits_lines_and_strips_carriage_returns() -> None:
    record = _record("a\r\nb\r\n%s", "c\rd")
    assert RenderFilter().filter(record)
    assert record.msg == "a\nb\nc\nd"
    assert record.args == ()


def test_render_filter_runs_once_per_record() -> None:
    record = _record("x")
    first, second = RenderFilter(), RenderFilter()
    first.filter(record)
    record.msg = "changed after the first render"
    second.filter(record)
    assert record.msg == "changed after the first render"


def test_render_filter_decodes_bytes() -> None:
    record = _record(b"bytes line")
    RenderFilter().filter(record)
    assert record.msg == "bytes line"


def test_render_filter_survives_a_bad_format() -> None:
    record = _record("%d", "not a number")
    assert RenderFilter().filter(record)
    assert record.msg == "%d"


def test_record_context_filter_uses_latest_record(monkeypatch: pytest.MonkeyPatch) -> None:
    from bastproxy.libs.records import RMANAGER

    class _Rec:
        uuid = "abc123"

    monkeypatch.setattr(RMANAGER, "get_latest_record", lambda: _Rec())
    record = _record("x")
    assert RecordContextFilter().filter(record)
    assert record.record_id == "abc123"  # type: ignore[attr-defined]
    # the record object itself is never stored
    assert not any(isinstance(v, _Rec) for v in vars(record).values())


def test_record_context_filter_none_without_a_record(monkeypatch: pytest.MonkeyPatch) -> None:
    from bastproxy.libs.records import RMANAGER

    monkeypatch.setattr(RMANAGER, "get_latest_record", lambda: None)
    record = _record("x")
    RecordContextFilter().filter(record)
    assert record.record_id is None  # type: ignore[attr-defined]


def test_record_context_filter_keeps_an_existing_record_id() -> None:
    record = _record("x")
    record.record_id = "keep"
    RecordContextFilter().filter(record)
    assert record.record_id == "keep"  # type: ignore[attr-defined]


def test_logrecord_class_no_longer_exists_in_src() -> None:
    """A log call cannot be built without being emitted: the LogRecord class is gone (#46)."""
    src = pathlib.Path(logger_module.__file__).resolve().parents[1]
    offenders = [
        str(path.relative_to(src))
        for path in src.rglob("*.py")
        if "LogRecord" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


# --- per-record log buffer and the file formatter (#247) ---


def _buffered(
    msg: str, record_id: str | None, name: str = "t247.buf", level: int = logging.DEBUG
) -> logging.LogRecord:
    record = logging.LogRecord(name, level, __file__, 1, msg, (), None)
    record.record_id = record_id
    return record


def test_buffer_stores_lines_per_record_id() -> None:
    buf = RecordLogBuffer()
    buf.handle(_buffered("one", "r1"))
    buf.handle(_buffered("two", "r2"))
    buf.handle(_buffered("three", "r1"))
    assert [line.rsplit(" - ", 1)[1] for line in buf.get("r1")] == ["one", "three"]
    assert [line.rsplit(" - ", 1)[1] for line in buf.get("r2")] == ["two"]
    assert buf.get("missing") == []
    assert "DEBUG" in buf.get("r1")[0]
    assert "t247.buf" in buf.get("r1")[0]


def test_buffer_caps_lines_per_record_keeping_the_newest() -> None:
    buf = RecordLogBuffer()
    assert MAX_LINES_PER_RECORD == 50
    for i in range(MAX_LINES_PER_RECORD + 5):
        buf.handle(_buffered(f"m{i}", "r1"))
    lines = buf.get("r1")
    assert len(lines) == MAX_LINES_PER_RECORD
    assert lines[0].endswith("m5")
    assert lines[-1].endswith(f"m{MAX_LINES_PER_RECORD + 4}")


def test_buffer_evicts_the_oldest_record_id() -> None:
    buf = RecordLogBuffer()
    assert MAX_RECORDS == 2000
    for i in range(MAX_RECORDS + 1):
        buf.handle(_buffered("x", f"r{i}"))
    assert buf.get("r0") == []
    assert len(buf.get("r1")) == 1
    assert len(buf.get(f"r{MAX_RECORDS}")) == 1
    assert len(buf._lines) == MAX_RECORDS


def test_buffer_ignores_a_missing_record_id() -> None:
    buf = RecordLogBuffer()
    buf.handle(_buffered("x", None))
    assert len(buf._lines) == 0


def test_get_record_logs_returns_a_copy() -> None:
    clear_record_logs()
    RECORD_LOG_BUFFER.handle(_buffered("keep", "copy1"))
    first = get_record_logs("copy1")
    first.append("junk")
    assert len(get_record_logs("copy1")) == 1
    clear_record_logs()
    assert get_record_logs("copy1") == []


def _root_with_buffer(monkeypatch: pytest.MonkeyPatch) -> None:
    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", [RECORD_LOG_BUFFER])
    monkeypatch.setattr(root, "level", logging.DEBUG)
    RECORD_LOG_BUFFER.filters.clear()
    RECORD_LOG_BUFFER.addFilter(RenderFilter())
    RECORD_LOG_BUFFER.addFilter(RecordContextFilter())
    clear_record_logs()


def test_buffer_with_context_filter_stores_under_the_latest_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bastproxy.libs.records import RMANAGER

    class _Rec:
        uuid = "uuid-247"

    _root_with_buffer(monkeypatch)
    monkeypatch.setattr(RMANAGER, "get_latest_record", lambda: _Rec())
    set_threshold("t247.ctx", logging.DEBUG)
    get_logger("t247.ctx").debug("hello %s", "there")
    lines = get_record_logs("uuid-247")
    assert len(lines) == 1
    assert lines[0].endswith("hello there")
    RECORD_LOG_BUFFER.filters.clear()
    clear_record_logs()


def test_debug_below_the_logger_threshold_is_not_buffered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bastproxy.libs.records import RMANAGER

    class _Rec:
        uuid = "uuid-thr"

    _root_with_buffer(monkeypatch)
    monkeypatch.setattr(RMANAGER, "get_latest_record", lambda: _Rec())
    get_logger("t247.thr").debug("dropped")
    get_logger("t247.thr").info("kept")
    lines = get_record_logs("uuid-thr")
    assert [line.rsplit(" - ", 1)[1] for line in lines] == ["kept"]
    RECORD_LOG_BUFFER.filters.clear()
    clear_record_logs()


def test_record_id_formatter_shows_the_id_or_a_dash() -> None:
    fmt = RecordIdFormatter("%(levelname)s - %(record_id)s - %(message)s")
    with_id = _buffered("m", "abc")
    assert fmt.format(with_id) == "DEBUG - abc - m"
    without = _buffered("m", None)
    assert fmt.format(without) == "DEBUG - - - m"
    # the record keeps None, so the buffer's check still works
    assert without.record_id is None  # type: ignore[attr-defined]

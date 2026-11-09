"""The records detail command shows the log lines buffered for a record (#247)."""

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from bastproxy.libs.logger import RECORD_LOG_BUFFER, clear_record_logs
from bastproxy.plugins.debug.records.plugin import _records
from bastproxy.plugins.debug.records.plugin._records import RecordPlugin


class _Record:
    uuid = "rec-247"

    def get_formatted_details(self, **_kwargs: Any) -> list[str]:
        return ["details"]


class _StubPlugin:
    plugin_id = "plugins.debug.records"

    def __init__(self, show: bool, args: dict[str, Any], base: Path) -> None:
        self.show = show
        self.args = args
        self.api = _StubApi(self)
        self.api.BASEDATAPATH = base  # type: ignore[attr-defined]


class _StubApi:
    def __init__(self, owner: _StubPlugin) -> None:
        self.owner = owner

    def __call__(self, name: str) -> Callable[..., Any]:
        if name.endswith("command.current.args.get"):
            return lambda: self.owner.args
        if name.endswith("setting.get"):
            return lambda _pid, _name: self.owner.show
        raise AssertionError(name)


@pytest.fixture(autouse=True)
def _record_found(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(_records.RMANAGER, "get_record", lambda _uid: _Record())
    clear_record_logs()
    yield
    clear_record_logs()


def _args(**extra: Any) -> dict[str, Any]:
    base = {
        "uid": "rec-247",
        "update": "",
        "full_children_records": False,
        "include_updates": True,
        "dump": False,
    }
    return base | extra


def _buffer_line(msg: str) -> None:
    import logging

    record = logging.LogRecord("t247.rec", logging.DEBUG, __file__, 1, msg, (), None)
    record.record_id = "rec-247"
    RECORD_LOG_BUFFER.handle(record)


def _detail(show: bool, base: Path, **extra: Any) -> list[str]:
    stub = _StubPlugin(show, _args(**extra), base)
    ok, lines = RecordPlugin._command_detail(stub)
    assert ok
    return list(lines)


def test_setting_on_shows_the_buffered_lines(tmp_path: Path) -> None:
    _buffer_line("first")
    _buffer_line("second")
    lines = _detail(True, tmp_path)
    assert lines[0] == "details"
    assert lines[1] == "Log messages :"
    assert lines[2].startswith("    ") and lines[2].endswith("first")
    assert lines[3].startswith("    ") and lines[3].endswith("second")


def test_setting_on_with_no_lines_shows_none(tmp_path: Path) -> None:
    assert _detail(True, tmp_path)[1:] == ["Log messages :", "    none"]


def test_setting_off_shows_no_section(tmp_path: Path) -> None:
    _buffer_line("first")
    assert _detail(False, tmp_path) == ["details"]


def test_dump_includes_the_section(tmp_path: Path) -> None:
    _buffer_line("first")
    lines = _detail(True, tmp_path, dump=True)
    assert lines[0].startswith("Record dumped to")
    text = (tmp_path / "dumps" / "rec-247.txt").read_text()
    assert "Log messages :" in text
    assert text.splitlines()[-1].endswith("first")


def test_update_view_has_no_section(tmp_path: Path) -> None:
    class _Update:
        def format_detailed(self) -> list[str]:
            return ["update text"]

    _Record.get_update = lambda _self, _u: _Update()  # type: ignore[attr-defined]
    try:
        assert _detail(True, tmp_path, update="u1") == ["update text"]
    finally:
        del _Record.get_update  # type: ignore[attr-defined]

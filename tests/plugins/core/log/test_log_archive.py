"""Tests for zipping rotated log files, retention and the archive command (#779)."""

import asyncio
import datetime
import logging
import os
import stat
import time
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from bastproxy.libs.validators import int_range
from bastproxy.plugins.core.log.libs import _custom_logger
from bastproxy.plugins.core.log.libs._custom_logger import (
    ArchivingFileHandler,
    CustomRotatingFileHandler,
    archive_file,
    prune_archives,
    run_archive_job,
    sweep_rotated,
)
from bastproxy.plugins.core.log.plugin._log import LogPlugin

_POSIX_MODES = pytest.mark.skipif(
    os.name == "nt", reason="POSIX permission bits are not reported on Windows"
)


class _StubAPI:
    def __init__(self, retention: int | None = None) -> None:
        self.table: dict[str, Callable[..., Any]] = {}
        if retention is not None:
            self.table["plugins.core.settings:setting.get"] = lambda plugin, name: retention
        self.asked: list[tuple[str, str]] = []

    def __call__(self, name: str) -> Callable[..., Any]:
        if name == "libs.api:api.exists":
            return lambda api_name: api_name in self.table
        return self.table[name]


def _handler(path: Path, retention: int | None = None) -> CustomRotatingFileHandler:
    handler = CustomRotatingFileHandler(filename=path, archive=True)
    handler.api = _StubAPI(retention)  # type: ignore[assignment]
    handler.formatter = logging.Formatter("%(message)s")
    return handler


def _write(handler: logging.Handler, msg: str) -> None:
    handler.handle(logging.LogRecord("t779", logging.INFO, "f", 1, msg, None, None))


def test_archive_file_makes_a_zip_and_removes_the_source(tmp_path: Path) -> None:
    src = tmp_path / "bastproxy.log.2026-11-01"
    src.write_text("data")
    target = archive_file(src, tmp_path / "archive")
    assert target == tmp_path / "archive" / "bastproxy.log.2026-11-01.zip"
    assert not src.exists()
    with zipfile.ZipFile(target) as zf:
        assert zf.namelist() == ["bastproxy.log.2026-11-01"]
        assert zf.read("bastproxy.log.2026-11-01") == b"data"


def test_archive_file_never_replaces_a_zip(tmp_path: Path) -> None:
    for _ in range(2):
        src = tmp_path / "x.log.2026-11-01"
        src.write_text("data")
        last = archive_file(src, tmp_path / "archive")
    assert last.name == "x.log.2026-11-01-1.zip"
    assert len(list((tmp_path / "archive").glob("*.zip"))) == 2


@_POSIX_MODES
def test_archive_is_private(tmp_path: Path) -> None:
    src = tmp_path / "x.log.2026-11-01"
    src.write_text("data")
    target = archive_file(src, tmp_path / "archive")
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert stat.S_IMODE(target.parent.stat().st_mode) == 0o700


def test_rollover_archives_when_enabled(tmp_path: Path) -> None:
    handler = _handler(tmp_path / "bastproxy.log")
    _write(handler, "one")
    handler.doRollover()
    _write(handler, "two")
    handler.close()
    assert len(list((tmp_path / "archive").glob("*.zip"))) == 1
    assert [p.name for p in tmp_path.iterdir() if p.name.startswith("bastproxy.log.")] == []
    assert (tmp_path / "bastproxy.log").read_text() == "two\n"


def test_midnight_path_archives(tmp_path: Path) -> None:
    handler = _handler(tmp_path / "bastproxy.log")
    _write(handler, "one")
    # a rollover time already past; 0 would make doRollover call time.localtime on a time
    # before 1970, which raises OSError on Windows (#832)
    handler.rolloverAt = int(time.time()) - 1
    _write(handler, "two")
    handler.close()
    assert len(list((tmp_path / "archive").glob("*.zip"))) == 1


def test_default_keeps_the_plain_rename(tmp_path: Path) -> None:
    handler = CustomRotatingFileHandler(filename=tmp_path / "bastproxy.log")
    handler.formatter = logging.Formatter("%(message)s")
    _write(handler, "one")
    handler.doRollover()
    handler.close()
    assert not (tmp_path / "archive").exists()
    assert len([p for p in tmp_path.iterdir() if p.name.startswith("bastproxy.log.")]) == 1


def test_sweep_zips_old_plain_files_only(tmp_path: Path) -> None:
    log = tmp_path / "bastproxy.log"
    log.write_text("now")
    (tmp_path / "bastproxy.log.2026-11-01").write_text("a")
    (tmp_path / "bastproxy.log.2026-11-02_10-00-00").write_text("b")
    (tmp_path / "bastproxy.log.bak").write_text("c")
    (tmp_path / "other.txt").write_text("d")
    done = sweep_rotated(log, tmp_path / "archive")
    assert len(done) == 2
    assert log.exists()
    assert (tmp_path / "bastproxy.log.bak").exists()
    assert (tmp_path / "other.txt").exists()


def test_prune_removes_only_old_zips(tmp_path: Path) -> None:
    arch = tmp_path / "archive"
    arch.mkdir()
    old, new, other = arch / "old.zip", arch / "new.zip", arch / "keep.txt"
    for path in (old, new, other):
        path.write_text("x")
    now = 1_000_000_000.0
    os.utime(old, (now - 40 * 86400, now - 40 * 86400))
    os.utime(new, (now - 5 * 86400, now - 5 * 86400))
    os.utime(other, (now - 400 * 86400, now - 400 * 86400))
    assert prune_archives(arch, 30, now) == [old]
    assert new.exists()
    assert other.exists()


def test_prune_zero_keeps_everything(tmp_path: Path) -> None:
    arch = tmp_path / "archive"
    arch.mkdir()
    old = arch / "old.zip"
    old.write_text("x")
    os.utime(old, (0, 0))
    assert prune_archives(arch, 0, 1e12) == []
    assert old.exists()


def test_run_job_prunes_with_the_retention_given(tmp_path: Path) -> None:
    arch = tmp_path / "archive"
    arch.mkdir()
    old = arch / "old.zip"
    old.write_text("x")
    os.utime(old, (0, 0))
    run_archive_job(None, tmp_path / "bastproxy.log", 30, now=100 * 86400.0)
    assert not old.exists()


def test_retention_is_read_from_settings_at_rotation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[int] = []
    monkeypatch.setattr(
        _custom_logger, "run_archive_job", lambda rotated, log, days, now=None: seen.append(days)
    )
    handler = _handler(tmp_path / "bastproxy.log", retention=7)
    _write(handler, "one")
    handler.doRollover()
    handler.close()
    assert seen == [7]


def test_retention_defaults_without_settings_api(tmp_path: Path) -> None:
    handler = _handler(tmp_path / "bastproxy.log")
    assert handler._retention_days() == 30
    handler.close()


def test_archive_now_rotates_zips_and_stays_writable(tmp_path: Path) -> None:
    handler = _handler(tmp_path / "bastproxy.log")
    _write(handler, "one")
    when = datetime.datetime(2026, 11, 5, 10, 30, 15)
    rotated = handler.archive_now(when)
    assert rotated == tmp_path / "bastproxy.log.2026-11-05_10-30-15"
    assert (tmp_path / "archive" / "bastproxy.log.2026-11-05_10-30-15.zip").exists()
    assert not rotated.exists()
    _write(handler, "two")
    handler.close()
    assert (tmp_path / "bastproxy.log").read_text() == "two\n"


def test_archive_now_of_an_empty_file_is_none(tmp_path: Path) -> None:
    handler = _handler(tmp_path / "bastproxy.log")
    assert handler.archive_now() is None
    handler.close()


def test_delayed_handler_archive_now_without_file(tmp_path: Path) -> None:
    handler = ArchivingFileHandler(tmp_path / "t.log", delay=True)
    assert handler.archive_now() is None
    handler.close()


async def test_job_runs_through_to_thread_with_a_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Callable[[], None]] = []
    real = asyncio.to_thread

    async def spy(func: Callable[[], None]) -> None:
        calls.append(func)
        await real(func)

    monkeypatch.setattr(asyncio, "to_thread", spy)
    handler = _handler(tmp_path / "bastproxy.log")
    _write(handler, "one")
    handler.doRollover()
    handler.close()
    await asyncio.gather(*list(_custom_logger._ARCHIVE_TASKS))
    assert len(calls) == 1
    assert len(list((tmp_path / "archive").glob("*.zip"))) == 1


async def test_failed_job_is_logged_on_the_loop(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def boom() -> None:
        raise OSError("disk full")

    caplog.set_level(logging.ERROR)
    _custom_logger._schedule_archive(boom)
    await asyncio.gather(*list(_custom_logger._ARCHIVE_TASKS), return_exceptions=True)
    await asyncio.sleep(0)
    assert "archiving a log file failed" in caplog.text


def test_failed_inline_job_does_not_raise(capsys: pytest.CaptureFixture[str]) -> None:
    def boom() -> None:
        raise OSError("disk full")

    _custom_logger._schedule_archive(boom)
    assert "disk full" in capsys.readouterr().err


def test_retention_setting_validator() -> None:
    validator = int_range(0, label="retention days")
    assert validator(0) == ""
    assert validator(30) == ""
    assert validator(-1) != ""


# --- the archive command ---


class _Target:
    def __init__(self, result: Path | None) -> None:
        self.result = result
        self.calls = 0

    def archive_now(self) -> Path | None:
        self.calls += 1
        return self.result


class _Types:
    def archive_type(self, top: str) -> Path | None:
        return Path(top)


class _StubLog:
    def __init__(self, targets: list[str]) -> None:
        self.separate_files = {"t779": {"timestamp": True}}
        self.targets = targets

    def api(self, name: str) -> Callable[..., Any]:
        return lambda: {"target": self.targets}


def test_archive_command(monkeypatch: pytest.MonkeyPatch) -> None:
    main, netdata = _Target(Path("m")), _Target(None)
    monkeypatch.setattr(
        "bastproxy.plugins.core.log.plugin._log.archive_target",
        lambda n: {"main": main, "networkdata": netdata}.get(n),
    )
    monkeypatch.setattr("bastproxy.plugins.core.log.plugin._log.type_file_handler", _Types)
    result = LogPlugin._command_archive(_StubLog(["main", "networkdata", "t779", "nope"]))
    assert result.message == [
        "archived main",
        "networkdata is empty",
        "archived t779",
        "nope is not an archive target",
    ]
    assert main.calls == 1


def test_archive_command_without_target_lists_targets() -> None:
    result = LogPlugin._command_archive(_StubLog([]))
    assert result.message == ["Valid archive targets", "main", "networkdata", "t779"]

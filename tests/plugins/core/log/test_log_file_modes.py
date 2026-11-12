"""Tests for the modes of log directories and files."""

import os
import stat
from collections.abc import Iterator
from pathlib import Path

import pytest

from bastproxy.plugins.core.log.libs._custom_logger import (
    CustomRotatingFileHandler,
    PrivateTimedRotatingFileHandler,
    make_log_dir,
)


@pytest.fixture
def umask022() -> Iterator[None]:
    old = os.umask(0o022)
    yield
    os.umask(old)


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


# Windows has no POSIX permission bits: stat reports 0o777 for a directory and 0o666 for a
# writable file whatever mode was asked for, and the user's ACL keeps the files private.
_POSIX_MODES = pytest.mark.skipif(
    os.name == "nt", reason="POSIX permission bits; Windows uses ACLs"
)


@_POSIX_MODES
def test_make_log_dir_creates_private_dirs(tmp_path: Path, umask022: None) -> None:
    target = tmp_path / "logs" / "networkdata"
    make_log_dir(target)
    assert _mode(target) == 0o700
    assert _mode(target.parent) == 0o700


@_POSIX_MODES
def test_make_log_dir_keeps_existing_dir_mode(tmp_path: Path, umask022: None) -> None:
    existing = tmp_path / "logs"
    existing.mkdir()
    make_log_dir(existing / "networkdata")
    assert _mode(existing) == 0o755
    assert _mode(existing / "networkdata") == 0o700


@_POSIX_MODES
@pytest.mark.parametrize("cls", [CustomRotatingFileHandler, PrivateTimedRotatingFileHandler])
def test_log_files_are_private_including_after_rollover(
    cls: type, tmp_path: Path, umask022: None
) -> None:
    logfile = tmp_path / "test.log"
    handler = cls(filename=logfile)
    try:
        assert _mode(logfile) == 0o600
        handler.doRollover()
        assert _mode(logfile) == 0o600
        rotated = [p for p in tmp_path.iterdir() if p != logfile]
        assert len(rotated) == 1
        assert _mode(rotated[0]) == 0o600
    finally:
        handler.close()


@_POSIX_MODES
def test_existing_log_file_mode_is_unchanged(tmp_path: Path, umask022: None) -> None:
    logfile = tmp_path / "test.log"
    logfile.write_text("old\n")
    logfile.chmod(0o644)
    handler = PrivateTimedRotatingFileHandler(filename=logfile)
    handler.close()
    assert _mode(logfile) == 0o644


@_POSIX_MODES
@pytest.mark.parametrize("cls", [CustomRotatingFileHandler, PrivateTimedRotatingFileHandler])
def test_new_log_files_are_created_private_without_a_chmod(
    cls: type, tmp_path: Path, umask022: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_chmod(*args: object, **kwargs: object) -> None:
        raise AssertionError("os.chmod must not be needed to make a new file private")

    monkeypatch.setattr(os, "chmod", no_chmod)
    logfile = tmp_path / "test.log"
    handler = cls(filename=logfile)
    try:
        assert _mode(logfile) == 0o600
        handler.doRollover()
        assert _mode(logfile) == 0o600
    finally:
        handler.close()


def test_new_log_file_is_opened_with_private_mode(
    tmp_path: Path, umask022: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    modes: list[int] = []
    real_open = os.open

    def spy(path: str, flags: int, mode: int = 0o777) -> int:
        modes.append(mode)
        return real_open(path, flags, mode)

    monkeypatch.setattr(os, "open", spy)
    handler = PrivateTimedRotatingFileHandler(filename=tmp_path / "test.log")
    handler.close()
    assert modes == [0o600]

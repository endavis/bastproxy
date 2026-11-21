"""Tests for the file mode used by SSC._command_setssc."""

import os
import stat
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from bastproxy.plugins.core.ssc.plugin._ssc import SSC

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")


def _make_ssc(directory: Path, value: str) -> SSC:
    """Build an SSC without the plugin loader, stubbing the command args."""
    ssc = object.__new__(SSC)
    ssc.name = "secret"
    ssc.desc = "secret"
    ssc.file_name = directory / "secret"

    def api(name: str) -> Callable[[], dict[str, str]]:
        assert name == "plugins.core.commands:command.current.args.get"
        return lambda: {"value": value}

    ssc.api = api  # type: ignore[assignment]
    return ssc


@pytest.fixture
def umask_022() -> Iterator[None]:
    old = os.umask(0o022)
    try:
        yield
    finally:
        os.umask(old)


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


@posix_only
def test_new_file_has_mode_0600_and_content(tmp_path: Path, umask_022: None) -> None:
    ssc = _make_ssc(tmp_path, "x")
    result = ssc._command_setssc()
    assert result.message == ["secret saved"]
    assert _mode(ssc.file_name) == 0o600
    assert ssc.file_name.read_text(encoding="utf-8") == "x"


@posix_only
def test_mode_is_0600_when_data_is_first_written(
    tmp_path: Path, umask_022: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    ssc = _make_ssc(tmp_path, "x")
    modes: list[int] = []
    real_fdopen = os.fdopen

    def spy(fd: int, *args: Any, **kwargs: Any) -> Any:
        modes.append(stat.S_IMODE(os.fstat(fd).st_mode))
        return real_fdopen(fd, *args, **kwargs)

    monkeypatch.setattr(os, "fdopen", spy)
    ssc._command_setssc()
    assert modes == [0o600]


@posix_only
def test_existing_file_becomes_0600_and_content_replaced(
    tmp_path: Path, umask_022: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    ssc = _make_ssc(tmp_path, "new")
    ssc.file_name.write_text("old content that is longer", encoding="utf-8")
    ssc.file_name.chmod(0o644)
    modes: list[int] = []
    real_fdopen = os.fdopen

    def spy(fd: int, *args: Any, **kwargs: Any) -> Any:
        modes.append(stat.S_IMODE(os.fstat(fd).st_mode))
        return real_fdopen(fd, *args, **kwargs)

    monkeypatch.setattr(os, "fdopen", spy)
    ssc._command_setssc()
    assert modes == [0o600]
    assert _mode(ssc.file_name) == 0o600
    assert ssc.file_name.read_text(encoding="utf-8") == "new"


def test_empty_value_writes_nothing(tmp_path: Path) -> None:
    ssc = _make_ssc(tmp_path, "")
    result = ssc._command_setssc()
    assert result.message == ["Please enter the secret"]
    assert not ssc.file_name.exists()

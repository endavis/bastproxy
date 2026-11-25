"""Tests for the networkdata log toggle and its archiving (#783)."""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from bastproxy.plugins.core.log.libs import _custom_logger
from bastproxy.plugins.core.log.libs._custom_logger import NetworkDataFileHandler
from tests.plugins.core.log.test_custom_logger import wired as wired


class _StubAPI:
    def __init__(self, value: bool | None) -> None:
        self.table: dict[str, Callable[..., Any]] = {}
        if value is not None:
            self.table["plugins.core.settings:setting.get"] = lambda plugin, name: value

    def __call__(self, name: str) -> Callable[..., Any]:
        if name == "libs.api:api.exists":
            return lambda api_name: api_name in self.table
        return self.table[name]


def _handler(tmp_path: Path, value: bool | None) -> NetworkDataFileHandler:
    handler = NetworkDataFileHandler(tmp_path / "networkdata.log", when="midnight", archive=True)
    handler.api = _StubAPI(value)  # type: ignore[assignment]
    handler.formatter = logging.Formatter("%(message)s")
    return handler


def _record(msg: str) -> logging.LogRecord:
    return logging.LogRecord("data.mud", logging.INFO, "f", 1, msg, None, None)


def test_writes_when_on(tmp_path: Path) -> None:
    handler = _handler(tmp_path, True)
    handler.handle(_record("line"))
    handler.close()
    assert (tmp_path / "networkdata.log").read_text() == "line\n"


def test_writes_without_the_settings_api(tmp_path: Path) -> None:
    handler = _handler(tmp_path, None)
    handler.handle(_record("line"))
    handler.close()
    assert (tmp_path / "networkdata.log").read_text() == "line\n"


def test_writes_nothing_when_off(tmp_path: Path) -> None:
    handler = _handler(tmp_path, False)
    handler.handle(_record("line"))
    handler.close()
    assert (tmp_path / "networkdata.log").read_text() == ""


def test_rollover_archives_into_the_networkdata_archive(tmp_path: Path) -> None:
    handler = _handler(tmp_path, True)
    handler.handle(_record("line"))
    handler.doRollover()
    handler.close()
    assert len(list((tmp_path / "archive").glob("*.zip"))) == 1


def test_setup_wires_archiving_handlers(wired: Path) -> None:
    data = logging.getLogger("data").handlers
    assert any(isinstance(h, NetworkDataFileHandler) and h.archive for h in data)
    root = logging.getLogger().handlers
    assert any(isinstance(h, _custom_logger.TypeFileHandler) for h in root)
    main = _custom_logger.archive_target("main")
    assert main is not None
    assert main.archive
    assert _custom_logger.archive_target("networkdata") is not None
    assert _custom_logger.type_file_handler() is not None

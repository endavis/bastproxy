"""The resource command must handle open files without a mode, as on Windows (#691)."""

from collections import namedtuple
from typing import Any
from unittest.mock import MagicMock

import psutil
import pytest

from bastproxy.plugins.core.proxy.plugin import _proxy
from bastproxy.plugins.core.proxy.plugin._proxy import ProxyPlugin

# psutil's open-file entry on Windows has only these two fields
WindowsOpenFile = namedtuple("WindowsOpenFile", ["path", "fd"])
LinuxOpenFile = namedtuple("LinuxOpenFile", ["path", "fd", "position", "mode", "flags"])


def _run(monkeypatch: pytest.MonkeyPatch, open_files: list[Any]) -> list[dict[str, Any]]:
    """Run the resource command with the given open files and return the open-files rows."""
    real_process = psutil.Process()

    class _Process:
        """The real process, except for its open files."""

        def __init__(self, _pid: int) -> None:
            pass

        def open_files(self) -> list[Any]:
            return open_files

        def __getattr__(self, name: str) -> Any:
            return getattr(real_process, name)

    monkeypatch.setattr(_proxy.psutil, "Process", _Process)
    tables: dict[str, list[dict[str, Any]]] = {}
    values = {"networkinterfaces": False, "openfiles": True, "ports": False}
    stub = MagicMock()

    def table(title: str, rows: list[dict[str, Any]], *_a: Any, **_k: Any) -> list[str]:
        tables[title] = rows
        return [f"TABLE {title}"]

    def api(name: str) -> Any:
        if name == "plugins.core.commands:command.current.args.get":
            return lambda: values
        if name == "plugins.core.commands:output.header.format":
            return lambda title: [f"== {title} =="]
        if name == "plugins.core.utils:table.format":
            return table
        return MagicMock()

    stub.api.side_effect = api
    result = ProxyPlugin._command_resource(stub)
    assert result.success is True
    return tables["Open Files"]


def test_open_file_without_mode_shows_na(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = _run(monkeypatch, [WindowsOpenFile(path="C:\\log.txt", fd=-1)])
    assert rows == [{"path": "C:\\log.txt", "mode": "n/a"}]


def test_open_file_with_mode_shows_it(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = _run(monkeypatch, [LinuxOpenFile("/tmp/log", 3, 0, "w", 1)])
    assert rows == [{"path": "/tmp/log", "mode": "w"}]

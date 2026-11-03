"""Tests for per-command call and error counts and the detail command (#92)."""

import datetime
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs import argp
from bastproxy.plugins.core.commands.libs import _command
from bastproxy.plugins.core.commands.libs._command import CommandClass, CommandStats
from bastproxy.plugins.core.commands.plugin._commands import CommandsPlugin

PID = "plugins.test.a"


@pytest.fixture(autouse=True)
def _patch_command_module(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_command, "API", MagicMock())
    monkeypatch.setattr(_command, "LogRecord", MagicMock())
    monkeypatch.setattr(_command, "CmdArgsRecord", lambda owner, data, **kw: dict(data))


def _make(function: Callable[..., Any], name: str = "x") -> CommandClass:
    parser = argp.ArgumentParser(add_help=False)
    parser.add_argument("-h", "--help", action="store_true")
    return CommandClass(PID, name, function, parser)


def _raiser() -> None:
    raise ValueError("boom")


def test_counts_increment_on_run() -> None:
    cmd = _make(lambda: True)
    cmd.run("")
    cmd.run("")
    assert cmd.count == 2
    assert cmd.count_since_reload == 2
    assert cmd.stats.error_count == 0


def test_parse_failure_and_help_do_not_count() -> None:
    cmd = _make(lambda: True)
    cmd.run('"unterminated')
    cmd.run("-h")
    assert cmd.count == 0
    assert cmd.stats.error_count == 0


def test_returning_false_is_not_an_error() -> None:
    cmd = _make(lambda: False)
    cmd.run("")
    assert cmd.count == 1
    assert cmd.stats.error_count == 0


def test_exception_is_recorded() -> None:
    cmd = _make(_raiser)
    assert cmd.run("")[0] is False
    assert cmd.stats.error_count == 1
    assert cmd.stats.last_error == "ValueError: boom"
    assert isinstance(cmd.stats.last_error, str)
    assert cmd.stats.last_error_time is not None
    assert cmd.stats.last_error_time.tzinfo == datetime.UTC
    cmd.record_error(KeyError("k"))
    assert cmd.stats.error_count == 2
    assert cmd.stats.last_error == "KeyError: 'k'"


def _stub() -> MagicMock:
    stub = MagicMock()
    stub.plugin_id = "plugins.core.commands"
    stub.api = MagicMock()
    stub.api.startup = True
    stub.api.side_effect = lambda name: lambda *a, **k: True
    stub.command_data = {}
    stub.commands_list = []
    stub.saved_command_counts = {}
    stub.saved_command_stats = {}
    return stub


def test_live_replace_carries_count_and_stats() -> None:
    stub = _stub()
    old = _make(_raiser)
    old.run("")
    stub.command_data[PID] = {"x": old}
    new = _make(lambda: True)
    CommandsPlugin.update_command(stub, PID, "x", new)
    assert new.count == 1
    assert new.stats is old.stats
    assert new.count_since_reload == 0


def test_unload_and_reload_restores_stats() -> None:
    stub = _stub()
    old = _make(_raiser)
    old.run("")
    expected = CommandStats(**vars(old.stats))
    stub.command_data[PID] = {"x": old}
    CommandsPlugin._api_remove_data_for_plugin(stub, PID)
    saved = stub.saved_command_stats[PID]["x"]
    assert isinstance(saved, dict)
    new = _make(lambda: True)
    CommandsPlugin.update_command(stub, PID, "x", new)
    assert new.stats == expected
    assert new.count == 1
    assert PID not in stub.saved_command_stats


def test_uninitialize_hook_saves_only_when_reloading() -> None:
    stub = _stub()
    stub.command_data[PID] = {"x": _make(lambda: True)}
    stub.is_reloading_f = False
    CommandsPlugin._phook_commands_save_on_reload(stub)
    assert stub.saved_command_counts == {}
    stub.is_reloading_f = True
    CommandsPlugin._phook_commands_save_on_reload(stub)
    assert stub.saved_command_counts == {PID: {"x": 0}}
    assert PID in stub.saved_command_stats


def test_detail_data_rows() -> None:
    stub = _stub()
    stub.api.time_format = "%Y"
    cmd = _make(_raiser)
    cmd.group = "Grp"
    rows = CommandsPlugin.command_detail_data(stub, cmd)
    assert [r["item"] for r in rows] == [
        "Plugin",
        "Group",
        "Function",
        "Calls (lifetime)",
        "Calls since reload",
        "Errors",
        "Last error",
        "Last error time",
        "Last run start",
        "Last run end",
    ]
    values = {r["item"]: r["value"] for r in rows}
    assert values["Plugin"] == PID
    assert values["Function"] == "_raiser"
    assert values["Last error"] == "None"
    assert values["Last run start"] == "Never"
    cmd.run("")
    values = {r["item"]: r["value"] for r in CommandsPlugin.command_detail_data(stub, cmd)}
    assert values["Calls (lifetime)"] == "1"
    assert values["Errors"] == "1"
    assert values["Last error"] == "ValueError: boom"
    assert values["Last run end"] == str(datetime.datetime.now(datetime.UTC).year)


def _detail_stub(argument: str) -> tuple[MagicMock, list[Any]]:
    stub = _stub()
    captured: list[Any] = []

    def table(title: str, data: Any, columns: Any) -> list[str]:
        captured.extend([title, data, columns])
        return ["table"]

    def api(name: str) -> Callable[..., Any]:
        if name.endswith("get.current.command.args"):
            return lambda: {"command": argument}
        return table

    stub.api.side_effect = api
    return stub, captured


def test_detail_command_found() -> None:
    stub, captured = _detail_stub("a.b.x")
    cmd = _make(lambda: True)
    cmd.full_cmd = "#bp.a.b.x"
    stub.find_command.return_value = (cmd, "", False, "", [])
    stub.command_detail_data.return_value = [{"item": "i", "value": "v"}]
    result = CommandsPlugin._command_detail(stub)
    assert result == (True, ["table"])
    assert captured[0] == "Command: #bp.a.b.x"
    assert captured[1] == [{"item": "i", "value": "v"}]


def test_detail_command_not_found() -> None:
    stub, _ = _detail_stub("nope")
    stub.find_command.return_value = (None, "", False, "", ["not found"])
    assert CommandsPlugin._command_detail(stub) == (True, ["not found"])


def test_detail_command_empty_argument() -> None:
    stub, _ = _detail_stub("")
    assert CommandsPlugin._command_detail(stub)[0] is False

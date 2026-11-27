"""`command.run.structured` runs one command by exact name and returns a structured reply (#845)."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs import argp
from bastproxy.libs.plugins.loader import PluginIdMatch
from bastproxy.plugins.core.commands import CommandResult
from bastproxy.plugins.core.commands.libs import _command
from bastproxy.plugins.core.commands.libs._command import MAX_ARGUMENT_LENGTH, CommandClass
from bastproxy.plugins.core.commands.plugin import _commands
from bastproxy.plugins.core.commands.plugin._commands import CALL_REASONS, CommandsPlugin

PLUGIN = "plugins.core.web"


@pytest.fixture(autouse=True)
def _patch_command_module(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_command, "API", MagicMock())
    monkeypatch.setattr(_command, "CmdArgsRecord", lambda owner, data, **kw: dict(data))


class Stub:
    """A commands plugin stand-in: real lookup methods, an api that allows only the lookup."""

    plugin_id = "plugins.core.commands"

    def __init__(self) -> None:
        self.command_data: dict[str, dict[str, CommandClass]] = {PLUGIN: {}}
        self.api_calls: list[str] = []

    def api(self, name: str) -> Any:
        self.api_calls.append(name)
        if name == "plugins.core.settings:setting.get":
            return lambda pid, key: "#bp"
        if name == "libs.plugins.loader:plugin.id.match":
            return self._match
        raise AssertionError(f"unexpected api {name}")

    @staticmethod
    def _match(plugin_id: str, active_only: bool = False) -> PluginIdMatch:
        if plugin_id == "core.web":
            return PluginIdMatch("plugins.core", PLUGIN)
        if plugin_id.startswith("core."):
            return PluginIdMatch("plugins.core", "")
        return PluginIdMatch()

    def find_command_split_command_string(self, command_str: str) -> Any:
        return CommandsPlugin.find_command_split_command_string(self, command_str)  # type: ignore[arg-type]

    def get_command_data_from_plugin(self, plugin_id: str, command: str) -> CommandClass | None:
        return self.command_data.get(plugin_id, {}).get(command)

    def _call_lookup(self, command: str) -> CommandClass | None:
        return CommandsPlugin._call_lookup(self, command)  # type: ignore[arg-type]

    def add(self, name: str, function: Any) -> None:
        parser = argp.ArgumentParser(add_help=False)
        parser.add_argument("-h", "--help", action="store_true")
        item = CommandClass(PLUGIN, name, function, parser)
        item.full_cmd = f"#bp.core.web.{name}"
        self.command_data[PLUGIN][name] = item


def call(stub: Stub, command: str, args: str = "") -> dict[str, Any]:
    reply: dict[str, Any] = CommandsPlugin._api_command_call(stub, command, args)
    return reply


def set_data(value: Any) -> bool:
    result: bool = CommandsPlugin._api_command_reply_data_set(MagicMock(), value)
    return result


@pytest.fixture
def stub() -> Stub:
    return Stub()


def test_an_exact_name_runs_and_returns_the_lines(stub: Stub) -> None:
    stub.add("status", lambda: CommandResult(True, ["one", "two"]))
    assert call(stub, "core.web.status") == {
        "ok": True,
        "reason": "",
        "lines": ["one", "two"],
        "data": None,
    }
    # only the lookup ran: nothing went to a client and no args-modify event was raised
    assert set(stub.api_calls) <= {
        "plugins.core.settings:setting.get",
        "libs.plugins.loader:plugin.id.match",
    }


@pytest.mark.parametrize("name", ["#bp.core.web.status", "plugins.core.web.status"])
def test_the_prefix_forms_resolve(stub: Stub, name: str) -> None:
    stub.add("status", lambda: CommandResult(True, ["ok"]))
    assert call(stub, name)["ok"] is True


@pytest.mark.parametrize(
    "name",
    [
        "core.web.stat",  # abbreviated
        "core.web.nothing",
        "core.web",  # no command: no default is run
        "core.web.",
        "core.we.status",
        "core.status",
        "nope.web.status",
        "core.web.status extra",
        "core.web.status.more",
        "",
    ],
)
def test_unknown_names_run_nothing(stub: Stub, name: str) -> None:
    ran: list[int] = []

    def fn() -> CommandResult:
        ran.append(1)
        return CommandResult(True)

    stub.add("status", fn)
    reply = call(stub, name)
    assert (reply["ok"], reply["reason"], reply["lines"], reply["data"]) == (
        False,
        "unknown_command",
        [],
        None,
    )
    assert ran == []


def test_a_parse_error_and_long_arguments_are_bad_arguments(stub: Stub) -> None:
    stub.add("status", lambda: CommandResult(True))
    assert call(stub, "core.web.status", '"abc')["reason"] == "bad_arguments"
    long = call(stub, "core.web.status", "x" * (MAX_ARGUMENT_LENGTH + 1))
    assert (long["ok"], long["reason"]) == (False, "bad_arguments")
    assert long["lines"]


def test_a_failed_result_is_failed(stub: Stub) -> None:
    stub.add("status", lambda: CommandResult(False, ["no luck"]))
    reply = call(stub, "core.web.status")
    assert (reply["ok"], reply["reason"]) == (False, "failed")
    assert reply["lines"][0] == "no luck"


def test_a_raise_is_error(stub: Stub) -> None:
    def boom() -> CommandResult:
        raise ValueError("boom")

    stub.add("status", boom)
    reply = call(stub, "core.web.status")
    assert (reply["ok"], reply["reason"]) == (False, "error")


def test_a_wrong_return_type_is_error(stub: Stub) -> None:
    stub.add("status", lambda: None)
    assert call(stub, "core.web.status")["reason"] == "error"


def test_help_is_ok(stub: Stub) -> None:
    stub.add("status", lambda: CommandResult(True))
    reply = call(stub, "core.web.status", "-h")
    assert (reply["ok"], reply["reason"]) == (True, "")
    assert reply["lines"]


def test_reply_data_is_returned(stub: Stub) -> None:
    def fn() -> CommandResult:
        assert set_data({"a": [1, 2]}) is True
        return CommandResult(True, ["x"])

    stub.add("status", fn)
    assert call(stub, "core.web.status")["data"] == {"a": [1, 2]}


def test_reply_data_survives_a_failed_command(stub: Stub) -> None:
    def fn() -> CommandResult:
        set_data(5)
        return CommandResult(False, ["x"])

    stub.add("status", fn)
    assert call(stub, "core.web.status")["data"] == 5


def test_set_outside_a_call_is_false_and_unserializable_is_refused(stub: Stub) -> None:
    assert set_data({"a": 1}) is False
    seen: list[bool] = []

    def fn() -> CommandResult:
        seen.append(set_data(object()))
        return CommandResult(True)

    stub.add("status", fn)
    assert call(stub, "core.web.status")["data"] is None
    assert seen == [False]
    assert _commands._reply_data.get() is None


def test_nested_boxes_restore(stub: Stub) -> None:
    def inner() -> CommandResult:
        set_data("inner")
        return CommandResult(True)

    def outer() -> CommandResult:
        set_data("outer-before")
        assert call(stub, "core.web.inner")["data"] == "inner"
        set_data("outer-after")
        return CommandResult(True)

    stub.add("inner", inner)
    stub.add("outer", outer)
    assert call(stub, "core.web.outer")["data"] == "outer-after"


def test_the_reasons_are_documented() -> None:
    assert CALL_REASONS == ("unknown_command", "bad_arguments", "failed", "error")

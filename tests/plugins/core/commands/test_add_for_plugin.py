"""Tests for command.add.for.plugin: commands under another plugin's name (#834)."""

# Standard Library
import logging
from collections.abc import Callable
from types import MethodType
from typing import Any
from unittest.mock import MagicMock

# 3rd Party
import pytest

# Project
from bastproxy.plugins.core.commands import CommandResult
from bastproxy.plugins.core.commands.libs import _command
from bastproxy.plugins.core.commands.plugin._commands import CommandsPlugin

HOST = "plugins.client.mapper"
OWNER = "plugins.aardwolf.mapper"
OTHER = "plugins.other.thing"


@pytest.fixture(autouse=True)
def _patch_command_module(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_command, "API", MagicMock())
    monkeypatch.setattr(_command, "CmdArgsRecord", lambda owner, data, **kw: dict(data))


class _Data:
    def __init__(self, autoadd: bool = True, kwargs: dict[str, Any] | None = None) -> None:
        self.command: dict[str, Any] = {"autoadd": autoadd, "kwargs": kwargs or {}}
        self.argparse: dict[str, Any] = {
            "kwargs": {"add_help": False, "description": "adds a portal"}
        }
        self.arguments: list[Any] = []


class _Plugin:
    def __init__(self, plugin_id: str, accepts: bool = False) -> None:
        self.plugin_id = plugin_id
        self.name = plugin_id
        self.accepts_command_extensions_f = accepts
        self.calls: list[str] = []


def _make(owner: _Plugin, fname: str, group: str | None = None) -> MethodType:
    def _func(self: _Plugin) -> CommandResult:
        self.calls.append(fname)
        return CommandResult(True, "done")

    _func.__name__ = fname
    kwargs = {"group": group} if group else {}
    _func.command_data = _Data(kwargs=kwargs)  # type: ignore[attr-defined]
    return MethodType(_func, owner)


class _Api:
    startup = False

    def __init__(self, plugins: dict[str, Any]) -> None:
        self.plugins = plugins

    def __call__(self, name: str) -> Callable[..., Any]:
        if name == "plugins.core.commands:command.format":
            return lambda plugin_id, command: f"#bp.{plugin_id}.{command}"
        if name == "libs.plugins.loader:plugin.instance.get":
            return lambda plugin_id: self.plugins.get(plugin_id)
        if name == "libs.plugins.loader:plugin.id.is.valid":
            return lambda plugin_id: plugin_id in self.plugins
        if name == "plugins.core.settings:setting.get":
            return lambda plugin_id, setting: "@C"
        if name == "plugins.core.settings:setting.list":
            return lambda plugin_id: {}
        if name == "plugins.core.commands:output.header.format":
            return lambda title: [title]
        raise AssertionError(name)


class _Fake:
    plugin_id = "plugins.core.commands"

    def __init__(self, plugins: dict[str, Any]) -> None:
        self.api = _Api(plugins)
        self.commands_list: list[str] = []
        self.command_data: dict[str, dict[str, Any]] = {}
        self.command_extensions: dict[str, dict[str, tuple[str, Callable[..., Any]]]] = {}
        self.saved_command_counts: dict[str, dict[str, int]] = {}
        self.saved_command_stats: dict[str, dict[str, dict[str, Any]]] = {}

    def update_command(self, plugin_id: str, name: str, command: Any) -> bool:
        return CommandsPlugin.update_command(self, plugin_id, name, command)  # type: ignore[arg-type]

    def _build_command(self, *args: Any, **kwargs: Any) -> Any:
        return CommandsPlugin._build_command(self, *args, **kwargs)  # type: ignore[arg-type]

    def _add_extension(self, host_id: str, func: Callable[..., Any]) -> bool:
        return CommandsPlugin._add_extension(self, host_id, func)  # type: ignore[arg-type]

    def format_command_list(self, commands: list[Any]) -> list[str]:
        return CommandsPlugin.format_command_list(self, commands)  # type: ignore[arg-type]

    def add(self, host_id: str, func: Callable[..., Any]) -> bool:
        added: bool = CommandsPlugin._api_command_add_for_plugin(self, host_id, func)
        return added


def _setup(accepts: bool = True) -> tuple[_Fake, _Plugin, _Plugin]:
    host = _Plugin(HOST, accepts)
    owner = _Plugin(OWNER)
    return _Fake({HOST: host, OWNER: owner, OTHER: _Plugin(OTHER)}), host, owner


def test_registers_under_the_host() -> None:
    fake, _, owner = _setup()
    assert fake.add(HOST, _make(owner, "_command_portal", group="portals"))
    command = fake.command_data[HOST]["portal"]
    assert command.plugin_id == HOST
    assert command.owner_id == OWNER
    assert command.group == OWNER
    assert command.arg_parser.prog == f"#bp.{HOST}.portal"
    assert command.arg_parser.epilog == "Added by aardwolf.mapper"
    assert f"{HOST}.portal" in fake.commands_list
    assert fake.command_extensions[HOST]["portal"][0] == OWNER


def test_forwards_to_the_owner_method() -> None:
    fake, _, owner = _setup()
    fake.add(HOST, _make(owner, "_command_portal"))
    result = fake.command_data[HOST]["portal"].run("")
    assert result.success
    assert owner.calls == ["_command_portal"]


@pytest.mark.parametrize("case", ["no_opt_in", "not_loaded", "self", "not_command"])
def test_refusals(case: str, caplog: pytest.LogCaptureFixture) -> None:
    fake, _, owner = _setup(accepts=case != "no_opt_in")
    func = _make(owner, "_command_portal")
    host_id = HOST
    if case == "not_loaded":
        host_id = "plugins.missing"
    elif case == "self":
        host_id = OWNER
    elif case == "not_command":
        func = _make(owner, "plain")
    with caplog.at_level(logging.WARNING):
        assert not fake.add(host_id, func)
    assert fake.command_data == {}
    assert fake.command_extensions == {}
    assert caplog.records


def test_clash_with_another_owner_is_refused(caplog: pytest.LogCaptureFixture) -> None:
    fake, _, owner = _setup()
    other = _Plugin(OTHER)
    assert fake.add(HOST, _make(owner, "_command_portal"))
    with caplog.at_level(logging.WARNING):
        assert not fake.add(HOST, _make(other, "_command_portal"))
    assert fake.command_data[HOST]["portal"].owner_id == OWNER
    assert any(OWNER in r.getMessage() and OTHER in r.getMessage() for r in caplog.records)


def test_clash_with_a_host_command_is_refused() -> None:
    fake, host, owner = _setup()
    built = fake._build_command(_make(host, "_command_portal"))
    fake.update_command(HOST, "portal", built[2])
    assert not fake.add(HOST, _make(owner, "_command_portal"))
    assert fake.command_data[HOST]["portal"].owner_id == HOST


def test_same_owner_replaces() -> None:
    fake, _, owner = _setup()
    fake.add(HOST, _make(owner, "_command_portal"))
    fake.command_data[HOST]["portal"].count = 4
    assert fake.add(HOST, _make(owner, "_command_portal"))
    assert fake.command_data[HOST]["portal"].count == 4
    assert fake.commands_list.count(f"{HOST}.portal") == 1


def test_owner_unload_removes_and_keeps_counts() -> None:
    fake, host, owner = _setup()
    own = fake._build_command(_make(host, "_command_walk"))
    fake.update_command(HOST, "walk", own[2])
    fake.add(HOST, _make(owner, "_command_portal"))
    fake.command_data[HOST]["portal"].count = 3
    CommandsPlugin.remove_extensions_for_owner(fake, OWNER)  # type: ignore[arg-type]
    assert list(fake.command_data[HOST]) == ["walk"]
    assert fake.command_extensions == {}
    assert f"{HOST}.portal" not in fake.commands_list
    assert fake.saved_command_counts[HOST] == {"portal": 3}
    # the owner reloads and registers again: the count comes back
    fake.add(HOST, _make(owner, "_command_portal"))
    assert fake.command_data[HOST]["portal"].count == 3


def test_host_reload_restores_extensions() -> None:
    fake, _, owner = _setup()
    fake.add(HOST, _make(owner, "_command_portal"))
    fake.command_data[HOST]["portal"].count = 5
    # what command.remove.for.plugin does for the host
    removed = fake.command_data.pop(HOST)
    fake.commands_list = []
    CommandsPlugin._save_command_data(fake, HOST, removed)  # type: ignore[arg-type]
    CommandsPlugin.add_extensions_for_plugin(fake, HOST)  # type: ignore[arg-type]
    assert fake.command_data[HOST]["portal"].count == 5
    assert f"{HOST}.portal" in fake.commands_list


def test_host_reload_host_command_wins() -> None:
    fake, host, owner = _setup()
    fake.add(HOST, _make(owner, "_command_portal"))
    fake.command_data.pop(HOST)
    built = fake._build_command(_make(host, "_command_portal"))
    fake.update_command(HOST, "portal", built[2])
    CommandsPlugin.add_extensions_for_plugin(fake, HOST)  # type: ignore[arg-type]
    assert fake.command_data[HOST]["portal"].owner_id == HOST
    assert fake.command_extensions == {}


def test_detail_rows_show_the_owner_only_for_extensions() -> None:
    fake, host, owner = _setup()
    fake.api.time_format = "%Y"  # type: ignore[attr-defined]
    fake.add(HOST, _make(owner, "_command_portal"))
    own = fake._build_command(_make(host, "_command_walk"))[2]
    rows = CommandsPlugin.command_detail_data(fake, fake.command_data[HOST]["portal"])  # type: ignore[arg-type]
    assert {"item": "Owner", "value": OWNER} in rows
    rows = CommandsPlugin.command_detail_data(fake, own)  # type: ignore[arg-type]
    assert all(row["item"] != "Owner" for row in rows)


def test_listing_shows_the_owner_section() -> None:
    fake, host, owner = _setup()
    fake.update_command(HOST, "walk", fake._build_command(_make(host, "_command_walk"))[2])
    fake.add(HOST, _make(owner, "_command_portal", group="portals"))
    lines = CommandsPlugin._api_command_list_formatted(fake, HOST)
    start = next(i for i, line in enumerate(lines) if "aardwolf.mapper" in line)
    assert lines[start].startswith("@C-----")
    assert "portal" in lines[start + 1]
    assert "walk" not in lines[start + 1]

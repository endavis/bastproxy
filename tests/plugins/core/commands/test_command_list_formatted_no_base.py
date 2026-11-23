"""command.list.formatted must not need a Base-group command (#393)."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins.core.commands.plugin._commands import CommandsPlugin

PID = "plugins.core.commands"
TARGET = "plugins.audit.badfmt"


def _command(name: str, group: str) -> Any:
    return SimpleNamespace(
        name=name,
        group=group,
        arg_parser=SimpleNamespace(description=f"{name} description"),
    )


def _stub(command_data: dict[str, Any], settings: dict[str, Any] | None = None) -> MagicMock:
    stub = MagicMock()
    stub.plugin_id = PID
    stub.command_data = command_data
    stub.format_command_list = lambda cl: CommandsPlugin.format_command_list(stub, cl)

    def api(name: str) -> Any:
        if name == "libs.plugins.loader:plugin.id.is.valid":
            return lambda _pid: True
        if name == "plugins.core.settings:setting.get":
            return lambda _pid, _setting: "@w"
        if name == "plugins.core.settings:setting.list":
            return lambda _pid: settings or {}
        if name == f"{PID}:output.header.format":
            return lambda title: [f"HEADER {title}"]
        raise AssertionError(name)

    stub.api = api
    return stub


def test_plugin_with_only_non_base_group() -> None:
    stub = _stub({TARGET: {"foo": _command("foo", "Other")}})

    lines = CommandsPlugin._api_command_list_formatted(stub, TARGET)

    text = "\n".join(lines)
    assert "HEADER" in text
    assert "foo" in text
    assert "Base" in text


def test_plugin_with_empty_command_entry() -> None:
    stub = _stub({TARGET: {}})

    lines = CommandsPlugin._api_command_list_formatted(stub, TARGET)

    assert lines[0].startswith("HEADER")
    assert not any("description" in line for line in lines)


def test_base_group_still_listed() -> None:
    stub = _stub({TARGET: {"set": _command("set", "Base")}}, {"opt": SimpleNamespace(hidden=False)})

    text = "\n".join(CommandsPlugin._api_command_list_formatted(stub, TARGET))

    assert "set description" in text


def test_set_hidden_when_plugin_has_no_settings() -> None:
    stub = _stub({TARGET: {"set": _command("set", "Base"), "foo": _command("foo", "Base")}})

    text = "\n".join(CommandsPlugin._api_command_list_formatted(stub, TARGET))

    assert "set description" not in text
    assert "foo description" in text
    assert "Base" in text


def test_set_hidden_when_plugin_has_only_hidden_settings() -> None:
    """Every plugin has a hidden `_version` setting; it does not count."""
    stub = _stub(
        {TARGET: {"set": _command("set", "Base"), "foo": _command("foo", "Base")}},
        {"_version": SimpleNamespace(hidden=True)},
    )

    text = "\n".join(CommandsPlugin._api_command_list_formatted(stub, TARGET))

    assert "set description" not in text
    assert "foo description" in text


def test_set_listed_when_plugin_has_settings() -> None:
    stub = _stub(
        {TARGET: {"set": _command("set", "Base"), "foo": _command("foo", "Base")}},
        {"opt": SimpleNamespace(hidden=False)},
    )

    text = "\n".join(CommandsPlugin._api_command_list_formatted(stub, TARGET))

    assert "set description" in text
    assert "foo description" in text


def test_set_in_non_base_group_not_hidden_without_settings() -> None:
    stub = _stub({TARGET: {"set": _command("set", "Other")}})

    text = "\n".join(CommandsPlugin._api_command_list_formatted(stub, TARGET))

    assert "set description" in text

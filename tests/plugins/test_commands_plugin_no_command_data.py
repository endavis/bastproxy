"""A valid plugin with no command data must not raise KeyError (#392)."""

from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins.core.commands.plugin._commands import CommandsPlugin

PID = "plugins.debug.api"


def _stub() -> MagicMock:
    """Build a plugin stub whose command_data has no entry for PID."""

    def api(name: str) -> Any:
        if name.endswith("plugin.id.is.valid"):
            return lambda plugin_id: True
        if name.endswith("setting.get"):
            return lambda plugin_id, key: "@C"
        if name.endswith("output.header.format"):
            return lambda text: [text]
        if name.endswith("current.args.get"):
            return lambda: {"command": "", "plugin": PID}
        raise AssertionError(name)

    stub = MagicMock()
    stub.plugin_id = "plugins.core.commands"
    stub.command_data = {}
    stub.api = api
    return stub


def test_command_data_get_returns_empty() -> None:
    """The command.data.get API returns an empty dict."""
    assert CommandsPlugin._api_command_data_get(_stub(), PID) == {}


def test_get_command_data_from_plugin_returns_none() -> None:
    """Looking up a command in a plugin with no data returns None."""
    assert CommandsPlugin.get_command_data_from_plugin(_stub(), PID, "x") is None


def test_command_list_formatted_does_not_look_up_missing_plugin() -> None:
    """Formatting the list does not raise KeyError for the plugin id.

    A later, separate defect (#393) may raise KeyError("Base") for an empty
    plugin; only the plugin-id lookup is under test here.
    """
    try:
        result = CommandsPlugin._api_command_list_formatted(_stub(), PID)
    except KeyError as err:
        assert err.args[0] != PID
    else:
        assert isinstance(result, list)


def test_command_list_reports_no_commands() -> None:
    """The list command says there are no commands in the plugin."""
    result = CommandsPlugin._command_list(_stub())
    assert result == (True, [f"There are no commands in plugin {PID}"])

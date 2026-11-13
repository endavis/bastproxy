"""Tests for the pluginm reload command (#220)."""

from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins.core.pluginm.plugin._pluginm import PluginManager

PLUGIN_ID = "plugins.test.beta"


def _stub(loaded: bool) -> tuple[MagicMock, dict[str, MagicMock]]:
    funcs: dict[str, MagicMock] = {
        "plugins.core.commands:command.current.args.get": MagicMock(
            return_value={"plugin": PLUGIN_ID}
        ),
        "libs.plugins.loader:plugin.id.is.valid": MagicMock(return_value=True),
        "libs.plugins.loader:plugin.is.loaded": MagicMock(return_value=loaded),
        f"{PLUGIN_ID}:plugin.reloading.set": MagicMock(),
        "libs.plugins.loader:plugin.reload": MagicMock(return_value=True),
        "plugins.core.settings:setting.get": MagicMock(return_value=[]),
        "plugins.core.settings:setting.set": MagicMock(),
    }
    stub = MagicMock()

    def api(name: str) -> Any:
        return funcs[name]

    stub.api = api
    return stub, funcs


def test_reload_unloaded_plugin_returns_message_and_does_nothing() -> None:
    """A valid but unloaded plugin id is refused before any state changes."""
    stub, funcs = _stub(loaded=False)
    result = PluginManager._command_reload(stub)
    ok = result.success
    msgs = result.message
    assert ok is True
    assert msgs == [f"{PLUGIN_ID} is not loaded; use #bp.core.pluginm.load {PLUGIN_ID}"]
    funcs[f"{PLUGIN_ID}:plugin.reloading.set"].assert_not_called()
    funcs["libs.plugins.loader:plugin.reload"].assert_not_called()
    funcs["plugins.core.settings:setting.set"].assert_not_called()


def test_reload_loaded_plugin_still_reloads() -> None:
    """A loaded plugin is flagged as reloading and reloaded."""
    stub, funcs = _stub(loaded=True)
    result = PluginManager._command_reload(stub)
    ok = result.success
    msgs = result.message
    assert ok is True
    assert msgs == [f"{PLUGIN_ID} reloaded"]
    funcs[f"{PLUGIN_ID}:plugin.reloading.set"].assert_called_once_with()
    funcs["libs.plugins.loader:plugin.reload"].assert_called_once_with(PLUGIN_ID)

"""Tests for the dead and wrong calls fixed in #128 (PS-9)."""

from typing import Any
from unittest.mock import MagicMock

from bastproxy.libs.plugins.loader import PluginLoader
from bastproxy.plugins._baseplugin._base import Plugin
from bastproxy.plugins.core.triggers.plugin._triggers import TriggersPlugin


def _base_stub(mud_connected: bool, character_active: bool) -> tuple[MagicMock, MagicMock]:
    """Return a stub plugin and the register.to.event mock."""
    register = MagicMock()

    def api(name: str) -> Any:
        if name == "plugins.core.proxy:is.mud.connected":
            return lambda: mud_connected
        if name == "libs.api:is.character.active":
            return lambda: character_active
        if name == "libs.api:add.apis.for.object":
            return MagicMock()
        if name == "plugins.core.events:register.to.event":
            return register
        return MagicMock()

    stub = MagicMock()
    stub.plugin_id = "plugins.test"
    stub.api = MagicMock(side_effect=api)
    stub.api.startup = True
    return stub, register


def test_post_initialize_calls_is_mud_connected() -> None:
    """A disconnected mud registers to the event even if the character is active."""
    stub, register = _base_stub(mud_connected=False, character_active=True)
    Plugin._phook_base_post_initialize_setup(stub)
    register.assert_called_once()
    stub._eventcb_baseplugin_after_character_is_active.assert_not_called()


def test_post_initialize_runs_callback_when_connected_and_active() -> None:
    """A connected mud with an active character runs the callback directly."""
    stub, register = _base_stub(mud_connected=True, character_active=True)
    Plugin._phook_base_post_initialize_setup(stub)
    stub._eventcb_baseplugin_after_character_is_active.assert_called_once()
    register.assert_not_called()


def test_trigger_remove_uses_existing_owner_api_name() -> None:
    """With no owner_id, the owner is found through `libs.api:get.caller.owner`."""
    names: list[str] = []

    def api(name: str) -> Any:
        names.append(name)
        return lambda **_kwargs: None

    stub = MagicMock()
    stub.plugin_id = "plugins.core.triggers"
    stub.api = MagicMock(side_effect=api)
    stub.api.startup = True
    assert TriggersPlugin._api_trigger_remove(stub, "trig") is False
    assert names == ["libs.api:get.caller.owner"]


def test_update_all_plugin_information_result_not_branched_on() -> None:
    """Callers just call it: no log, no exit, even if it returned something truthy."""
    loader = MagicMock()
    loader.update_all_plugin_information.return_value = ["conflict"]
    loader.plugins_info = {}
    loader.api = lambda _name: lambda *_a, **_k: []
    PluginLoader._load_core_and_client_plugins_on_startup(loader)
    loader.update_all_plugin_information.assert_called_once_with()
    PluginLoader._api_get_not_loaded_plugins(loader)
    assert loader.update_all_plugin_information.call_count == 2

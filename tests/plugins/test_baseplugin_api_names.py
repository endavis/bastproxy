"""BasePlugin registers its APIs under the ADR-0004 names, with no aliases (#163)."""

import pytest

from bastproxy.plugins._baseplugin import BasePlugin

# old API name -> (new API name, new method name)
RENAMES: dict[str, tuple[str, str]] = {
    "get.data.directory": ("data.directory.get", "_api_data_directory_get"),
    "set.reload": ("plugin.reloading.set", "_api_plugin_reloading_set"),
    "get.plugin.hooks": ("plugin.hook.list", "_api_plugin_hook_list"),
    "dump": ("plugin.dump", "_api_plugin_dump"),
    "save.state": ("plugin.state.save", "_api_plugin_state_save"),
    "reset": ("plugin.reset", "_api_plugin_reset"),
}


def _registered_names() -> dict[str, str]:
    """Map each API name BasePlugin declares to the method that declares it."""
    names: dict[str, str] = {}
    for attr in dir(BasePlugin):
        api = getattr(getattr(BasePlugin, attr), "api", None)
        if isinstance(api, dict):
            names[api["name"]] = attr
    return names


@pytest.mark.parametrize(("old", "new_and_method"), RENAMES.items())
def test_new_name_registered_and_old_name_gone(old: str, new_and_method: tuple[str, str]) -> None:
    new, method = new_and_method
    registered = _registered_names()
    assert registered.get(new) == method
    assert old not in registered

"""Tests for loading several plugins or a package with one load command (#724)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.plugins.core.pluginm.plugin._pluginm import PluginManager, _package_matches

LOADER = "libs.plugins.loader"
PM_ID = "plugins.core.pluginm"
AARD = ["plugins.aardwolf.a", "plugins.aardwolf.b", "plugins.aardwolf.c"]


def _stub(
    arg: Any,
    not_loaded: list[str],
    loaded: set[str] | None = None,
    bad: set[str] | None = None,
) -> tuple[MagicMock, list[str], MagicMock]:
    store: list[str] = []
    bad = bad or set()
    load = MagicMock(
        side_effect=lambda pids: {
            "loaded_plugins": [p for p in pids if p not in bad],
            "bad_plugins": [p for p in pids if p in bad],
        }
    )
    funcs: dict[str, Any] = {
        "plugins.core.commands:command.current.args.get": lambda: {"plugin": arg},
        f"{LOADER}:plugin.is.loaded": lambda pid: pid in (loaded or set()),
        f"{LOADER}:plugin.list.not.loaded": lambda: not_loaded,
        f"{LOADER}:plugin.load": load,
        "plugins.core.settings:setting.get": lambda *_a: store,
        "plugins.core.settings:setting.set": lambda _o, _n, v: store.__setitem__(slice(None), v),
    }
    stub = MagicMock()
    stub.plugin_id = PM_ID
    stub.api = lambda name: funcs[name]
    return stub, store, load


def test_two_plugins_load_in_one_call() -> None:
    stub, store, load = _stub(
        ["aardwolf.connect", "statdb"], ["plugins.aardwolf.connect", "plugins.statdb"]
    )
    result = PluginManager._command_load(stub)
    load.assert_called_once_with(["plugins.aardwolf.connect", "plugins.statdb"])
    assert store == ["plugins.aardwolf.connect", "plugins.statdb"]
    assert result.success


@pytest.mark.parametrize("name", ["aardwolf", "plugins.aardwolf"])
def test_package_loads_all_its_plugins(name: str) -> None:
    stub, _store, load = _stub([name], [*AARD, "plugins.other.x"])
    PluginManager._command_load(stub)
    load.assert_called_once_with(AARD)


def test_partial_name_not_found() -> None:
    stub, _store, load = _stub(["aard"], list(AARD))
    result = PluginManager._command_load(stub)
    assert result.message == ["Plugin plugins.aard not found"]
    assert not result.success
    load.assert_not_called()


def test_mixed_names() -> None:
    stub, _store, load = _stub(["up", "new", "nope"], ["plugins.new"], loaded={"plugins.up"})
    result = PluginManager._command_load(stub)
    load.assert_called_once_with(["plugins.new"])
    assert "Loaded the following plugins" in result.message
    assert "Plugin plugins.up is already loaded" in result.message
    assert "Plugin plugins.nope not found" in result.message
    assert result.success


def test_package_with_some_loaded_loads_only_the_rest() -> None:
    stub, _store, load = _stub(["aardwolf"], AARD[1:], loaded={AARD[0]})
    PluginManager._command_load(stub)
    load.assert_called_once_with(AARD[1:])


def test_failed_plugin_reported_and_others_saved() -> None:
    stub, store, _load = _stub(["aardwolf"], list(AARD), bad={AARD[1]})
    result = PluginManager._command_load(stub)
    assert "Failed to load the following plugins, please check the logs" in result.message
    assert "   " + AARD[1] in result.message
    assert store == [AARD[0], AARD[2]]


def test_repeated_names_load_once() -> None:
    stub, _store, load = _stub(["aardwolf", "aardwolf.a"], list(AARD))
    PluginManager._command_load(stub)
    load.assert_called_once_with(AARD)


@pytest.mark.parametrize("arg", [["lc.livecheck"], "lc.livecheck"])
def test_single_name_messages_unchanged(arg: Any) -> None:
    stub, _store, _load = _stub(arg, ["plugins.lc.livecheck"])
    result = PluginManager._command_load(stub)
    assert result.message == ["Loaded the following plugins", "   plugins.lc.livecheck"]
    assert result.success

    stub, _store, load = _stub(arg, [], loaded={"plugins.lc.livecheck"})
    result = PluginManager._command_load(stub)
    assert result.message == ["Plugin plugins.lc.livecheck is already loaded"]
    assert result.success
    load.assert_not_called()

    stub, _store, _load = _stub(arg, [])
    result = PluginManager._command_load(stub)
    assert result.message == ["Plugin plugins.lc.livecheck not found"]
    assert not result.success


def test_empty_list_specifies_nothing() -> None:
    stub, _store, _load = _stub([], [])
    result = PluginManager._command_load(stub)
    assert result.message == ["No plugin specified"]
    assert not result.success


def test_package_matches_whole_parts_only() -> None:
    ids = [*AARD, "plugins.aardwolfx.y", "plugins.aardwolf"]
    assert _package_matches("plugins.aardwolf", ids) == AARD
    assert _package_matches("plugins.aard", ids) == []
    assert _package_matches("plugins.aardwolf.a", ids) == []

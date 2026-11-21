"""Tests for keeping pluginstoload free of repeated plugins (#665)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins.core.pluginm.plugin._pluginm import PluginManager

LOADER = "libs.plugins.loader"
PM_ID = "plugins.core.pluginm"


def _load_stub(
    arg: str, loaded: list[str], initial: list[str]
) -> tuple[MagicMock, list[str], MagicMock]:
    store = list(initial)
    set_mock = MagicMock(side_effect=lambda _o, _n, value: store.__setitem__(slice(None), value))
    funcs: dict[str, Any] = {
        "plugins.core.commands:command.current.args.get": lambda: {"plugin": arg},
        f"{LOADER}:plugin.is.loaded": lambda _pid: False,
        f"{LOADER}:plugin.list.not.loaded": lambda: [arg],
        f"{LOADER}:plugin.load": lambda _pids: {"loaded_plugins": loaded, "bad_plugins": []},
        "plugins.core.settings:setting.get": lambda *_a: store,
        "plugins.core.settings:setting.set": set_mock,
        "plugins.core.events:event.raise": MagicMock(),
    }
    stub = MagicMock()
    stub.plugin_id = PM_ID
    stub.api = lambda name: funcs[name]
    return stub, store, set_mock


def test_load_of_plugin_already_in_list_leaves_list_unchanged() -> None:
    stub, store, set_mock = _load_stub("plugins.a", ["plugins.a"], ["plugins.a", "plugins.b"])
    PluginManager._command_load(stub)
    assert store == ["plugins.a", "plugins.b"]
    set_mock.assert_not_called()


def test_load_with_dependency_already_in_list_keeps_one_copy_in_order() -> None:
    stub, store, _set = _load_stub("plugins.a", ["plugins.dep", "plugins.a"], ["plugins.dep"])
    PluginManager._command_load(stub)
    assert store == ["plugins.dep", "plugins.a"]


def test_load_appends_new_plugins() -> None:
    stub, store, _set = _load_stub("plugins.a", ["plugins.dep", "plugins.a"], ["plugins.x"])
    PluginManager._command_load(stub)
    assert store == ["plugins.x", "plugins.dep", "plugins.a"]


def _startup_stub(
    initial: list[str],
    *,
    missing: tuple[str, ...] = (),
    loaded: tuple[str, ...] = (),
    dev: tuple[str, ...] = (),
) -> tuple[MagicMock, list[str], MagicMock, MagicMock]:
    store = list(initial)
    set_mock = MagicMock(side_effect=lambda _o, _n, value: store.__setitem__(slice(None), value))
    load_mock = MagicMock()
    funcs: dict[str, Any] = {
        "plugins.core.settings:setting.get": lambda *_a: store,
        "plugins.core.settings:setting.set": set_mock,
        f"{LOADER}:plugin.exists": lambda pid: pid not in missing,
        f"{LOADER}:plugin.is.loaded": lambda pid: pid in loaded,
        f"{LOADER}:plugin.info.get": lambda pid: MagicMock(is_dev=pid in dev),
        f"{LOADER}:plugin.load": load_mock,
    }
    stub = MagicMock()
    stub.plugin_id = PM_ID
    stub.api = lambda name: funcs[name]
    return stub, store, set_mock, load_mock


def test_startup_drops_repeats() -> None:
    stub, store, _set, load = _startup_stub(["plugins.a", "plugins.b", "plugins.a"])
    PluginManager._load_other_plugins_after_core_and_client_plugins(stub)
    assert store == ["plugins.a", "plugins.b"]
    load.assert_called_once_with(["plugins.a", "plugins.b"])


def test_startup_still_drops_missing_loaded_and_dev_with_repeats() -> None:
    stub, store, _set, load = _startup_stub(
        [
            "plugins.gone",
            "plugins.a",
            "plugins.up",
            "plugins.dev",
            "plugins.a",
            "plugins.gone",
            "plugins.b",
            "plugins.up",
        ],
        missing=("plugins.gone",),
        loaded=("plugins.up",),
        dev=("plugins.dev",),
    )
    PluginManager._load_other_plugins_after_core_and_client_plugins(stub)
    assert store == ["plugins.a", "plugins.b"]
    load.assert_called_once_with(["plugins.a", "plugins.b"])


def test_startup_with_nothing_to_load_does_not_load() -> None:
    stub, store, _set, load = _startup_stub(["plugins.up", "plugins.up"], loaded=("plugins.up",))
    PluginManager._load_other_plugins_after_core_and_client_plugins(stub)
    assert store == []
    load.assert_not_called()

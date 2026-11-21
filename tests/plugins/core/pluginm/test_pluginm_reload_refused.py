"""Tests for a refused plugin reload keeping its pluginstoload entry (#662)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from bastproxy.libs.plugins.loader import PluginLoader
from bastproxy.libs.plugins.plugininfo import PluginInfo
from bastproxy.plugins.core.pluginm.plugin._pluginm import PluginManager

PLUGIN_ID = "plugins.test.beta"
PM_ID = "plugins.core.pluginm"


def _command_stub(
    *, reload_result: bool, loaded_after: bool, initial: list[str]
) -> tuple[MagicMock, dict[str, MagicMock], list[str]]:
    store = list(initial)
    funcs: dict[str, MagicMock] = {
        "plugins.core.commands:command.current.args.get": MagicMock(
            return_value={"plugin": PLUGIN_ID}
        ),
        "libs.plugins.loader:plugin.id.is.valid": MagicMock(return_value=True),
        "libs.plugins.loader:plugin.is.loaded": MagicMock(side_effect=[True, loaded_after]),
        "libs.plugins.loader:plugin.reload": MagicMock(return_value=reload_result),
        "plugins.core.settings:setting.get": MagicMock(side_effect=lambda *_a: store),
        "plugins.core.settings:setting.set": MagicMock(
            side_effect=lambda _o, _n, value: store.__setitem__(slice(None), value)
        ),
    }
    stub = MagicMock()
    stub.plugin_id = PM_ID

    def api(name: str) -> Any:
        return funcs[name]

    stub.api = api
    return stub, funcs, store


def test_refused_reload_keeps_entry_while_loaded() -> None:
    """A refused reload leaves the still-loaded plugin in pluginstoload."""
    stub, funcs, store = _command_stub(reload_result=False, loaded_after=True, initial=[PLUGIN_ID])
    result = PluginManager._command_reload(stub)
    assert result.success is False
    assert "still loaded" in result.message[0]
    assert store == [PLUGIN_ID]
    funcs["plugins.core.settings:setting.set"].assert_not_called()


def test_failed_load_after_unload_removes_entry() -> None:
    """A plugin that was unloaded and did not load again leaves pluginstoload."""
    stub, _funcs, store = _command_stub(
        reload_result=False, loaded_after=False, initial=[PLUGIN_ID, "plugins.other"]
    )
    result = PluginManager._command_reload(stub)
    assert result.success is False
    assert "unloaded but not loaded again" in result.message[0]
    assert store == ["plugins.other"]


def test_successful_reload_adds_entry_once() -> None:
    """A successful reload appends the plugin when missing and never duplicates it."""
    stub, _funcs, store = _command_stub(reload_result=True, loaded_after=True, initial=[])
    assert PluginManager._command_reload(stub).success is True
    assert store == [PLUGIN_ID]

    stub, _funcs, store = _command_stub(reload_result=True, loaded_after=True, initial=[PLUGIN_ID])
    assert PluginManager._command_reload(stub).success is True
    assert store == [PLUGIN_ID]


def test_command_never_sets_the_reloading_flag() -> None:
    """The command no longer calls plugin.reloading.set; the loader owns the flag."""
    stub, _funcs, _store = _command_stub(reload_result=True, loaded_after=True, initial=[])
    stub_api = stub.api
    seen: list[str] = []

    def spy(name: str) -> Any:
        seen.append(name)
        return stub_api(name)

    stub.api = spy
    PluginManager._command_reload(stub)
    assert not any("reloading.set" in name for name in seen)


# loader


def _loader(
    *,
    can_reload: dict[str, bool],
    deps: dict[str, list[str]] | None = None,
    unload_ok: dict[str, bool] | None = None,
    reload_dependents: bool = False,
) -> tuple[PluginLoader, dict[str, SimpleNamespace], list[bool]]:
    deps = deps or {}
    unload_ok = unload_ok or {}
    loader = PluginLoader.__new__(PluginLoader)
    loader.plugins_info = {}
    instances: dict[str, SimpleNamespace] = {}
    for pid, can in can_reload.items():
        info = PluginInfo(plugin_id=pid)
        info.dependencies = deps.get(pid, [])
        inst = SimpleNamespace(
            can_reload_f=can,
            reload_dependents_f=reload_dependents and pid == PLUGIN_ID,
            is_reloading_f=False,
        )
        info.runtime_info.is_loaded = True
        info.runtime_info.plugin_instance = inst  # type: ignore[assignment]
        loader.plugins_info[pid] = info
        instances[pid] = inst

    flag_at_unload: list[bool] = []

    def unload(pid: str, **_kw: Any) -> bool:
        if pid == PLUGIN_ID:
            flag_at_unload.append(instances[pid].is_reloading_f)
        return unload_ok.get(pid, True)

    def load(pids: list[str], **_kw: Any) -> dict[str, list[str]]:
        return {"loaded_plugins": list(pids), "bad_plugins": []}

    apis: dict[str, Any] = {
        "libs.plugins.loader:plugin.unload": unload,
        "libs.plugins.loader:plugin.load": load,
        "plugins.core.settings:setting.get": lambda *_a: [],
        "plugins.core.settings:setting.set": lambda *_a: None,
    }
    loader.api = MagicMock(side_effect=lambda name: apis[name])
    return loader, instances, flag_at_unload


def test_loader_refused_for_the_plugin_leaves_flag_unset() -> None:
    loader, instances, _ = _loader(can_reload={PLUGIN_ID: False})
    assert loader._api_plugin_reload(PLUGIN_ID) is False
    assert instances[PLUGIN_ID].is_reloading_f is False


def test_loader_refused_for_a_dependent_leaves_flag_unset() -> None:
    dependent = "plugins.test.gamma"
    loader, instances, _ = _loader(
        can_reload={PLUGIN_ID: True, dependent: False},
        deps={dependent: [PLUGIN_ID]},
        reload_dependents=True,
    )
    assert loader._api_plugin_reload(PLUGIN_ID) is False
    assert instances[PLUGIN_ID].is_reloading_f is False


def test_loader_allowed_sets_flag_before_unload() -> None:
    loader, _instances, flag_at_unload = _loader(can_reload={PLUGIN_ID: True})
    assert loader._api_plugin_reload(PLUGIN_ID) is True
    assert flag_at_unload == [True]


def test_loader_failed_unload_clears_flag() -> None:
    loader, instances, flag_at_unload = _loader(
        can_reload={PLUGIN_ID: True}, unload_ok={PLUGIN_ID: False}
    )
    assert loader._api_plugin_reload(PLUGIN_ID) is False
    assert flag_at_unload == [True]
    assert instances[PLUGIN_ID].is_reloading_f is False

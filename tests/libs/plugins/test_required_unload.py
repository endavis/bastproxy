"""Tests for refusing to unload required plugins (issue #130)."""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs.plugins import imputils
from bastproxy.libs.plugins.loader import PluginLoader
from bastproxy.libs.plugins.plugininfo import PluginInfo
from bastproxy.plugins.core.pluginm.plugin._pluginm import PluginManager

ROOT_PKG = "zzreq130"
RECORDER = "zzreq130rec"

_PLUGIN_CODE = """\
import {recorder}


class Plugin:
    can_reload_f = {can_reload}
    reload_dependents_f = {reload_dependents}

    def restore_reload_cache(self):
        pass

    def __init__(self, plugin_id, plugin_info):
        self.info = plugin_info
        {recorder}.events.append(("init", plugin_id))
        if {fail_init}:
            raise RuntimeError("boom")

    def initialize(self):
        {recorder}.events.append(("initialize", self.info.plugin_id))
        if {fail_initialize}:
            raise RuntimeError("boom")
        self.info.runtime_info.is_loaded = True

    def uninitialize(self):
        {recorder}.events.append(("uninitialize", self.info.plugin_id))
"""

Env = tuple[Path, Callable[[], PluginLoader]]


def _package(name: str) -> str:
    return f"{ROOT_PKG}.test.{name}"


def _write_plugin(
    root: Path,
    name: str,
    deps_line: str = "",
    *,
    can_reload: bool = True,
    reload_dependents: bool = False,
    fail_init: bool = False,
    fail_initialize: bool = False,
) -> None:
    plugin_dir = root / ROOT_PKG / "test" / name
    (plugin_dir / "plugin").mkdir(parents=True, exist_ok=True)
    (root / ROOT_PKG / "__init__.py").write_text("")
    (root / ROOT_PKG / "test" / "__init__.py").write_text("")
    if not (root / f"{RECORDER}.py").exists():
        (root / f"{RECORDER}.py").write_text("events = []\n")
    (plugin_dir / "__init__.py").write_text(
        f'PLUGIN_NAME = "{name}"\n'
        'PLUGIN_PURPOSE = "repro"\n'
        'PLUGIN_AUTHOR = "Bast"\n'
        "PLUGIN_VERSION = 1\n" + deps_line
    )
    (plugin_dir / "plugin" / "__init__.py").write_text(
        "from ._plugin import Plugin\n\n__all__ = ['Plugin']\n"
    )
    (plugin_dir / "plugin" / "_plugin.py").write_text(
        _PLUGIN_CODE.format(
            recorder=RECORDER,
            can_reload=can_reload,
            reload_dependents=reload_dependents,
            fail_init=fail_init,
            fail_initialize=fail_initialize,
        )
    )


def _build_loader(root: Path, monkeypatch: pytest.MonkeyPatch) -> PluginLoader:
    monkeypatch.syspath_prepend(str(root))
    _, found, _ = imputils.find_packages_and_plugins(root / ROOT_PKG, f"{ROOT_PKG}.")
    loader = PluginLoader.__new__(PluginLoader)
    loader.plugins_info = {}
    for item in found:
        info = PluginInfo(plugin_id=item["plugin_id"])
        info.package_init_file_path = item["package_init_file_path"]
        info.package_path = item["package_path"]
        info.package_import_location = item["package_import_location"]
        loader.plugins_info[item["plugin_id"]] = info
    loader.weak_references_to_modules = {}
    settings: dict[str, list[str]] = {"pluginstoload": []}
    setattr(loader, "test_settings", settings)  # noqa: B010

    apis: dict[str, Callable[..., Any]] = {
        "plugin.unload": loader._api_plugin_unload,
        "plugin.load": loader._api_plugin_load,
        "plugins.core.settings:setting.get": lambda _owner, name: list(settings[name]),
        "plugins.core.settings:setting.set": lambda _owner, name, value: settings.update(
            {name: value}
        ),
    }

    def _api(name: str) -> Callable[..., Any]:
        key = name.split(":", 1)[1] if name.endswith((":plugin.unload", ":plugin.load")) else name
        return apis.get(key, MagicMock())

    loader.api = MagicMock(side_effect=_api)
    return loader


def _settings(loader: PluginLoader) -> dict[str, list[str]]:
    settings: dict[str, list[str]] = getattr(loader, "test_settings")  # noqa: B009
    return settings


def _events() -> list[tuple[str, str]]:
    events: list[tuple[str, str]] = sys.modules[RECORDER].events
    return list(events)


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Env]:
    """Return the throwaway root and a loader factory; clean sys.modules after."""
    sys.modules.pop(RECORDER, None)
    yield tmp_path, lambda: _build_loader(tmp_path, monkeypatch)
    for name in [
        n for n in sys.modules if n in (ROOT_PKG, RECORDER) or n.startswith(f"{ROOT_PKG}.")
    ]:
        del sys.modules[name]


def _loaded(env: Env, **kwargs: Any) -> tuple[PluginLoader, str]:
    root, factory = env
    _write_plugin(root, "a", **kwargs)
    loader = factory()
    pid = _package("a")
    assert loader._api_plugin_load([pid])["bad_plugins"] == []
    return loader, pid


def test_required_plugin_is_not_unloaded(env: Env) -> None:
    loader, pid = _loaded(env)
    loader.plugins_info[pid].is_required = True
    assert loader._api_plugin_unload(pid) is False
    assert ("uninitialize", pid) not in _events()
    assert loader.plugins_info[pid].runtime_info.is_loaded
    assert any(n.startswith(f"{pid}") for n in sys.modules)


def test_required_plugin_unloads_with_allow_required(env: Env) -> None:
    loader, pid = _loaded(env)
    loader.plugins_info[pid].is_required = True
    assert loader._api_plugin_unload(pid, allow_required=True) is True
    assert ("uninitialize", pid) in _events()
    assert not loader.plugins_info[pid].runtime_info.is_loaded


def test_non_required_plugin_still_unloads(env: Env) -> None:
    loader, pid = _loaded(env)
    assert loader._api_plugin_unload(pid) is True
    assert ("uninitialize", pid) in _events()


def test_cannot_reload_plugin_refused_even_with_allow_required(env: Env) -> None:
    loader, pid = _loaded(env, can_reload=False)
    assert loader._api_plugin_unload(pid, allow_required=True) is False
    assert ("uninitialize", pid) not in _events()


def test_required_reloadable_plugin_can_be_reloaded(env: Env) -> None:
    loader, pid = _loaded(env)
    loader.plugins_info[pid].is_required = True
    assert loader._api_plugin_reload(pid) is True
    kinds = [e[0] for e in _events() if e[1] == pid]
    assert kinds == ["init", "initialize", "uninitialize", "init", "initialize"]


def test_failed_initialize_of_required_plugin_is_cleaned_up(env: Env) -> None:
    root, factory = env
    _write_plugin(root, "a", fail_initialize=True)
    loader = factory()
    pid = _package("a")
    loader.plugins_info[pid].is_required = True
    result = loader._api_plugin_load([pid], exit_on_error=False)
    assert pid in result["bad_plugins"]
    assert not [n for n in sys.modules if n.startswith(f"{ROOT_PKG}.test.a")]


def _command_stub(is_required: bool, unload_result: bool = True) -> tuple[MagicMock, MagicMock]:
    unload = MagicMock(return_value=unload_result)
    info = MagicMock()
    info.is_required = is_required

    def api(name: str) -> Any:
        return {
            "plugins.core.commands:command.current.args.get": lambda: {"plugin": "p.x"},
            "libs.plugins.loader:plugin.is.loaded": lambda _pid: True,
            "libs.plugins.loader:plugin.info.get": lambda _pid: info,
            "libs.plugins.loader:plugin.unload": unload,
            "plugins.core.settings:setting.get": lambda *_a: [],
        }.get(name, MagicMock())

    stub = MagicMock()
    stub.plugin_id = "plugins.core.pluginm"
    stub.api = MagicMock(side_effect=api)
    return stub, unload


def test_unload_command_refuses_required_plugin() -> None:
    stub, unload = _command_stub(is_required=True)
    result = PluginManager._command_unload(stub)
    assert result == (False, ["Plugin p.x is required and cannot be unloaded"])
    unload.assert_not_called()


def test_unload_command_unloads_non_required_plugin() -> None:
    stub, unload = _command_stub(is_required=False)
    assert PluginManager._command_unload(stub) == (True, ["Plugin p.x unloaded"])
    unload.assert_called_once_with("p.x")

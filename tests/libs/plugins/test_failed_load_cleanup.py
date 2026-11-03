# Project: bastproxy
# Filename: tests/libs/plugins/test_failed_load_cleanup.py
#
# File Description: Tests that a failed plugin load leaves no modules behind
#
# By: Bast
"""Tests for the failed-load cleanup in ``_api_load_plugins`` (issue #111)."""

from __future__ import annotations

import gc
import logging
import sys
import types
import weakref
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs.api import API
from bastproxy.libs.plugins import imputils
from bastproxy.libs.plugins.loader import PluginLoader, plugin_module_names
from bastproxy.libs.plugins.plugininfo import PluginInfo

ROOT_PKG = "zzfailload111"
PACKAGE = f"{ROOT_PKG}.test.zzfail"
PLUGIN_ID = PACKAGE

_BROKEN_INIT = (
    "class Plugin:\n"
    "    def restore_reload_cache(self):\n"
    "        pass\n\n"
    "    def __init__(self, plugin_id, plugin_info):\n"
    "        raise RuntimeError('boom')\n"
)
_BROKEN_INITIALIZE = (
    "class Plugin:\n"
    "    def restore_reload_cache(self):\n"
    "        pass\n\n"
    "    def __init__(self, plugin_id, plugin_info):\n"
    "        pass\n\n"
    "    def initialize(self):\n"
    "        raise RuntimeError('boom')\n"
)
_GOOD = (
    "VERSION = 'fixed'\n\n\n"
    "class Plugin:\n"
    "    version = VERSION\n\n"
    "    def restore_reload_cache(self):\n"
    "        pass\n\n"
    "    def __init__(self, plugin_id, plugin_info):\n"
    "        self.info = plugin_info\n\n"
    "    def initialize(self):\n"
    "        # the real BasePlugin flags itself loaded through the API\n"
    "        self.info.runtime_info.is_loaded = True\n"
)


def _write_plugin(root: Path, code: str) -> None:
    """Write (or rewrite) the throwaway plugin package under ``root``."""
    plugin_dir = root / ROOT_PKG / "test" / "zzfail"
    (plugin_dir / "plugin").mkdir(parents=True, exist_ok=True)
    (root / ROOT_PKG / "__init__.py").write_text("")
    (root / ROOT_PKG / "test" / "__init__.py").write_text("")
    (plugin_dir / "__init__.py").write_text(
        'PLUGIN_NAME = "zzfail"\n'
        'PLUGIN_PURPOSE = "repro"\n'
        'PLUGIN_AUTHOR = "Bast"\n'
        "PLUGIN_VERSION = 1\n"
    )
    (plugin_dir / "plugin" / "__init__.py").write_text(
        "from ._plugin import Plugin\n\n__all__ = ['Plugin']\n"
    )
    (plugin_dir / "plugin" / "_plugin.py").write_text(code)


def _plugin_modules() -> list[str]:
    return plugin_module_names(PACKAGE)


def _make_loader(root: Path, monkeypatch: pytest.MonkeyPatch) -> PluginLoader:
    monkeypatch.syspath_prepend(str(root))
    _, found, _ = imputils.find_packages_and_plugins(root / ROOT_PKG, f"{ROOT_PKG}.")
    assert [p["plugin_id"] for p in found] == [PACKAGE]

    plugin_info = PluginInfo(plugin_id=PLUGIN_ID)
    plugin_info.package_init_file_path = found[0]["package_init_file_path"]
    plugin_info.package_path = found[0]["package_path"]
    plugin_info.package_import_location = found[0]["package_import_location"]

    loader = PluginLoader.__new__(PluginLoader)
    loader.api = MagicMock()
    loader.plugins_info = {PLUGIN_ID: plugin_info}
    loader.weak_references_to_modules = {}
    return loader


@pytest.fixture
def make_loader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[Path, Callable[[str], PluginLoader]]]:
    """Return a throwaway root and a factory-built loader; clean sys.modules after."""

    def _factory(code: str) -> PluginLoader:
        _write_plugin(tmp_path, code)
        return _make_loader(tmp_path, monkeypatch)

    yield tmp_path, _factory
    for name in [n for n in sys.modules if n == ROOT_PKG or n.startswith(f"{ROOT_PKG}.")]:
        del sys.modules[name]


@pytest.mark.parametrize("broken", [_BROKEN_INIT, _BROKEN_INITIALIZE])
def test_failed_load_leaves_no_modules_and_reload_gets_new_code(
    make_loader: tuple[Path, Callable[[str], PluginLoader]], broken: str
) -> None:
    """A failed instantiate/initialize removes every plugin module; a retry reimports."""
    root, factory = make_loader
    loader = factory(broken)

    result = loader._api_load_plugins([PLUGIN_ID])
    assert result["bad_plugins"] == [PLUGIN_ID]
    assert _plugin_modules() == []

    _write_plugin(root, _GOOD)
    result = loader._api_load_plugins([PLUGIN_ID])
    assert result["bad_plugins"] == []
    info = loader.plugins_info[PLUGIN_ID]
    assert sys.modules[info.plugin_class_import_location].Plugin.version == "fixed"


def test_plugin_module_names_matches_package_and_children_only() -> None:
    """The helper matches the package and its children, not sibling prefixes."""
    names = ["zzhelper111", "zzhelper111.a", "zzhelper111.a.b", "zzhelper1112", "zzhelper11"]
    for name in names:
        sys.modules[name] = MagicMock()
    try:
        assert sorted(plugin_module_names("zzhelper111")) == [
            "zzhelper111",
            "zzhelper111.a",
            "zzhelper111.a.b",
        ]
    finally:
        for name in names:
            del sys.modules[name]


# ------------------------------------------------------------------
# Registry cleanup after a failed load (issue #121)
# ------------------------------------------------------------------
WORLD_MODULE = "zz121world"
KINDS = ("timers", "events", "watch", "settings")


class _FakeDict:
    """Stand-in for a settings PersistentDict that records ``close``."""

    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _World:
    """Fake subsystem registries, keyed by owner, plus an ``ev_plugin_unloaded`` dispatcher.

    They hold the bound methods they are given (a MagicMock would keep them alive
    through ``mock_calls`` and make the weakref check meaningless).
    """

    def __init__(self) -> None:
        self.registries: dict[str, dict[str, list[Any]]] = {kind: {} for kind in KINDS}
        self.refs: list[weakref.ReferenceType[Any]] = []
        self.raised: list[tuple[str, dict[str, str]]] = []
        self.uninitialized: list[str] = []

    def register(self, kind: str, owner: str, obj: Any) -> None:
        self.registries[kind].setdefault(owner, []).append(obj)

    def raise_event(self, name: str, event_args: dict[str, str]) -> None:
        self.raised.append((name, event_args))
        for kind in KINDS:
            # like Event.raise_priority, one handler failing must not stop the rest
            owner = event_args["plugin_id"]
            for obj in self.registries[kind].pop(owner, []):
                if isinstance(obj, _FakeDict):
                    obj.close()

    def empty_for(self, owner: str) -> bool:
        return all(owner not in registry for registry in self.registries.values())


_PLUGIN_TEMPLATE = (
    "import weakref\n"
    "import zz121world as W\n"
    "from bastproxy.libs.api import AddAPI\n"
    "from bastproxy.plugins._baseplugin._base import Plugin as Base\n\n\n"
    "class Plugin(Base):\n"
    "    def __init__(self, plugin_id, plugin_info):\n"
    "        super().__init__(plugin_id, plugin_info)\n"
    "        W.refs.append(weakref.ref(self))\n"
    "{init_body}\n"
    "    @AddAPI('ping')\n"
    "    def _api_ping(self):\n"
    "        return 1\n\n"
    "    def _cb(self, *args):\n"
    "        pass\n\n"
    "    def uninitialize(self):\n"
    "        W.uninitialized.append(self.plugin_id)\n\n"
    "    def initialize(self):\n"
    "{initialize_body}\n"
)
_REGISTER_ALL = (
    "        W.register('timers', self.plugin_id, self._cb)\n"
    "        W.register('events', self.plugin_id, self._cb)\n"
    "        W.register('watch', self.plugin_id, self._cb)\n"
    "        W.register('settings', self.plugin_id, W.make_dict())\n"
)


def _plugin_code(init_body: str = "        pass", initialize_body: str = "        pass") -> str:
    return _PLUGIN_TEMPLATE.format(init_body=init_body, initialize_body=initialize_body)


_INIT_FAIL = _plugin_code(
    init_body=(
        "        W.register('events', self.plugin_id, self._cb)\n"
        "        raise RuntimeError('init boom')"
    )
)
_INITIALIZE_FAIL = _plugin_code(
    initialize_body=_REGISTER_ALL + "        raise RuntimeError('initialize boom')"
)


class _Env:
    """The loader, fake world and API routing for one failed-load test."""

    def __init__(self, loader: PluginLoader, world: _World, routes: dict[str, Any]) -> None:
        self.loader = loader
        self.world = world
        self.routes = routes
        self.real_api = API(owner_id="test121")

    def stale_api_keys(self) -> list[str]:
        prefix = f"{PLUGIN_ID}:"
        return [
            key for key in (*API._class_api, *self.real_api._instance_api) if key.startswith(prefix)
        ]


@pytest.fixture
def cleanup_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[[str], _Env]]:
    """Return a factory for a loader wired to the real API and the fake world."""
    # the real API needs these for the base plugin's reload-cache restore
    from bastproxy.libs.plugins import reloadutils  # noqa: F401

    envs: list[_Env] = []

    def _factory(code: str) -> _Env:
        world = _World()
        module = types.ModuleType(WORLD_MODULE)
        module.__dict__.update(
            refs=world.refs,
            uninitialized=world.uninitialized,
            register=world.register,
            make_dict=_FakeDict,
        )
        monkeypatch.setitem(sys.modules, WORLD_MODULE, module)

        _write_plugin(tmp_path, code)
        loader = _make_loader(tmp_path, monkeypatch)
        loader.plugins_info[PLUGIN_ID].data_directory = tmp_path / "data"
        settings: dict[str, list[str]] = {"pluginstoload": []}
        env = _Env(loader, world, {})
        env.routes.update(
            {
                "libs.api:remove": env.real_api("libs.api:remove"),
                # the fake events API is not in the real API, so report it present
                "libs.api:has": lambda _name: True,
                "plugins.core.events:raise.event": world.raise_event,
                "unload.plugin": loader._api_unload_plugin,
                "plugins.core.settings:setting.get": lambda _owner, name: list(settings[name]),
                "plugins.core.settings:setting.set": lambda _owner, name, value: settings.update(
                    {name: value}
                ),
            }
        )

        def _api(name: str) -> Callable[..., Any]:
            key = name.split(":", 1)[1] if name.endswith(":unload.plugin") else name
            return env.routes.get(key) or MagicMock()

        loader.api = MagicMock(side_effect=_api)
        envs.append(env)
        return env

    yield _factory
    for env in envs:
        if env.stale_api_keys():
            env.real_api("libs.api:remove")(PLUGIN_ID)
    for name in [n for n in sys.modules if n == ROOT_PKG or n.startswith(f"{ROOT_PKG}.")]:
        del sys.modules[name]


@pytest.fixture
def no_log_capture(monkeypatch: pytest.MonkeyPatch) -> Callable[[], None]:
    """Keep pytest's log-capture handlers from retaining ``exc_info`` tracebacks.

    The loader logs the load failure with ``exc_info=True``. pytest's capture
    handlers keep every ``LogRecord``, and the record's traceback references the
    plugin's frames and so the instance. That is the test harness holding the
    instance, not the loader, so the weakref test has to run without it.
    """

    def _drop() -> None:
        # pytest installs its handlers for the call phase, so drop them from inside the test
        root = logging.getLogger()
        kept = [h for h in root.handlers if type(h).__name__ != "LogCaptureHandler"]
        monkeypatch.setattr(root, "handlers", kept)

    return _drop


def _assert_cleaned(env: _Env) -> None:
    assert env.world.empty_for(PLUGIN_ID)
    assert env.stale_api_keys() == []
    assert env.world.raised == [("ev_plugin_unloaded", {"plugin_id": PLUGIN_ID})]
    assert env.loader.plugins_info[PLUGIN_ID].runtime_info.plugin_instance is None


@pytest.mark.parametrize("code", [_INIT_FAIL, _INITIALIZE_FAIL], ids=["init", "initialize"])
def test_failed_load_removes_registrations_and_frees_instance(
    cleanup_env: Callable[[str], _Env], code: str, no_log_capture: Callable[[], None]
) -> None:
    """A failure in __init__ or initialize leaves no registry, API or live instance."""
    env = cleanup_env(code)
    no_log_capture()

    result = env.loader._api_load_plugins([PLUGIN_ID])

    assert result["bad_plugins"] == [PLUGIN_ID]
    _assert_cleaned(env)
    gc.collect()
    assert [ref() for ref in env.world.refs] == [None]


def test_failed_initialize_closes_settings_stand_in(cleanup_env: Callable[[str], _Env]) -> None:
    """The settings handler stand-in is closed when the failed plugin is cleaned up."""
    env = cleanup_env(_INITIALIZE_FAIL)
    seen: list[_FakeDict] = []
    original = env.world.register

    def _spy(kind: str, owner: str, obj: Any) -> None:
        if isinstance(obj, _FakeDict):
            seen.append(obj)
        original(kind, owner, obj)

    sys.modules[WORLD_MODULE].register = _spy  # type: ignore[attr-defined]

    env.loader._api_load_plugins([PLUGIN_ID])

    assert len(seen) == 1
    assert seen[0].closed is True


def test_cleanup_continues_when_event_raise_fails(cleanup_env: Callable[[str], _Env]) -> None:
    """A failing raise.event is logged and the API removal still happens."""
    env = cleanup_env(_INIT_FAIL)
    raise_event = MagicMock(side_effect=RuntimeError("event boom"))
    env.routes["plugins.core.events:raise.event"] = raise_event

    result = env.loader._api_load_plugins([PLUGIN_ID])

    assert result["bad_plugins"] == [PLUGIN_ID]
    raise_event.assert_called_once()
    assert env.stale_api_keys() == []
    assert _plugin_modules() == []


def test_cleanup_skips_event_when_events_api_missing(
    cleanup_env: Callable[[str], _Env],
) -> None:
    """Without the events plugin nothing is raised, but the APIs are still removed."""
    env = cleanup_env(_INIT_FAIL)
    raise_event = MagicMock()
    remove = MagicMock()
    env.routes["libs.api:has"] = lambda _name: False
    env.routes["plugins.core.events:raise.event"] = raise_event
    env.routes["libs.api:remove"] = remove

    env.loader._api_load_plugins([PLUGIN_ID])

    raise_event.assert_not_called()
    remove.assert_called_once_with(PLUGIN_ID)


def test_failed_initialize_cleans_up_plugin_with_can_reload_false(
    cleanup_env: Callable[[str], _Env],
) -> None:
    """A can_reload_f=False plugin that fails initialize is still cleaned up."""
    code = _plugin_code(
        initialize_body=(
            "        self.can_reload_f = False\n"
            + _REGISTER_ALL
            + "        raise RuntimeError('initialize boom')"
        )
    )
    env = cleanup_env(code)

    result = env.loader._api_load_plugins([PLUGIN_ID])

    assert result["bad_plugins"] == [PLUGIN_ID]
    _assert_cleaned(env)
    assert _plugin_modules() == []


def test_initialize_failure_after_loaded_flag_does_not_uninitialize(
    cleanup_env: Callable[[str], _Env],
) -> None:
    """A hook failing after is_loaded was set takes the never-loaded path."""
    code = _plugin_code(
        initialize_body=(
            "        self.plugin_info.runtime_info.is_loaded = True\n"
            + _REGISTER_ALL
            + "        raise RuntimeError('initialize boom')"
        )
    )
    env = cleanup_env(code)

    result = env.loader._api_load_plugins([PLUGIN_ID])

    assert result["bad_plugins"] == [PLUGIN_ID]
    assert env.world.uninitialized == []
    _assert_cleaned(env)
    assert env.loader.plugins_info.get(PLUGIN_ID) is not None
    assert env.loader.plugins_info[PLUGIN_ID].runtime_info.is_loaded is False


def _loaded_loader(*, can_reload: bool) -> tuple[PluginLoader, MagicMock]:
    plugin_info = PluginInfo(plugin_id=PLUGIN_ID)
    instance = MagicMock()
    instance.can_reload_f = can_reload
    plugin_info.runtime_info.plugin_instance = instance
    plugin_info.runtime_info.is_loaded = True
    loader = PluginLoader.__new__(PluginLoader)
    loader.api = MagicMock()
    loader.plugins_info = {PLUGIN_ID: plugin_info}
    loader.weak_references_to_modules = {}
    loader._remove_plugin_registrations = MagicMock()  # type: ignore[method-assign]
    return loader, instance


def test_loaded_plugin_with_can_reload_false_still_refused() -> None:
    """The can_reload_f refusal still protects a loaded plugin."""
    loader, instance = _loaded_loader(can_reload=False)

    assert loader._api_unload_plugin(PLUGIN_ID) is False
    instance.uninitialize.assert_not_called()


def test_loaded_unload_still_uses_uninitialize() -> None:
    """A loaded plugin is uninitialized, not cleaned up through the failed-load path."""
    loader, instance = _loaded_loader(can_reload=True)

    assert loader._api_unload_plugin(PLUGIN_ID) is True
    instance.uninitialize.assert_called_once_with()
    loader._remove_plugin_registrations.assert_not_called()  # type: ignore[attr-defined]

# Project: bastproxy
# Filename: tests/libs/plugins/test_plugin_dependencies.py
#
# File Description: Tests for PLUGIN_DEPENDENCIES parsing, loading and reloading
#
# By: Bast
"""Tests for plugin dependencies (issue #97)."""

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

ROOT_PKG = "zzdep97"
RECORDER = "zzdep97rec"

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


def _dep(*names: str) -> str:
    return f"PLUGIN_DEPENDENCIES = {[_package(n) for n in names]!r}\n"


def _parse(tmp_path: Path, extra: str) -> PluginInfo:
    init = tmp_path / "__init__.py"
    init.write_text(
        'PLUGIN_NAME = "x"\nPLUGIN_PURPOSE = "p"\nPLUGIN_AUTHOR = "a"\nPLUGIN_VERSION = 1\n' + extra
    )
    info = PluginInfo("plugins.test.x")
    info.package_init_file_path = init
    info.update_from_init()
    return info


# ---------------------------------------------------------------- parsing
def test_parse_one_line_multi_line_and_tuple(tmp_path: Path) -> None:
    assert _parse(tmp_path, 'PLUGIN_DEPENDENCIES = ["plugins.a"]\n').dependencies == ["plugins.a"]
    multi = "PLUGIN_DEPENDENCIES = [\n    \"plugins.a\",\n    'plugins.b',\n]\n"
    assert _parse(tmp_path, multi).dependencies == ["plugins.a", "plugins.b"]
    assert _parse(tmp_path, 'PLUGIN_DEPENDENCIES = ("plugins.a",)\n').dependencies == ["plugins.a"]


def test_parse_missing_line_gives_empty(tmp_path: Path) -> None:
    info = _parse(tmp_path, "")
    assert info.dependencies == []
    assert info.import_errors == []


@pytest.mark.parametrize("value", ["'plugins.a'", "[1, 2]", "foo()", "{'a': 1}"])
def test_parse_invalid_value_gives_empty_and_error(tmp_path: Path, value: str) -> None:
    info = _parse(tmp_path, f"PLUGIN_DEPENDENCIES = {value}\n")
    assert info.dependencies == []
    assert len(info.import_errors) == 1
    info.update_from_init()
    assert len(info.import_errors) == 1


def test_parse_drops_self_and_duplicates(tmp_path: Path) -> None:
    deps = 'PLUGIN_DEPENDENCIES = ["plugins.a", "plugins.test.x", "plugins.a", "plugins.b"]\n'
    assert _parse(tmp_path, deps).dependencies == ["plugins.a", "plugins.b"]


def test_parse_line_after_early_break_point(tmp_path: Path) -> None:
    """Placed after every other metadata line (where the line loop breaks)."""
    init = tmp_path / "__init__.py"
    init.write_text(
        'PLUGIN_REQUIRED = True\nPLUGIN_NAME = "x"\nPLUGIN_PURPOSE = "p"\n'
        'PLUGIN_AUTHOR = "a"\nPLUGIN_VERSION = 1\n\nX = 1\nPLUGIN_DEPENDENCIES = ["plugins.a"]\n'
    )
    info = PluginInfo("plugins.test.x")
    info.package_init_file_path = init
    info.update_from_init()
    assert info.dependencies == ["plugins.a"]


def test_parse_resets_when_line_removed(tmp_path: Path) -> None:
    info = _parse(tmp_path, 'PLUGIN_DEPENDENCIES = ["plugins.a"]\n')
    assert info.dependencies == ["plugins.a"]
    info.package_init_file_path.write_text('PLUGIN_NAME = "x"\n')
    info.update_from_init()
    assert info.dependencies == []


# ---------------------------------------------------------------- loading
def test_dependency_loads_and_initializes_first(env: Env) -> None:
    root, factory = env
    _write_plugin(root, "a")
    _write_plugin(root, "b", _dep("a"))
    loader = factory()

    result = loader._api_plugin_load([_package("b")])
    assert result["bad_plugins"] == []
    assert result["loaded_plugins"] == [_package("a"), _package("b")]
    assert [e for e in _events() if e[0] == "initialize"] == [
        ("initialize", _package("a")),
        ("initialize", _package("b")),
    ]


def test_missing_dependency_fails_dependent_and_leaves_no_modules(env: Env) -> None:
    root, factory = env
    _write_plugin(root, "b", f"PLUGIN_DEPENDENCIES = ['{ROOT_PKG}.test.ghost']\n")
    loader = factory()

    result = loader._api_plugin_load([_package("b")])
    assert _package("b") in result["bad_plugins"]
    assert result["loaded_plugins"] == []
    assert not [n for n in sys.modules if n.startswith(_package("b"))]
    assert _events() == []


def test_failing_dependency_fails_dependent_but_not_unrelated(env: Env) -> None:
    root, factory = env
    _write_plugin(root, "a", fail_initialize=True)
    _write_plugin(root, "b", _dep("a"))
    _write_plugin(root, "c")
    loader = factory()

    result = loader._api_plugin_load([_package("b"), _package("c")])
    assert set(result["bad_plugins"]) == {_package("a"), _package("b")}
    assert result["loaded_plugins"] == [_package("c")]
    assert ("initialize", _package("b")) not in _events()
    assert not [n for n in sys.modules if n.startswith((_package("a"), _package("b")))]


def test_unknown_plugin_id_is_reported_not_raised(env: Env) -> None:
    root, factory = env
    _write_plugin(root, "a")
    loader = factory()
    result = loader._api_plugin_load(["nope", _package("a")])
    assert result["bad_plugins"] == ["nope"]
    assert result["loaded_plugins"] == [_package("a")]


# --------------------------------------------------------------- reloading
def _chain(root: Path, *, flag: bool, c_can_reload: bool = True) -> list[str]:
    _write_plugin(root, "a", reload_dependents=flag)
    _write_plugin(root, "b", _dep("a"))
    _write_plugin(root, "c", _dep("b"), can_reload=c_can_reload)
    return [_package(n) for n in ("a", "b", "c")]


def test_reload_with_flag_reloads_dependents_in_order(env: Env) -> None:
    root, factory = env
    ids = _chain(root, flag=True)
    loader = factory()
    assert loader._api_plugin_load(ids)["bad_plugins"] == []
    old = {p: loader.plugins_info[p].runtime_info.plugin_instance for p in ids}
    _settings(loader)["pluginstoload"] = [ids[1], ids[2]]
    sys.modules[RECORDER].events.clear()

    assert loader._api_plugin_reload(ids[0]) is True

    events = _events()
    assert [e[1] for e in events if e[0] == "uninitialize"] == [ids[2], ids[1], ids[0]]
    assert [e[1] for e in events if e[0] == "initialize"] == ids
    for pid in ids:
        new = loader.plugins_info[pid].runtime_info.plugin_instance
        assert new is not None
        assert new is not old[pid]
    assert set(_settings(loader)["pluginstoload"]) == {ids[1], ids[2]}


def test_reload_without_flag_reloads_only_the_plugin(env: Env) -> None:
    root, factory = env
    ids = _chain(root, flag=False)
    loader = factory()
    loader._api_plugin_load(ids)
    sys.modules[RECORDER].events.clear()

    assert loader._api_plugin_reload(ids[0]) is True
    assert _events() == [
        ("uninitialize", ids[0]),
        ("init", ids[0]),
        ("initialize", ids[0]),
    ]
    assert loader.plugins_info[ids[1]].runtime_info.is_loaded


def test_reload_refused_when_a_dependent_cannot_reload(env: Env) -> None:
    root, factory = env
    ids = _chain(root, flag=True, c_can_reload=False)
    loader = factory()
    loader._api_plugin_load(ids)
    sys.modules[RECORDER].events.clear()

    assert loader._api_plugin_reload(ids[0]) is False
    assert _events() == []
    assert all(loader.plugins_info[p].runtime_info.is_loaded for p in ids)


def test_reload_returns_false_when_new_code_fails(env: Env) -> None:
    root, factory = env
    _write_plugin(root, "a")
    loader = factory()
    loader._api_plugin_load([_package("a")])
    _write_plugin(root, "a", fail_init=True)

    assert loader._api_plugin_reload(_package("a")) is False
    assert not loader.plugins_info[_package("a")].runtime_info.is_loaded

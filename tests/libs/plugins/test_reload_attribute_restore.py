"""Tests that reload attributes survive a plugin's own ``__init__`` defaults (#124)."""

from __future__ import annotations

import sys
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs.plugins.loader import PluginLoader
from bastproxy.libs.plugins.plugininfo import PluginInfo
from bastproxy.libs.plugins.reloadutils import HELPER, ReloadHelper
from bastproxy.plugins._baseplugin import RegisterPluginHook
from bastproxy.plugins._baseplugin._base import Plugin

PLUGIN_ID = "plugins.test.zzrestore124"
PACKAGE = "zzrestore124"
MODULE_NAME = f"{PACKAGE}.plugin"


class _InitPlugin(Plugin):
    """Sets the list and its default after ``super().__init__()``, as the issue describes."""

    def __init__(self, plugin_id: str, plugin_info: Any) -> None:
        super().__init__(plugin_id, plugin_info)
        self.attributes_to_save_on_reload = ["counter"]
        self.counter = 0


class _HookPlugin(Plugin):
    """Sets the list and its default in an ``__init__`` hook above priority 75."""

    @RegisterPluginHook("__init__", priority=90)
    def _phook_init_plugin(self) -> None:
        self.attributes_to_save_on_reload = ["counter"]
        self.counter = 0


@pytest.fixture
def helper() -> Iterator[ReloadHelper]:
    """Return the module-level ReloadHelper that owns the registered cache APIs."""
    HELPER.reload_cache.pop(PLUGIN_ID, None)
    yield HELPER
    HELPER.reload_cache.pop(PLUGIN_ID, None)


def _make_loader(
    plugin_cls: type[Plugin], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[PluginLoader, PluginInfo]:
    """Return a loader whose plugin module holds ``plugin_cls``."""
    plugin_info = PluginInfo(plugin_id=PLUGIN_ID)
    plugin_info.package_import_location = PACKAGE
    plugin_info.data_directory = tmp_path
    monkeypatch.setitem(sys.modules, MODULE_NAME, types.SimpleNamespace(Plugin=plugin_cls))

    loader = PluginLoader.__new__(PluginLoader)
    loader.api = MagicMock()
    loader.plugins_info = {PLUGIN_ID: plugin_info}
    return loader, plugin_info


def _load(
    plugin_cls: type[Plugin],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Plugin:
    """Instantiate ``plugin_cls`` through the loader's ``_instantiate_single_plugin``."""
    loader, plugin_info = _make_loader(plugin_cls, tmp_path, monkeypatch)
    assert loader._instantiate_single_plugin(PLUGIN_ID) is True
    instance = plugin_info.runtime_info.plugin_instance
    assert instance is not None
    return instance


@pytest.mark.parametrize("plugin_cls", [_InitPlugin, _HookPlugin])
def test_restored_value_survives_init_defaults(
    helper: ReloadHelper,
    plugin_cls: type[Plugin],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A value restored from the reload cache is not overwritten by a default."""
    helper._api_cache_add(PLUGIN_ID, "counter", 42)

    instance = _load(plugin_cls, tmp_path, monkeypatch)

    assert instance.counter == 42  # type: ignore[attr-defined]
    assert helper._api_cache_get(PLUGIN_ID) == {}


def test_no_cache_keeps_defaults(
    helper: ReloadHelper, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without a reload cache the plugin keeps the defaults it set."""
    instance = _load(_InitPlugin, tmp_path, monkeypatch)

    assert instance.counter == 0  # type: ignore[attr-defined]


def test_restore_failure_fails_instantiation(
    helper: ReloadHelper, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An error while restoring is handled like an instantiation failure."""

    class _Broken(_InitPlugin):
        def restore_reload_cache(self) -> None:
            raise RuntimeError("boom")

    loader, _ = _make_loader(_Broken, tmp_path, monkeypatch)
    assert loader._instantiate_single_plugin(PLUGIN_ID) is False

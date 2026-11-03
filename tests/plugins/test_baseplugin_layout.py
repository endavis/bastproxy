"""Pin the _baseplugin layout: supporting modules live in libs/ (#94)."""

import importlib.util

import bastproxy.plugins._baseplugin as baseplugin_pkg
from bastproxy.plugins._baseplugin import BasePlugin, RegisterPluginHook
from bastproxy.plugins._baseplugin._base import Plugin
from bastproxy.plugins._baseplugin.libs import _pluginhooks
from bastproxy.plugins._baseplugin.libs._commands import Commands
from bastproxy.plugins._baseplugin.libs._settings import Settings

PKG = "bastproxy.plugins._baseplugin"


def test_export_surface() -> None:
    assert baseplugin_pkg.__all__ == ["BasePlugin", "RegisterPluginHook"]
    assert RegisterPluginHook is _pluginhooks.RegisterPluginHook


def test_modules_live_in_libs() -> None:
    for name in ("_pluginhooks", "_commands", "_settings"):
        assert importlib.util.find_spec(f"{PKG}.libs.{name}") is not None
        assert importlib.util.find_spec(f"{PKG}.{name}") is None


def test_mro() -> None:
    assert BasePlugin.__mro__[1:4] == (Plugin, Commands, Settings)

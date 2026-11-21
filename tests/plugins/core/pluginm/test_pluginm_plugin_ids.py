"""Tests for plugin ids without the plugins prefix in load, unload, reload and list (#664)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.plugins.core.pluginm.plugin import _pluginm
from bastproxy.plugins.core.pluginm.plugin._pluginm import PluginManager

SHORT = "lc.livecheck"
FULL = "plugins.lc.livecheck"
LOADER = "libs.plugins.loader"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (SHORT, FULL),
        (FULL, FULL),
        (".core", "plugins.core"),
        ("myplugins.x", "plugins.myplugins.x"),
    ],
)
def test_full_plugin_id(name: str, expected: str) -> None:
    assert _pluginm._full_plugin_id(name) == expected


def _stub(
    arg: str, *, loaded: bool, valid: bool = True, known: bool = True, load_ok: bool = True
) -> tuple[MagicMock, dict[str, MagicMock]]:
    funcs: dict[str, MagicMock] = {
        "plugins.core.commands:command.current.args.get": MagicMock(return_value={"plugin": arg}),
        f"{LOADER}:plugin.id.is.valid": MagicMock(return_value=valid),
        f"{LOADER}:plugin.is.loaded": MagicMock(return_value=loaded),
        f"{LOADER}:plugin.list.not.loaded": MagicMock(return_value=[FULL] if known else []),
        f"{LOADER}:plugin.load": MagicMock(
            return_value={
                "loaded_plugins": [FULL] if load_ok else [],
                "bad_plugins": [] if load_ok else [FULL],
            }
        ),
        f"{LOADER}:plugin.unload": MagicMock(return_value=True),
        f"{LOADER}:plugin.reload": MagicMock(return_value=True),
        f"{LOADER}:plugin.info.get": MagicMock(return_value=MagicMock(is_required=False)),
        "plugins.core.settings:setting.get": MagicMock(return_value=[]),
        "plugins.core.settings:setting.set": MagicMock(),
        "plugins.core.events:event.raise": MagicMock(),
    }
    stub = MagicMock()
    stub.plugin_id = "plugins.core.pluginm"
    stub.api = lambda name: funcs[name]
    return stub, funcs


@pytest.mark.parametrize("arg", [SHORT, FULL])
def test_load_calls_loader_with_full_id(arg: str) -> None:
    stub, funcs = _stub(arg, loaded=False)
    result = PluginManager._command_load(stub)
    assert result.success is True
    funcs[f"{LOADER}:plugin.load"].assert_called_once_with([FULL])


@pytest.mark.parametrize("arg", [SHORT, FULL])
def test_unload_calls_loader_with_full_id(arg: str) -> None:
    stub, funcs = _stub(arg, loaded=True)
    result = PluginManager._command_unload(stub)
    assert result.success is True
    funcs[f"{LOADER}:plugin.unload"].assert_called_once_with(FULL)


@pytest.mark.parametrize("arg", [SHORT, FULL])
def test_reload_calls_loader_with_full_id(arg: str) -> None:
    stub, funcs = _stub(arg, loaded=True)
    result = PluginManager._command_reload(stub)
    assert result.success is True
    funcs[f"{LOADER}:plugin.reload"].assert_called_once_with(FULL)


def test_load_not_found_fails() -> None:
    stub, funcs = _stub(SHORT, loaded=False, known=False)
    result = PluginManager._command_load(stub)
    assert result.success is False
    assert result.message == [f"Plugin {FULL} not found"]
    funcs[f"{LOADER}:plugin.load"].assert_not_called()


def test_load_already_loaded_still_succeeds() -> None:
    stub, _funcs = _stub(SHORT, loaded=True)
    assert PluginManager._command_load(stub).success is True


def test_unload_not_loaded_fails() -> None:
    stub, funcs = _stub(SHORT, loaded=False)
    result = PluginManager._command_unload(stub)
    assert result.success is False
    assert result.message == [f"Plugin {FULL} is not loaded"]
    funcs[f"{LOADER}:plugin.unload"].assert_not_called()


def test_reload_invalid_id_fails() -> None:
    stub, funcs = _stub(SHORT, loaded=True, valid=False)
    result = PluginManager._command_reload(stub)
    assert result.success is False
    assert result.message == [f"{FULL} is not a valid plugin id"]
    funcs[f"{LOADER}:plugin.reload"].assert_not_called()


def test_reload_not_loaded_fails() -> None:
    stub, funcs = _stub(SHORT, loaded=False)
    result = PluginManager._command_reload(stub)
    assert result.success is False
    assert result.message == [f"{FULL} is not loaded; use #bp.core.pluginm.load {FULL}"]
    funcs[f"{LOADER}:plugin.reload"].assert_not_called()


@pytest.mark.parametrize("command", ["_command_load", "_command_unload"])
def test_empty_argument_is_reported(command: str) -> None:
    stub, _funcs = _stub("", loaded=False)
    result = getattr(PluginManager, command)(stub)
    assert result.success is False
    assert result.message == ["No plugin specified"]


def test_reload_empty_argument_is_invalid() -> None:
    stub, funcs = _stub("", loaded=False, valid=False)
    result = PluginManager._command_reload(stub)
    assert result.success is False
    funcs[f"{LOADER}:plugin.id.is.valid"].assert_called_once_with("")


def _list_stub() -> MagicMock:
    infos: dict[str, Any] = {
        "plugins.core.a": MagicMock(
            package="plugins.core", package_import_location="no_such_pkg_zz.a.plugin"
        ),
        "plugins.core.b": MagicMock(
            package="plugins.core", package_import_location="no_such_pkg_zz.a.plugin"
        ),
    }
    funcs: dict[str, Any] = {
        f"{LOADER}:plugin.list.loaded": lambda: infos,
        f"{LOADER}:plugin.info.get": lambda pid: infos[pid],
    }
    stub = MagicMock()
    stub.api = lambda name: funcs[name]
    stub._command_helper_format_plugin_list.side_effect = lambda plugins, title, **_k: [
        title,
        *plugins,
    ]
    return stub


def test_list_short_and_full_package_agree() -> None:
    short = PluginManager._get_package_plugins(_list_stub(), "core")
    full = PluginManager._get_package_plugins(_list_stub(), "plugins.core")
    assert short == full
    assert "plugins.core.a" in short


def test_list_unknown_package() -> None:
    assert PluginManager._get_package_plugins(_list_stub(), "nope") == [
        "That is not a valid package"
    ]

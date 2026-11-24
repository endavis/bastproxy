"""Tests for the gc re-freeze after pluginm load, unload and reload (#758)."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.plugins.core.pluginm.plugin import _pluginm
from bastproxy.plugins.core.pluginm.plugin._pluginm import PluginManager

PLUGIN_ID = "plugins.test.beta"
L = "libs.plugins.loader:"


def _stub(
    plugin_arg: Any, *, loaded: bool = True, required: bool = False, result: bool = True
) -> tuple[MagicMock, dict[str, MagicMock]]:
    info = MagicMock()
    info.is_required = required
    funcs: dict[str, MagicMock] = {
        "plugins.core.commands:command.current.args.get": MagicMock(
            return_value={"plugin": plugin_arg}
        ),
        L + "plugin.id.is.valid": MagicMock(return_value=True),
        L + "plugin.is.loaded": MagicMock(return_value=loaded),
        L + "plugin.list.not.loaded": MagicMock(return_value=[PLUGIN_ID]),
        L + "plugin.info.get": MagicMock(return_value=info),
        L + "plugin.reload": MagicMock(return_value=result),
        L + "plugin.unload": MagicMock(return_value=result),
        L + "plugin.load": MagicMock(
            return_value={"loaded_plugins": [PLUGIN_ID], "bad_plugins": []}
        ),
        "plugins.core.settings:setting.get": MagicMock(return_value=[]),
        "plugins.core.settings:setting.set": MagicMock(),
    }
    stub = MagicMock()
    stub.api = lambda name: funcs[name]
    return stub, funcs


@pytest.fixture
def refreeze(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock = MagicMock()
    monkeypatch.setattr(_pluginm.gcfreeze, "refreeze", mock)
    return mock


def test_load_refreezes(refreeze: MagicMock) -> None:
    stub, _ = _stub([PLUGIN_ID], loaded=False)
    PluginManager._command_load(stub)
    refreeze.assert_called_once()


def test_load_nothing_to_load_does_not_refreeze(refreeze: MagicMock) -> None:
    stub, _ = _stub([PLUGIN_ID], loaded=True)
    PluginManager._command_load(stub)
    refreeze.assert_not_called()


def test_load_no_plugin_does_not_refreeze(refreeze: MagicMock) -> None:
    stub, _ = _stub([])
    PluginManager._command_load(stub)
    refreeze.assert_not_called()


def test_unload_refreezes(refreeze: MagicMock) -> None:
    stub, _ = _stub(PLUGIN_ID)
    assert PluginManager._command_unload(stub).success is True
    refreeze.assert_called_once()


def test_failed_unload_refreezes(refreeze: MagicMock) -> None:
    stub, _ = _stub(PLUGIN_ID, result=False)
    assert PluginManager._command_unload(stub).success is False
    refreeze.assert_called_once()


def test_unload_refusals_do_not_refreeze(refreeze: MagicMock) -> None:
    PluginManager._command_unload(_stub("")[0])
    PluginManager._command_unload(_stub(PLUGIN_ID, loaded=False)[0])
    PluginManager._command_unload(_stub(PLUGIN_ID, required=True)[0])
    refreeze.assert_not_called()


def test_reload_refreezes(refreeze: MagicMock) -> None:
    stub, _ = _stub(PLUGIN_ID)
    assert PluginManager._command_reload(stub).success is True
    refreeze.assert_called_once()


def test_failed_reload_that_unloaded_refreezes(refreeze: MagicMock) -> None:
    stub, funcs = _stub(PLUGIN_ID, result=False)
    answers = iter([True, False])  # loaded before the reload, gone after it
    funcs[L + "plugin.is.loaded"].side_effect = lambda *_a: next(answers)
    result = PluginManager._command_reload(stub)
    assert result.success is False
    assert "unloaded but not loaded again" in result.message[0]
    refreeze.assert_called_once()


def test_reload_refusals_do_not_refreeze(refreeze: MagicMock) -> None:
    PluginManager._command_reload(_stub(PLUGIN_ID, loaded=False)[0])
    refreeze.assert_not_called()

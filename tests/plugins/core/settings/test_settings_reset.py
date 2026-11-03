"""The settings plugin must not shadow the base plugin's reset API (#164)."""

from bastproxy.plugins._baseplugin import BasePlugin
from bastproxy.plugins.core.settings.plugin._settings import SettingsPlugin


def test_settings_plugin_does_not_shadow_base_reset() -> None:
    assert SettingsPlugin._api_reset is BasePlugin._api_reset


def test_settings_reset_has_its_own_method_name() -> None:
    assert callable(SettingsPlugin._api_setting_reset)
    assert SettingsPlugin._api_setting_reset is not BasePlugin._api_reset


def test_setting_reset_restores_defaults_and_syncs() -> None:
    from unittest.mock import MagicMock

    stub = MagicMock()
    info = MagicMock()
    info.default = 5
    stub.settings_info = {"p": {"x": info}}
    values = MagicMock()
    stub.settings_values = {"p": values}

    SettingsPlugin._api_setting_reset(stub, "p")

    values.clear.assert_called_once_with()
    values.__setitem__.assert_called_once_with("x", 5)
    values.sync.assert_called_once_with()

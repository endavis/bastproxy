"""setting.set refuses a value the settings file cannot hold (#608)."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs.persistentdict import PersistentDict
from bastproxy.plugins.core.settings.libs._settinginfo import SettingInfo, SettingValidationError
from bastproxy.plugins.core.settings.plugin._settings import SettingsPlugin

PID = "plugins.test.a"


def test_set_with_unserializable_value_is_refused(temp_data_dir: Path) -> None:
    path = temp_data_dir / "settingvalues.txt"
    values = PersistentDict(PID, path)
    values["foo"] = "old"
    values.sync()
    before = path.read_text(encoding="utf-8")

    stub = MagicMock()
    stub.plugin_id = "plugins.core.settings"
    stub.settings_info = {PID: {"foo": SettingInfo("foo", "d", "help", object)}}
    stub.settings_values = {PID: values}

    def api(name: str) -> Any:
        if name == "plugins.core.settings:setting.get":
            return lambda pid, setting: stub.settings_values[pid].get(setting)
        return lambda *a, **k: False

    stub.api = api

    with pytest.raises(SettingValidationError, match="cannot be saved"):
        SettingsPlugin._api_setting_set(stub, PID, "foo", {1, 2})
    assert values["foo"] == "old"
    assert path.read_text(encoding="utf-8") == before

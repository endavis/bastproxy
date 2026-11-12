"""Tests for the mudwindowsize setting of the proxy plugin (#308)."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.plugins.core.proxy.plugin import _proxy
from bastproxy.plugins.core.proxy.plugin._proxy import ProxyPlugin


def test_initialize_adds_the_setting_and_applies_it(monkeypatch: pytest.MonkeyPatch) -> None:
    added: list[tuple[Any, ...]] = []
    forwarder = MagicMock()
    monkeypatch.setattr(_proxy, "WINDOW_SIZE", forwarder)
    stub = MagicMock()
    stub.plugin_id = "plugins.core.proxy"

    def api(name: str) -> Any:
        if name == "plugins.core.settings:setting.add":
            return lambda *args, **_k: added.append(args)
        if name == "plugins.core.settings:setting.get":
            return lambda _plugin, setting: "100x30" if setting == "mudwindowsize" else None
        return MagicMock()

    stub.api.side_effect = api

    ProxyPlugin._phook_initialize(stub)

    [entry] = [a for a in added if a[1] == "mudwindowsize"]
    assert entry[2] == "client"
    assert entry[3] is str
    forwarder.set_mode.assert_called_once_with("100x30")


def test_modified_event_passes_the_new_value(monkeypatch: pytest.MonkeyPatch) -> None:
    forwarder = MagicMock()
    monkeypatch.setattr(_proxy, "WINDOW_SIZE", forwarder)
    stub = MagicMock()
    stub.api.side_effect = lambda _name: lambda *_a, **_k: {"newvalue": "off"}

    ProxyPlugin._eventcb_mudwindowsize_change(stub)

    forwarder.set_mode.assert_called_once_with("off")

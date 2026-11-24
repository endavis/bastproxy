"""Tests for the startup gc freeze in MudProxy (#758)."""

import logging
from typing import Any
from unittest.mock import MagicMock

import pytest

import bastproxy
from bastproxy import MudProxy
from bastproxy.libs.api import API as BASEAPI


def test_freeze_gc_freezes(monkeypatch: pytest.MonkeyPatch) -> None:
    freeze = MagicMock()
    monkeypatch.setattr(bastproxy.gcfreeze, "freeze_long_lived_objects", freeze)
    MudProxy._freeze_gc(MagicMock(), {})
    freeze.assert_called_once_with("startup")


def test_freeze_gc_opt_out(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    freeze = MagicMock()
    monkeypatch.setattr(bastproxy.gcfreeze, "freeze_long_lived_objects", freeze)
    with caplog.at_level(logging.INFO):
        MudProxy._freeze_gc(MagicMock(), {"no_gc_freeze": True})
    freeze.assert_not_called()
    assert any("disabled by --no-gc-freeze" in r.getMessage() for r in caplog.records)


def test_run_freezes_after_plugins_before_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    parent = MagicMock()
    startup_seen: list[bool] = []

    def freeze_side_effect(*_a: Any, **_k: Any) -> int:
        startup_seen.append(BASEAPI.startup)
        return 0

    parent.freeze.side_effect = freeze_side_effect
    loader_cls = MagicMock()
    loader_cls.return_value.load_plugins_on_startup = parent.load_plugins_on_startup
    listeners_cls = MagicMock()
    listeners_cls.return_value.create_listeners = parent.create_listeners
    monkeypatch.setattr("bastproxy.libs.plugins.loader.PluginLoader", loader_cls)
    monkeypatch.setattr("bastproxy.libs.net.listeners.Listeners", listeners_cls)
    monkeypatch.setattr(bastproxy, "run_asynch", parent.run_asynch)
    monkeypatch.setattr(bastproxy.gcfreeze, "freeze_long_lived_objects", parent.freeze)
    monkeypatch.setattr(BASEAPI, "startup", True)

    proxy = MagicMock()

    def api(name: str) -> Any:
        if name == "plugins.core.events:event.raise":
            return parent.event_raise
        return MagicMock()

    proxy.api = MagicMock(side_effect=api)
    proxy._freeze_gc = lambda args: MudProxy._freeze_gc(proxy, args)
    MudProxy.run(proxy, {"port": -1, "IPv4_address": "", "no_gc_freeze": False})

    wanted = ("load_plugins_on_startup", "freeze", "event_raise", "create_listeners")
    names = [c[0] for c in parent.mock_calls if c[0] in wanted]
    assert names == ["load_plugins_on_startup", "freeze", "event_raise", "create_listeners"]
    assert startup_seen == [True]

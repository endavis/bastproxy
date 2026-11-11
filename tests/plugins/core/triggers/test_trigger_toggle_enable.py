"""Regression tests for #347: trigger.toggle.enable sets TriggerItem.enabled."""

# Standard Library
from types import SimpleNamespace
from typing import Any

# Third Party
import pytest

# Project
from bastproxy.plugins.core.triggers.plugin import _triggers
from bastproxy.plugins.core.triggers.plugin._triggers import TriggersPlugin

OWNER = "owner"
TRIGGER_ID = "t_owner_trig"


def _make(enabled: bool) -> tuple[Any, SimpleNamespace]:
    trigger = SimpleNamespace(regex_id="rid", enabled=enabled)
    rebuilds: list[int] = []
    fake_self = SimpleNamespace(
        triggers={TRIGGER_ID: trigger},
        regexes={"rid": {"triggers": [TRIGGER_ID] if enabled else []}},
        create_trigger_id=lambda name, owner: f"t_{owner}_{name}",
        rebuild_regexes=lambda: rebuilds.append(1),
        plugin_id="plugins.core.triggers",
        api=lambda name: None,
        rebuilds=rebuilds,
    )
    return fake_self, trigger


def _toggle(fake_self: Any, flag: bool, name: str = "trig") -> None:
    toggle: Any = TriggersPlugin._api_trigger_toggle_enable
    toggle(fake_self, name, flag, owner_id=OWNER)


def test_disabled_trigger_can_be_enabled() -> None:
    fake_self, trigger = _make(enabled=False)
    _toggle(fake_self, True)
    assert trigger.enabled is True
    assert TRIGGER_ID in fake_self.regexes["rid"]["triggers"]
    assert fake_self.rebuilds == [1]


def test_enabled_trigger_can_be_disabled_then_enabled_again() -> None:
    fake_self, trigger = _make(enabled=True)
    _toggle(fake_self, False)
    assert trigger.enabled is False
    assert TRIGGER_ID not in fake_self.regexes["rid"]["triggers"]
    _toggle(fake_self, True)
    assert trigger.enabled is True
    assert TRIGGER_ID in fake_self.regexes["rid"]["triggers"]


def test_unknown_trigger_logs_and_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logged: list[tuple[Any, ...]] = []
    monkeypatch.setattr(_triggers, "log_to", lambda *a, **k: logged.append(a))
    fake_self, _ = _make(enabled=True)
    _toggle(fake_self, True, name="missing")
    assert len(logged) == 1
    assert fake_self.rebuilds == []

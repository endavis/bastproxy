"""Regression tests for #347: trigger.toggle.enable sets TriggerItem.enabled."""

# Standard Library
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

# Third Party
import pytest

# Project
from bastproxy.libs.records.enums import Originated
from bastproxy.libs.records.rtypes.networkdata import NetworkDataLine
from bastproxy.plugins.core.colors.plugin._colors import ColorsPlugin
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


# The issue's reproduction, driven through the real add, toggle and matching code.
_PLUGIN = "plugins.core.triggers"


class _Harness:
    """A stand-in plugin whose add, toggle and matching methods are the real ones."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.raised: list[str] = []
        self.line: Any = None
        raised = self.raised

        def event_raise(event_name: str, event_args: dict[str, Any]) -> dict[str, Any]:
            raised.append(event_name)
            return event_args

        monkeypatch.setattr(_triggers, "API", lambda owner_id: lambda _name: event_raise)
        monkeypatch.setattr(_triggers, "log_to", lambda *a, **k: None)
        quiet = SimpleNamespace(raisetrigger=lambda _args: None)
        self.plugin_id = _PLUGIN
        self.triggers: dict[str, Any] = {"beall": quiet, "all": quiet, "empty": quiet}
        self.beall_id, self.all_id, self.emptyline_id = "beall", "all", "empty"
        self.regexes: dict[str, Any] = {}
        self.regex_lookup_to_id: dict[str, str] = {}
        self.latest_regex_id = 0
        self.created_regex: dict[str, Any] = {"created_regex": "", "created_regex_compiled": ""}
        self.api = lambda _name: lambda *a, **k: {"line": self.line}

    create_trigger_id = staticmethod(TriggersPlugin.create_trigger_id)

    def __getattr__(self, name: str) -> Any:
        method = getattr(TriggersPlugin, name)
        return lambda *a, **k: method(self, *a, **k)

    def send(self, text: str) -> int:
        """Send one MUD line through the real matching path; return the raise count."""
        self.line = NetworkDataLine(text, originated=Originated.MUD)
        before = len(self.raised)
        self._eventcb_check_trigger()
        return len(self.raised) - before


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch) -> _Harness:
    colors = MagicMock()
    colors.plugin_id = "plugins.core.colors"
    table = {
        "plugins.core.colors:ansicode.strip": lambda text: ColorsPlugin._api_ansicode_strip(
            colors, text
        ),
        "plugins.core.colors:ansicode.to.colorcode": lambda text: (
            ColorsPlugin._api_ansicode_to_colorcode(colors, text)
        ),
    }
    monkeypatch.setattr(NetworkDataLine, "api", staticmethod(lambda name: table[name]))
    return _Harness(monkeypatch)


def _add(h: _Harness, enabled: bool) -> None:
    add: Any = TriggersPlugin._api_trigger_add
    success, _item = add(h, "t", r"^starts off$", owner_id=OWNER, enabled=enabled)
    assert success is True


def test_disabled_trigger_fires_only_after_toggle_on(harness: _Harness) -> None:
    _add(harness, enabled=False)
    assert harness.send("starts off") == 0
    _toggle(harness, True, name="t")
    assert harness.send("starts off") == 1
    assert harness.raised == [harness.triggers["t_owner_t"].event_name]
    _toggle(harness, False, name="t")
    assert harness.send("starts off") == 0
    _toggle(harness, True, name="t")
    assert harness.send("starts off") == 1

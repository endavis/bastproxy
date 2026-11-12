"""Tests for omit, remove refusals, unload, stats and the API success paths."""

# Standard Library
import logging
from typing import Any

# Third Party
import pytest

# Project
from bastproxy.plugins.core.triggers.plugin._triggers import TriggersPlugin

from .conftest import OWNER, PLUGIN, Harness

API = "plugins.core.triggers:"


def test_omit_trigger_stops_line_going_to_clients(harness: Harness) -> None:
    """TriggerItem.raisetrigger: omit sets sendtoclients False."""
    harness.add("hide", r"^secret", omit=True)
    assert harness.send("secret stuff") == ["hide"]
    assert harness.line.sendtoclients is False


@pytest.mark.xfail(
    strict=True,
    reason="raisetrigger sets line.sendtoclients, which nothing reads; NetworkDataLine has "
    "line.send (omit is a no-op) - decision pending",
)
def test_omit_trigger_clears_a_flag_the_line_really_uses(harness: Harness) -> None:
    harness.add("hide", r"^secret", omit=True)
    harness.send("secret stuff")
    assert harness.line.send is False


def test_non_omit_trigger_leaves_line_for_clients(harness: Harness) -> None:
    harness.add("show", r"^plain")
    harness.send("plain text")
    assert getattr(harness.line, "sendtoclients", True) is True


def test_toggle_omit_success_then_line_is_omitted(harness: Harness) -> None:
    """trigger.toggle.omit success path, observed through send()."""
    harness.add("t", r"^hello")
    assert harness.api(API + "trigger.toggle.omit")("t", True) is True
    assert harness.item("t").omit is True
    harness.send("hello")
    assert harness.line.sendtoclients is False


def test_toggle_omit_off_keeps_line(harness: Harness) -> None:
    harness.add("t", r"^hello", omit=True)
    assert harness.api(API + "trigger.toggle.omit")("t", False) is True
    harness.send("hello")
    assert getattr(harness.line, "sendtoclients", True) is True


def test_toggle_omit_unknown_returns_false_and_logs(harness: Harness) -> None:
    assert harness.api(API + "trigger.toggle.omit")("missing", True) is False
    assert len(harness.errors()) == 1


def test_get_returns_the_item(harness: Harness) -> None:
    """trigger.get success path."""
    harness.add("g", r"^g")
    assert harness.api(API + "trigger.get")("g") is harness.item("g")


def test_argtypes_converted_through_send(harness: Harness) -> None:
    """argtypes int conversion via send()."""
    harness.add("hp", r"^hp (?P<hp>\d+) (?P<name>\w+)", argtypes={"hp": int})
    harness.send("hp 7 bob")
    assert harness.raised[0][1]["matches"] == {"hp": 7, "name": "bob"}


def test_remove_without_owner_returns_false_and_logs(harness: Harness) -> None:
    """trigger.remove: no owner resolvable."""
    harness.add("r", r"^r")
    harness.owner = None
    harness.logged.clear()
    assert harness.api(API + "trigger.remove")("r") is False
    assert len(harness.errors()) == 1
    assert OWNER not in harness.errors()[0][0] or PLUGIN in harness.errors()[0][0]
    assert "t_plugins.test.owner_r" in harness.triggers


def test_remove_with_explicit_owner_ignores_missing_caller(harness: Harness) -> None:
    harness.add("r", r"^r")
    harness.owner = None
    assert harness.api(API + "trigger.remove")("r", owner_id=OWNER) is True
    assert "t_plugins.test.owner_r" not in harness.triggers


def test_remove_refused_when_event_has_listeners(harness: Harness) -> None:
    """trigger.remove: listeners and force=False."""
    harness.add("r", r"^r")
    harness.listen("r")
    assert harness.api(API + "trigger.remove")("r") is False
    assert len(harness.errors()) == 1
    assert "t_plugins.test.owner_r" in harness.triggers
    assert harness.item("r") in harness._ordered


def test_remove_force_removes_despite_listeners(harness: Harness) -> None:
    harness.add("r", r"^r")
    harness.listen("r")
    assert harness.api(API + "trigger.remove")("r", force=True) is True
    assert "t_plugins.test.owner_r" not in harness.triggers
    assert "r" not in harness.ordered_names()


def test_remove_unknown_returns_false_and_logs(harness: Harness) -> None:
    assert harness.api(API + "trigger.remove")("nope") is False
    assert len(harness.errors()) == 1


def test_remove_succeeds_with_no_listeners(harness: Harness) -> None:
    harness.add("r", r"^r")
    assert harness.api(API + "trigger.remove")("r") is True
    assert harness.send("r") == []


def test_plugin_unloaded_removes_that_plugins_triggers(harness: Harness) -> None:
    """_eventcb_plugin_unloaded."""
    harness.add("a", r"^a")
    harness.add("b", None)
    harness.add("keep", r"^k", owner_id="plugins.test.other")
    harness.current_record = {"plugin_id": OWNER}
    harness._eventcb_plugin_unloaded()
    assert harness.api(API + "trigger.get")("a", OWNER) is None
    assert harness.api(API + "trigger.get")("b", OWNER) is None
    assert harness.item("keep", "plugins.test.other") is not None


def test_plugin_unloaded_without_record_does_nothing(harness: Harness) -> None:
    harness.add("a", r"^a")
    harness.current_record = None
    harness._eventcb_plugin_unloaded()
    assert harness.item("a") is not None


def test_stats_counts_triggers(harness: Harness) -> None:
    """_eventcb_triggers_ev_plugins_stats."""
    harness.add("on", r"^on")
    harness.add("off", r"^off", enabled=False)
    harness.send("on")
    harness.send("on")
    harness.current_record = {"stats": {}}
    harness._eventcb_triggers_ev_plugins_stats()
    stats: Any = harness.current_record["stats"]["Triggers"]
    # 3 disabled built-ins (the harness adds them disabled) plus "off"
    assert stats["Total Triggers"] == 5
    assert stats["Enabled Triggers"] == 1
    assert stats["Disabled Triggers"] == 4
    assert stats["Overall Trigger Hits"] == 2
    assert stats["Triggers Memory Usage"] > 0
    assert stats["showorder"][0] == "Total Triggers"


def test_stats_without_record_does_nothing(harness: Harness) -> None:
    harness.current_record = None
    harness._eventcb_triggers_ev_plugins_stats()


def test_builtins_start_disabled_in_harness_and_enabled_by_initialize(harness: Harness) -> None:
    """The harness mirrors the old default; _phook_initialize adds them enabled."""
    assert harness.item("all", PLUGIN).enabled is False
    harness.triggers.clear()
    harness._ordered.clear()
    original = harness.api
    harness.api = lambda name: (  # type: ignore[method-assign]
        (lambda *a, **k: None) if name == "plugins.core.settings:setting.add" else original(name)
    )
    TriggersPlugin._phook_initialize(harness)
    assert all(harness.item(n, PLUGIN).enabled for n in ("beall", "all", "emptyline"))


def test_errors_helper_only_counts_error_level(harness: Harness) -> None:
    harness.logged.append(([PLUGIN], logging.DEBUG, "x"))
    assert harness.errors() == []

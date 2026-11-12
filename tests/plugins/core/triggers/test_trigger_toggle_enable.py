"""Regression tests for #347: trigger.toggle.enable sets TriggerItem.enabled."""

# Third Party
import pytest

# Project
from .conftest import Harness


def test_disabled_trigger_can_be_enabled(harness: Harness) -> None:
    harness.add("trig", r"^abc", enabled=False)
    assert harness.ordered_names() == []
    harness._api_trigger_toggle_enable("trig", True)
    assert harness.item("trig").enabled is True
    assert harness.ordered_names() == ["trig"]


def test_enabled_trigger_can_be_disabled_then_enabled_again(harness: Harness) -> None:
    harness.add("trig", r"^abc")
    harness._api_trigger_toggle_enable("trig", False)
    assert harness.item("trig").enabled is False
    assert harness.ordered_names() == []
    harness._api_trigger_toggle_enable("trig", True)
    assert harness.item("trig").enabled is True
    assert harness.ordered_names() == ["trig"]


def test_unknown_trigger_logs_and_does_not_raise(harness: Harness) -> None:
    harness._api_trigger_toggle_enable("missing", True)
    assert len(harness.errors()) == 1


def test_toggling_a_regexless_trigger_raises_no_keyerror(harness: Harness) -> None:
    harness.add("plain", None)
    harness._api_trigger_toggle_enable("plain", True)
    harness._api_trigger_toggle_enable("plain", False)
    assert harness.ordered_names() == []


# The issue's reproduction, driven through the real add, toggle and matching code.
def test_disabled_trigger_fires_only_after_toggle_on(harness: Harness) -> None:
    success, _item = harness.add("t", r"^starts off$", enabled=False)
    assert success is True
    assert harness.send("starts off") == []
    harness._api_trigger_toggle_enable("t", True)
    assert harness.send("starts off") == ["t"]
    harness._api_trigger_toggle_enable("t", False)
    assert harness.send("starts off") == []
    harness._api_trigger_toggle_enable("t", True)
    assert harness.send("starts off") == ["t"]


@pytest.mark.parametrize("flag", [True, False])
def test_flag_is_stored_as_bool(harness: Harness, flag: bool) -> None:
    harness.add("trig", r"^abc")
    harness._api_trigger_toggle_enable("trig", flag)
    assert harness.item("trig").enabled is flag

"""Regression tests for #349: group toggle and group membership."""

# Project
from .conftest import OWNER, Harness


def test_group_toggle_disables_every_member(harness: Harness) -> None:
    harness.add("a", r"^one$", group="g")
    harness.add("b", r"^two$", group="g")
    harness._api_group_toggle_enable("g", False)
    assert harness.item("a").enabled is False
    assert harness.item("b").enabled is False
    assert harness.send("one") == []
    assert harness.send("two") == []
    assert harness.errors() == []


def test_group_toggle_enables_every_member(harness: Harness) -> None:
    harness.add("a", r"^one$", group="g", enabled=False)
    harness.add("b", r"^two$", group="g", enabled=False)
    harness._api_group_toggle_enable("g", True)
    assert harness.send("one") == ["a"]
    assert harness.send("two") == ["b"]


def test_group_toggle_leaves_other_triggers_alone(harness: Harness) -> None:
    harness.add("a", r"^one$", group="g")
    harness.add("c", r"^three$")
    harness._api_group_toggle_enable("g", False)
    assert harness.send("three") == ["c"]


def test_remove_drops_id_from_group(harness: Harness) -> None:
    harness.add("a", r"^one$", group="g")
    harness.add("b", r"^two$", group="g")
    trigger_id = harness.create_trigger_id("a", OWNER)
    assert harness._api_trigger_remove("a", force=True) is True
    assert trigger_id not in harness.trigger_groups["g"]
    assert len(harness.trigger_groups["g"]) == 1


def test_group_toggle_after_remove_logs_nothing(harness: Harness) -> None:
    harness.add("a", r"^one$", group="g")
    harness.add("b", r"^two$", group="g")
    harness._api_trigger_remove("a", force=True)
    harness._api_group_toggle_enable("g", False)
    assert harness.send("two") == []
    assert harness.errors() == []


def test_reload_keeps_each_id_once(harness: Harness) -> None:
    trigger_id = harness.create_trigger_id("a", OWNER)
    for _ in range(3):
        harness.add("a", r"^one$", group="g")
        harness._api_trigger_remove_for_owner(OWNER)
    harness.add("a", r"^one$", group="g")
    assert harness.trigger_groups["g"].count(trigger_id) == 1

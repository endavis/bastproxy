"""Tests for #348: trigger.update applies changes instead of raising TypeError."""

# Standard Library
from typing import Any

# Project
from .conftest import Harness

TID = "t_plugins.test.owner_trig"


def _setup(harness: Harness, enabled: bool = True, group: str | None = "g1") -> None:
    harness.add("trig", "foo", enabled=enabled, group=group)


def _update(harness: Harness, data: dict[str, Any], name: str = "trig") -> Any:
    return harness._api_trigger_update(name, data)


def test_simple_attributes(harness: Harness) -> None:
    _setup(harness)
    data = {
        "omit": True,
        "priority": 5,
        "stopevaluating": True,
        "argtypes": {"a": int},
        "matchcolor": True,
    }
    assert _update(harness, data) is True
    for key, value in data.items():
        assert getattr(harness.item("trig"), key) == value


def test_regex_change_matches_new_not_old(harness: Harness) -> None:
    _setup(harness)
    assert _update(harness, {"regex": "(?P<n>bar)\\d"}) is True
    item = harness.item("trig")
    assert item.regex == item.original_regex == "(?P<n>bar)\\d"
    assert item.original_regex_compiled.pattern == "(?P<n>bar)\\d"
    assert harness.send("foo") == []
    assert harness.send("bar1") == ["trig"]
    assert harness.raised[-1][1]["matches"] == {"n": "bar"}
    assert harness.ordered_names() == ["trig"]


def test_regex_change_disabled_trigger_not_added(harness: Harness) -> None:
    _setup(harness, enabled=False)
    assert _update(harness, {"regex": "bar"}) is True
    assert harness.ordered_names() == []
    assert harness.send("bar") == []


def test_invalid_regex_leaves_trigger_untouched(harness: Harness) -> None:
    _setup(harness)
    assert _update(harness, {"regex": "(unclosed", "priority": 1}) is False
    item = harness.item("trig")
    assert item.regex == "foo"
    assert item.regex_id is None
    assert item.original_regex == "foo"
    assert item.priority == 100
    assert harness.send("foo") == ["trig"]


def test_unknown_key_rejected_and_nothing_changed(harness: Harness) -> None:
    _setup(harness)
    assert _update(harness, {"priority": 1, "bogus": 2}) is False
    assert harness.item("trig").priority == 100
    assert not hasattr(harness.item("trig"), "bogus")


def test_group_move_uses_trigger_id(harness: Harness) -> None:
    _setup(harness)
    assert _update(harness, {"group": "g2"}) is True
    assert harness.item("trig").group == "g2"
    assert harness.trigger_groups["g1"] == []
    assert harness.trigger_groups["g2"] == [TID]


def test_group_from_none(harness: Harness) -> None:
    _setup(harness, group=None)
    assert _update(harness, {"group": "g2"}) is True
    assert harness.trigger_groups == {"g2": [TID]}


def test_enabled_off_and_on(harness: Harness) -> None:
    _setup(harness)
    assert _update(harness, {"enabled": False}) is True
    assert harness.item("trig").enabled is False
    assert harness.ordered_names() == []
    assert _update(harness, {"enabled": True}) is True
    assert harness.ordered_names() == ["trig"]


def test_unchanged_value_is_skipped(harness: Harness) -> None:
    _setup(harness)
    before = list(harness._ordered)
    assert _update(harness, {"enabled": True, "regex": "foo"}) is True
    assert harness._ordered == before


def test_priority_change_moves_trigger_and_keeps_order(harness: Harness) -> None:
    _setup(harness)
    harness.add("other", "foo")
    order = harness.item("trig").order
    assert harness.ordered_names() == ["trig", "other"]
    assert _update(harness, {"priority": 500}) is True
    assert harness.ordered_names() == ["other", "trig"]
    assert harness.item("trig").order == order


def test_unknown_trigger(harness: Harness) -> None:
    _setup(harness)
    assert _update(harness, {"priority": 1}, name="nope") is False

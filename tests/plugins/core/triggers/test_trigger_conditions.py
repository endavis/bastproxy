"""Tests for #546: GMCP conditions (``when=``) on triggers."""

# Standard Library
from typing import Any

# Third Party
import pytest

# Project
from bastproxy.plugins.core.triggers.plugin import _conditions
from bastproxy.plugins.core.triggers.plugin._conditions import check, parse_conditions, resolve

from .conftest import Harness


def _holds(spec: str, value: Any, path: str = "Char.Vitals.hp") -> bool:
    cache = {"Char.Vitals": {"hp": value}}
    return check(parse_conditions({path: spec}), cache.get)


@pytest.mark.parametrize(
    ("spec", "value", "expected"),
    [
        (">50", 51, True),
        (">50", 50, False),
        (">=50", 50, True),
        (">=50", 49, False),
        ("<50", 49, True),
        ("<50", 50, False),
        ("<=50", 50, True),
        ("<=50", 51, False),
        ("=50", 50, True),
        ("=50", 50.0, True),
        ("=50", "50", True),
        ("=50", 51, False),
        ("!=50", 51, True),
        ("!=50", 50, False),
        (" >= 50 ", 50, True),
        (">50", "60", True),
        (">50.5", 50.6, True),
        ("=dead", "dead", True),
        ("=dead", "alive", False),
        ("!=dead", "alive", True),
        ("=true", True, True),
        ("=false", False, True),
        ("=true", False, False),
        (">0", True, False),
    ],
)
def test_operators(spec: str, value: Any, expected: bool) -> None:
    assert _holds(spec, value) is expected


@pytest.mark.parametrize("spec", [">1", "<1", ">=1", "<=1"])
def test_non_numeric_value_fails_ordering(spec: str) -> None:
    assert _holds(spec, "abc") is False
    assert _holds(spec, {"a": 1}) is False


@pytest.mark.parametrize("spec", ["=1", "!=1", ">1", "<1", ">=1", "<=1"])
def test_missing_value_fails_every_operator(spec: str) -> None:
    empty: dict[str, Any] = {}
    partial: dict[str, Any] = {"Char.Vitals": {"hp": 1}}
    assert check(parse_conditions({"Char.Vitals.hp": spec}), empty.get) is False
    assert check(parse_conditions({"Char.Vitals.mp": spec}), partial.get) is False
    assert _holds(spec, None) is False
    # a non-dict in the middle of the path
    cache = {"Char.Vitals": {"hp": 5}}
    assert check(parse_conditions({"Char.Vitals.hp.x": spec}), cache.get) is False


def test_longest_package_prefix_wins() -> None:
    cache = {"Char": {"Vitals": {"hp": 1}}, "Char.Vitals": {"hp": 99}}
    assert resolve("Char.Vitals.hp", cache.get) == 99
    assert check(parse_conditions({"Char.Vitals.hp": "=99"}), cache.get) is True


def test_whole_package_path_and_shorter_prefix() -> None:
    cache = {"Char": {"Vitals": {"hp": 7}}}
    assert resolve("Char.Vitals.hp", cache.get) == 7
    assert resolve("Char", cache.get) == {"Vitals": {"hp": 7}}


def test_lookup_is_case_sensitive() -> None:
    assert _holds(">1", 5, path="char.vitals.hp") is False


@pytest.mark.parametrize(
    "when",
    [
        "x",
        ["a"],
        {1: ">1"},
        {"a": 1},
        {"": ">1"},
        {"a..b": ">1"},
        {".a": ">1"},
        {"a": "50"},
        {"a": ">"},
        {"a": "  "},
        {"a": ">abc"},
        {"a": ">50%"},
        {"a": ">nan"},
        {"a": "<inf"},
    ],
)
def test_parse_rejects(when: Any) -> None:
    with pytest.raises(ValueError, match="when"):
        parse_conditions(when)


def test_parse_accepts_nothing_and_whitespace() -> None:
    assert parse_conditions(None) == ()
    assert parse_conditions({}) == ()
    (condition,) = parse_conditions({"a.b": "  >=  1.5 "})
    assert condition.operator == ">="
    assert condition.operand == "1.5"
    assert condition.number == 1.5
    assert _conditions.Condition("a.b", ">=", "1.5", 1.5) == condition


def test_fires_only_when_every_condition_holds(harness: Harness) -> None:
    harness.add("t", "^go", when={"Char.Vitals.hp": ">50", "Char.Status.state": "=fight"})
    harness.gmcp["Char.Vitals"] = {"hp": 60}
    harness.gmcp["Char.Status"] = {"state": "idle"}
    assert harness.send("go") == []
    harness.gmcp["Char.Status"] = {"state": "fight"}
    assert harness.send("go") == ["t"]
    harness.gmcp["Char.Vitals"] = {"hp": 50}
    assert harness.send("go") == []


def test_failed_condition_does_not_hit_log_error_or_stop(harness: Harness) -> None:
    harness.add("first", "^go", priority=1, stopevaluating=True, when={"Char.Vitals.hp": ">50"})
    harness.add("second", "^go", priority=2)
    harness.gmcp["Char.Vitals"] = {"hp": 1}
    assert harness.send("go") == ["second"]
    assert harness.item("first").hits == 0
    assert harness.item("second").hits == 1
    assert harness.errors() == []
    harness.gmcp["Char.Vitals"] = {"hp": 99}
    assert harness.send("go") == ["first"]
    assert harness.item("first").hits == 1


def test_non_matching_regex_does_not_read_gmcp(harness: Harness) -> None:
    harness.add("t", "^go", when={"Char.Vitals.hp": ">50"})
    assert harness.send("stop") == []
    assert harness.gmcp_calls == 0


def test_without_when_gmcp_is_never_read(harness: Harness) -> None:
    harness.add("t", "^go")
    assert harness.item("t").conditions == ()
    assert harness.item("t").when is None
    assert harness.send("go") == ["t"]
    assert harness.gmcp_calls == 0


def test_shared_pattern_conditions_are_per_trigger(harness: Harness) -> None:
    harness.add("a", "^go", when={"Char.Vitals.hp": ">50"})
    harness.add("b", "^go")
    harness.gmcp["Char.Vitals"] = {"hp": 1}
    assert harness.send("go") == ["b"]
    harness.gmcp["Char.Vitals"] = {"hp": 90}
    assert harness.send("go") == ["a", "b"]


@pytest.mark.parametrize("when", ["x", {"a": "50"}, {"a": ">x"}, {1: ">1"}])
def test_add_rejects_bad_when_and_stores_nothing(harness: Harness, when: Any) -> None:
    result = harness.add("bad", "foo", group="grp", when=when)
    assert result.success is False
    assert result.trigger is None
    assert harness.create_trigger_id("bad", "plugins.test.owner") not in harness.triggers
    assert "grp" not in harness.trigger_groups
    assert len(harness.errors()) == 1


def test_add_keeps_a_copy_of_when(harness: Harness) -> None:
    when = {"Char.Vitals.hp": ">50"}
    harness.add("t", "foo", when=when)
    when["Char.Vitals.hp"] = "<1"
    assert harness.item("t").when == {"Char.Vitals.hp": ">50"}

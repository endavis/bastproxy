"""Per-trigger matching: every trigger matches its own regex, in priority order (#346, #359)."""

# Standard Library
from typing import Any

# Third Party
import pytest

# Project
from bastproxy.plugins.core.triggers.plugin import _triggers
from bastproxy.plugins.core.triggers.plugin._triggers import TriggerAddResult

from .conftest import OWNER, PLUGIN, RED_ANSI, RESET_ANSI, Harness


def test_overlapping_triggers_both_fire_in_priority_order(harness: Harness) -> None:
    harness.add("a", r"^You slash (\w+)", priority=200)
    harness.add("b", r"^You slash .*", priority=1)
    assert harness.send("You slash goblin.") == ["b", "a"]


def test_equal_priority_fires_in_order_added(harness: Harness) -> None:
    for name in ("one", "two", "three"):
        harness.add(name, r"^go")
    assert harness.send("go") == ["one", "two", "three"]


def test_updating_priority_reorders_and_keeps_order(harness: Harness) -> None:
    harness.add("one", r"^go")
    harness.add("two", r"^go")
    order_before = harness.item("two").order
    harness._api_trigger_update("two", {"priority": 5})
    assert harness.send("go") == ["two", "one"]
    assert harness.item("two").order == order_before


def test_toggle_off_and_on_keeps_original_order(harness: Harness) -> None:
    harness.add("one", r"^go")
    harness.add("two", r"^go")
    harness._api_trigger_toggle_enable("one", False)
    assert harness.send("go") == ["two"]
    harness._api_trigger_toggle_enable("one", True)
    assert harness.send("go") == ["one", "two"]


def test_stopevaluating_stops_later_trigger_with_other_regex(harness: Harness) -> None:
    harness.add("first", r"^go", stopevaluating=True)
    harness.add("second", r"^g.*")
    harness.listen("all", PLUGIN)
    assert harness.send("go") == ["first", "all"]


def test_stopevaluating_on_nonmatching_trigger_stops_nothing(harness: Harness) -> None:
    harness.add("first", r"^nomatch", stopevaluating=True)
    harness.add("second", r"^go")
    assert harness.send("go") == ["second"]


@pytest.mark.parametrize(
    ("regex", "good", "bad"),
    [
        (r"^(?P<w>\w+) (?P=w)$", "go go", "go stop"),
        (r"^(\w+) \1$", "go go", "go stop"),
    ],
)
def test_backreferences_work(harness: Harness, regex: str, good: str, bad: str) -> None:
    harness.add("back", regex)
    harness.add("after", r"^go")
    assert harness.send(good) == ["back", "after"]
    assert harness.send(bad) == ["after"]


def test_matchcolor_matches_only_colorcoded_text(harness: Harness) -> None:
    harness.add("color", r"^@rWARNING", matchcolor=True)
    harness.add("plain", r"^WARNING")
    colored = f"{RED_ANSI}WARNING{RESET_ANSI}"
    assert harness.send("WARNING", ansi=colored) == ["color", "plain"]
    assert harness.send("WARNING") == ["plain"]


def test_matchcolor_without_flag_does_not_see_color(harness: Harness) -> None:
    harness.add("nocolor", r"^@rWARNING")
    assert harness.send("WARNING", ansi=f"{RED_ANSI}WARNING{RESET_ANSI}") == []


def test_regex_is_anchored_at_the_start(harness: Harness) -> None:
    harness.add("anchored", r"orc")
    harness.add("loose", r".*orc")
    assert harness.send("You hit orc.") == ["loose"]


def test_matches_are_converted_and_per_trigger(harness: Harness) -> None:
    harness.add("a", r"^hp (?P<hp>\d+)", argtypes={"hp": int})
    harness.add("b", r"^hp (?P<other>\d+)")
    harness.send("hp 42")
    matches = [args["matches"] for _name, args in harness.raised]
    assert matches == [{"hp": 42}, {"other": "42"}]


def test_failing_trigger_is_isolated(harness: Harness) -> None:
    harness.add("bad", r"^hp (?P<hp>\w+)", argtypes={"hp": int})
    harness.add("good", r"^hp")
    harness.listen("all", PLUGIN)
    assert harness.send("hp abc") == ["good", "all"]
    errors = harness.errors()
    assert len(errors) == 1
    assert OWNER in errors[0][0]
    assert "t_plugins.test.owner_bad" in errors[0]


def test_failed_trigger_does_not_apply_stopevaluating(harness: Harness) -> None:
    harness.add("bad", r"^hp (?P<hp>\w+)", argtypes={"hp": int}, stopevaluating=True)
    harness.add("good", r"^hp")
    assert harness.send("hp abc") == ["good"]


def test_callback_removing_a_later_trigger(harness: Harness) -> None:
    harness.add("a", r"^go")
    harness.add("b", r"^go")
    harness.callbacks["a"] = lambda: harness._api_trigger_remove("b", force=True)
    assert harness.send("go") == ["a"]
    assert harness.errors() == []
    assert "t_plugins.test.owner_b" not in harness.triggers


def test_none_group_is_not_converted(harness: Harness) -> None:
    harness.add("opt", r"^opt(?: (?P<n>\d+))?$", argtypes={"n": int})
    assert harness.send("opt") == ["opt"]
    assert harness.errors() == []
    assert [args["matches"] for _name, args in harness.raised] == [{"n": None}]


def test_present_optional_group_is_still_converted(harness: Harness) -> None:
    harness.add("opt", r"^opt(?: (?P<n>\d+))?$", argtypes={"n": int})
    assert harness.send("opt 7") == ["opt"]
    assert [args["matches"] for _name, args in harness.raised] == [{"n": 7}]


def test_callback_removing_an_earlier_trigger(harness: Harness) -> None:
    harness.add("a", r"^go")
    harness.add("b", r"^go")
    harness.add("c", r"^go")
    harness.callbacks["b"] = lambda: harness._api_trigger_remove("a", force=True)
    assert harness.send("go") == ["a", "b", "c"]
    assert harness.errors() == []
    assert harness.ordered_names() == ["b", "c"]


def test_callback_removing_its_own_trigger(harness: Harness) -> None:
    harness.add("a", r"^go")
    harness.add("b", r"^go")
    harness.callbacks["a"] = lambda: harness._api_trigger_remove("a", force=True)
    assert harness.send("go") == ["a", "b"]
    assert harness.ordered_names() == ["b"]


def test_callback_disabling_a_later_trigger(harness: Harness) -> None:
    harness.add("a", r"^go")
    harness.add("b", r"^go")
    harness.callbacks["a"] = lambda: harness._api_trigger_toggle_enable("b", False)
    assert harness.send("go") == ["a"]


def test_builtins_need_a_listener(harness: Harness) -> None:
    harness.add("a", r"^go")
    assert harness.send("go") == ["a"]
    assert harness.send("") == []


def test_builtins_fire_in_order_with_listeners(harness: Harness) -> None:
    harness.add("a", r"^go")
    harness.add("b", r"^go", priority=1)
    for name in ("beall", "all", "emptyline"):
        harness.listen(name, PLUGIN)
    assert harness.send("go") == ["beall", "b", "a", "all"]


def test_empty_line_raises_only_emptyline_and_tries_no_regex(harness: Harness) -> None:
    harness.add("any", r"^")
    harness.listen("emptyline", PLUGIN)
    assert harness.send("") == ["emptyline"]


def test_internal_line_raises_nothing(harness: Harness) -> None:
    harness.add("a", r"^go")
    for name in ("beall", "all"):
        harness.listen(name, PLUGIN)
    assert harness.send("go", internal=True) == []


def test_add_compiles_each_regex_once(harness: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    real_compile = _triggers.re.compile

    def counting(pattern: str, *a: Any, **k: Any) -> Any:
        calls.append(pattern)
        return real_compile(pattern, *a, **k)

    monkeypatch.setattr(_triggers.re, "compile", counting)
    for i in range(50):
        harness.add(f"t{i}", rf"^word{i}")
    assert len(calls) == 50


def test_failed_compile_returns_false_and_changes_nothing(harness: Harness) -> None:
    before_triggers = dict(harness.triggers)
    before_ordered = list(harness._ordered)
    assert harness.add("bad", "(unclosed") == TriggerAddResult(False, None)
    assert harness.triggers == before_triggers
    assert harness._ordered == before_ordered


def test_regexless_trigger_remove_and_toggle(harness: Harness) -> None:
    harness.add("plain", None)
    harness._api_trigger_toggle_enable("plain", True)
    assert "plain" not in harness.ordered_names()
    assert harness._api_trigger_remove("plain") is True


def test_item_regex_equals_original_regex(harness: Harness) -> None:
    item = harness.add("named", r"^(?P<w>\w+)").trigger
    assert item.regex == item.original_regex == r"^(?P<w>\w+)"
    assert item.regex_id is None


def test_stats_have_no_regex_rows(harness: Harness) -> None:
    harness.current_record = {"stats": {}}
    harness._eventcb_triggers_ev_plugins_stats()
    rows = harness.current_record["stats"]["Triggers"]
    assert not [key for key in rows if "Regex" in key]
    assert "Total Triggers" in rows


def test_detail_has_no_regex_id_rows(harness: Harness) -> None:
    harness.add("named", r"^go")
    harness.command_args = {"trigger": [harness.item("named").trigger_id]}
    result = harness._command_detail()
    _ok = result.success
    message = result.message
    text = "\n".join(message)
    assert "Regex ID" not in text
    assert "w/o Groups" not in text
    assert "Regex" in text


class _CountingPattern:
    """A compiled pattern stand-in that counts ``match`` calls in a shared list."""

    def __init__(self, compiled: Any, calls: list[str]) -> None:
        self._compiled = compiled
        self._calls = calls
        self.pattern = compiled.pattern
        self.flags = compiled.flags

    def __hash__(self) -> int:
        return hash(self._compiled)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _CountingPattern) and self._compiled == other._compiled

    def match(self, text: str) -> Any:
        self._calls.append(text)
        return self._compiled.match(text)


def _spy(harness: Harness, *names: str) -> list[str]:
    """Wrap the named triggers' compiled patterns; return the shared call list."""
    calls: list[str] = []
    for name in names:
        item = harness.item(name)
        item.original_regex_compiled = _CountingPattern(item.original_regex_compiled, calls)
    return calls


def test_shared_pattern_matches_once_and_all_fire_in_order(harness: Harness) -> None:
    names = [f"dup{i}" for i in range(5)]
    for name in names:
        harness.add(name, r"^You are hungry\.$")
    calls = _spy(harness, *names)
    assert harness.send("You are hungry.") == names
    assert calls == ["You are hungry."]


def test_shared_pattern_that_does_not_match_is_tried_once(harness: Harness) -> None:
    names = ["a", "b", "c"]
    for name in names:
        harness.add(name, r"^You are hungry\.$")
    calls = _spy(harness, *names)
    assert harness.send("You are full.") == []
    assert len(calls) == 1


def test_shared_pattern_keeps_stopevaluating(harness: Harness) -> None:
    harness.add("one", r"^go", stopevaluating=True)
    harness.add("two", r"^go")
    assert harness.send("go") == ["one"]


def test_same_pattern_different_matchcolor_matches_separately(harness: Harness) -> None:
    harness.add("plain", r"^WARNING")
    harness.add("color", r"^WARNING", matchcolor=True)
    harness.add("plain2", r"^WARNING")
    calls = _spy(harness, "plain", "color", "plain2")
    colored = f"{RED_ANSI}WARNING{RESET_ANSI}"
    # the colour-coded text starts with a colour code, so only the plain variants match
    assert harness.send("WARNING", ansi=colored) == ["plain", "plain2"]
    assert len(calls) == 2
    assert calls[0] != calls[1]


def test_argtypes_on_one_duplicate_do_not_change_another(harness: Harness) -> None:
    harness.add("typed", r"^hp (?P<hp>\d+)", argtypes={"hp": int})
    harness.add("raw", r"^hp (?P<hp>\d+)")
    harness.add("typed2", r"^hp (?P<hp>\d+)", argtypes={"hp": float})
    calls = _spy(harness, "typed", "raw", "typed2")
    harness.send("hp 42")
    assert len(calls) == 1
    seen = {args["trigger_name"]: args["matches"] for _e, args in harness.raised}
    assert seen["typed"] == {"hp": 42}
    assert seen["raw"] == {"hp": "42"}
    assert seen["typed2"] == {"hp": 42.0}
    assert seen["typed"] is not seen["raw"]


def test_shared_flag_follows_add_update_toggle_and_remove(harness: Harness) -> None:
    harness.add("a", r"^go")
    assert harness.item("a").shared_pattern is False
    harness.add("b", r"^go")
    assert harness.item("a").shared_pattern is True
    assert harness.item("b").shared_pattern is True
    harness.add("c", r"^go")
    assert harness.item("c").shared_pattern is True

    # a different regex leaves the group; two remain shared
    harness._api_trigger_update("c", {"regex": r"^stop"})
    assert harness.item("c").shared_pattern is False
    assert harness.item("a").shared_pattern is True

    # toggling one of two off leaves the other unshared, and on shares them again
    harness._api_trigger_toggle_enable("b", False)
    assert harness.item("a").shared_pattern is False
    assert harness.item("b").shared_pattern is False
    harness._api_trigger_toggle_enable("b", True)
    assert harness.item("a").shared_pattern is True
    assert harness.item("b").shared_pattern is True

    # removing one of two leaves the survivor unshared
    harness._api_trigger_remove("b")
    assert harness.item("a").shared_pattern is False


def test_matching_is_correct_after_each_shared_change(harness: Harness) -> None:
    harness.add("a", r"^go")
    harness.add("b", r"^go")
    harness._api_trigger_update("b", {"regex": r"^stop"})
    assert harness.send("go") == ["a"]
    assert harness.send("stop") == ["b"]
    harness._api_trigger_update("b", {"regex": r"^go"})
    assert harness.send("go") == ["a", "b"]
    harness._api_trigger_toggle_enable("a", False)
    assert harness.send("go") == ["b"]
    harness._api_trigger_toggle_enable("a", True)
    harness._api_trigger_remove("a")
    calls = _spy(harness, "b")
    assert harness.send("go") == ["b"]
    assert len(calls) == 1
    assert harness.item("b").shared_pattern is False


def test_unshared_trigger_is_matched_directly(harness: Harness) -> None:
    harness.add("a", r"^go")
    harness.add("b", r"^stop")
    calls = _spy(harness, "a", "b")
    assert harness.send("go") == ["a"]
    assert len(calls) == 2


def test_matchcolor_update_changes_sharing(harness: Harness) -> None:
    harness.add("a", r"^go")
    harness.add("b", r"^go", matchcolor=True)
    assert harness.item("a").shared_pattern is False
    harness._api_trigger_update("b", {"matchcolor": False})
    assert harness.item("a").shared_pattern is True
    assert harness.item("b").shared_pattern is True

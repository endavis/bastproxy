"""Tests for #348: trigger.update applies changes instead of raising TypeError."""

# Standard Library
from functools import partial
from types import SimpleNamespace
from typing import Any

# Project
from bastproxy.plugins.core.triggers.plugin._triggers import TriggerItem, TriggersPlugin

OWNER = "plugins.test.owner"
TID = f"t_{OWNER}_trig"


def _make(enabled: bool = True, group: str | None = "g1") -> Any:
    fake: Any = SimpleNamespace(plugin_id="plugins.core.triggers")
    fake.api = lambda name: lambda **_kw: OWNER
    fake.triggers = {}
    fake.regexes = {}
    fake.regex_lookup_to_id = {}
    fake.trigger_groups = {}
    fake.created_regex = {}
    fake.latest_regex_id = 0
    fake.rebuild_count = 0
    fake.create_trigger_id = TriggersPlugin.create_trigger_id
    fake.create_regex_id = partial(TriggersPlugin.create_regex_id, fake)
    fake.find_regex_id = partial(TriggersPlugin.find_regex_id, fake)
    real_rebuild = partial(TriggersPlugin.rebuild_regexes, fake)

    def rebuild() -> None:
        fake.rebuild_count += 1
        real_rebuild()

    fake.rebuild_regexes = rebuild

    regex_id = fake.find_regex_id("foo")
    item = TriggerItem(
        OWNER, "trig", "foo", regex_id, "foo", enabled=enabled, group=group, trigger_id=TID
    )
    fake.triggers[TID] = item
    if enabled:
        fake.regexes[regex_id]["triggers"].append(TID)
    if group:
        fake.trigger_groups[group] = [TID]
    return fake


def _update(fake: Any, data: dict[str, Any], name: str = "trig") -> Any:
    update: Any = TriggersPlugin._api_trigger_update
    return update(fake, name, data)


def test_simple_attributes() -> None:
    fake = _make()
    data = {
        "omit": True,
        "priority": 5,
        "stopevaluating": True,
        "argtypes": {"a": int},
        "matchcolor": True,
    }
    assert _update(fake, data) is True
    for key, value in data.items():
        assert getattr(fake.triggers[TID], key) == value


def test_regex_change_moves_entry_and_recompiles() -> None:
    fake = _make()
    old_id = fake.triggers[TID].regex_id
    assert _update(fake, {"regex": "(?P<n>bar)\\d"}) is True
    item = fake.triggers[TID]
    assert item.regex == "(bar)\\d"
    assert item.original_regex == "(?P<n>bar)\\d"
    assert item.original_regex_compiled.pattern == "(?P<n>bar)\\d"
    assert item.regex_id != old_id
    assert TID not in fake.regexes[old_id]["triggers"]
    assert fake.regexes[item.regex_id]["triggers"] == [TID]
    assert "bar" in fake.created_regex["created_regex"]
    assert fake.rebuild_count == 1


def test_regex_change_disabled_trigger_not_added() -> None:
    fake = _make(enabled=False)
    assert _update(fake, {"regex": "bar"}) is True
    assert fake.regexes[fake.triggers[TID].regex_id]["triggers"] == []


def test_invalid_regex_leaves_trigger_untouched() -> None:
    fake = _make()
    old_id = fake.triggers[TID].regex_id
    assert _update(fake, {"regex": "(unclosed", "priority": 1}) is False
    item = fake.triggers[TID]
    assert item.regex == "foo"
    assert item.regex_id == old_id
    assert item.original_regex == "foo"
    assert item.priority == 100
    assert fake.regexes[old_id]["triggers"] == [TID]
    assert len(fake.regexes) == 1


def test_unknown_key_rejected_and_nothing_changed() -> None:
    fake = _make()
    assert _update(fake, {"priority": 1, "bogus": 2}) is False
    assert fake.triggers[TID].priority == 100
    assert not hasattr(fake.triggers[TID], "bogus")


def test_group_move_uses_trigger_id() -> None:
    fake = _make()
    assert _update(fake, {"group": "g2"}) is True
    assert fake.triggers[TID].group == "g2"
    assert fake.trigger_groups["g1"] == []
    assert fake.trigger_groups["g2"] == [TID]


def test_group_from_none() -> None:
    fake = _make(group=None)
    assert _update(fake, {"group": "g2"}) is True
    assert fake.trigger_groups == {"g2": [TID]}


def test_enabled_off_and_on() -> None:
    fake = _make()
    regex_id = fake.triggers[TID].regex_id
    assert _update(fake, {"enabled": False}) is True
    assert fake.triggers[TID].enabled is False
    assert fake.regexes[regex_id]["triggers"] == []
    assert fake.created_regex["created_regex"] == ""
    assert _update(fake, {"enabled": True}) is True
    assert fake.regexes[regex_id]["triggers"] == [TID]
    assert "foo" in fake.created_regex["created_regex"]


def test_unchanged_value_is_skipped() -> None:
    fake = _make()
    assert _update(fake, {"enabled": True, "regex": "foo"}) is True
    assert fake.rebuild_count == 0


def test_unknown_trigger() -> None:
    fake = _make()
    assert _update(fake, {"priority": 1}, name="nope") is False

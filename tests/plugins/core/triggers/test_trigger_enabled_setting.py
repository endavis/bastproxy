"""The plugin's ``enabled`` setting stops and starts matching (#356)."""

# Project
from .conftest import Harness


def set_enabled(harness: Harness, value: bool, old: object = True) -> None:
    """Deliver the setting's modified event to the real handler."""
    harness.current_record = {"var": "enabled", "newvalue": value, "oldvalue": old}
    harness._eventcb_enabled_modify()


def test_disabled_setting_stops_matching_and_reenable_resumes(harness: Harness) -> None:
    fired: list[str] = []
    harness.add("a", r"^You slash")
    harness.callbacks["a"] = lambda: fired.append("a")

    set_enabled(harness, False)
    assert harness.send("You slash goblin.") == []
    assert fired == []

    set_enabled(harness, True, old=False)
    assert harness.send("You slash goblin.") == ["a"]
    assert fired == ["a"]


def test_disabled_setting_skips_builtin_raises(harness: Harness) -> None:
    for name in ("beall", "all", "emptyline"):
        harness.listeners.add(harness.item(name, "plugins.core.triggers").event_name)

    set_enabled(harness, False)
    assert harness.send("anything") == []
    assert harness.send("") == []

    set_enabled(harness, True, old=False)
    assert "beall" in harness.send("anything")


def test_value_saved_false_at_startup_applies_before_any_line(harness: Harness) -> None:
    """The load-time raise carries oldvalue "__init__"; it must still disable matching."""
    harness.add("a", r"^You slash")

    set_enabled(harness, False, old="__init__")

    assert harness.send("You slash goblin.") == []

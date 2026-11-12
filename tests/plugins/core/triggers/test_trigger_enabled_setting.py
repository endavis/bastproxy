"""The plugin's ``enabled`` setting stops and starts matching (#356)."""

# Project
from .conftest import Harness


def test_disabled_setting_stops_matching_and_reenable_resumes(harness: Harness) -> None:
    fired: list[str] = []
    harness.add("a", r"^You slash")
    harness.callbacks["a"] = lambda: fired.append("a")

    harness.setting_enabled = False
    assert harness.send("You slash goblin.") == []
    assert fired == []

    harness.setting_enabled = True
    assert harness.send("You slash goblin.") == ["a"]
    assert fired == ["a"]


def test_disabled_setting_skips_builtin_raises(harness: Harness) -> None:
    for name in ("beall", "all", "emptyline"):
        harness.listeners.add(harness.item(name, "plugins.core.triggers").event_name)

    harness.setting_enabled = False
    assert harness.send("anything") == []
    assert harness.send("") == []

    harness.setting_enabled = True
    assert "beall" in harness.send("anything")

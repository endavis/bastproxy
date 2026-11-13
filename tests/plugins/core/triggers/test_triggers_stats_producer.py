"""The triggers stats reader feeds the plugin.stats.get result (#466)."""

from typing import Any

from .conftest import Harness


def test_triggers_section_added_to_stats(harness: Harness) -> None:
    harness.add("on", r"^on")
    stats: dict[str, Any] = {}
    harness.current_record = {"plugin_id": harness.plugin_id, "stats": stats}

    harness._eventcb_triggers_ev_plugins_stats()

    assert "Triggers" in stats
    assert stats["Triggers"]["showorder"][0] == "Total Triggers"

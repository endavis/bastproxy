"""The stats callbacks must register to the event ``plugin.stats.get`` raises (#637)."""

from typing import Any

import pytest

from bastproxy.plugins.core.timers.plugin._timers import TimersPlugin
from bastproxy.plugins.core.triggers.plugin._triggers import TriggersPlugin

PID = "plugins.test.a"


@pytest.mark.parametrize(
    ("plugin_class", "callback"),
    [
        (TimersPlugin, "_eventcb_timers_ev_plugins_stats"),
        (TriggersPlugin, "_eventcb_triggers_ev_plugins_stats"),
    ],
)
def test_stats_callback_registers_to_raised_event(plugin_class: Any, callback: str) -> None:
    registrations = getattr(plugin_class, callback).event_registration
    # the events plugin formats the name with the plugin instance's attributes
    names = [item["event_name"].format(plugin_id=PID) for item in registrations]

    # _api_plugin_stats_get raises f"ev_{plugin_id}_stats"
    assert names == [f"ev_{PID}_stats"]

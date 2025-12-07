# Project: bastproxy
# Filename: plugins/debug/apihelp/_apihelp.py
#
# File Description: a plugin to show api functions and details
#
# By: Bast
"""A plugin to test mud triggers"""
# Standard Library

# 3rd Party

# Project
from bastproxy.plugins._baseplugin import BasePlugin, RegisterPluginHook


class TriggerExPlugin(BasePlugin):
    """a plugin to test triggers"""

    @RegisterPluginHook("initialize")
    def _phook_triggerex_initialize(self):
        """Register a test trigger to capture say events."""
        success, trigger = self.api("plugins.core.triggers:trigger.add")(
            "test_say", r"^(?P<object>.*) says, \"(?P<message>.*)\"$"
        )
        if success:
            self.api("plugins.core.triggers:trigger.register")(
                trigger.trigger_id, self._trigger_say
            )

    def _trigger_say(self):
        """Handle the test trigger by echoing the parsed event."""
        if event_record := self.api("plugins.core.events:get.current.event.record")():
            print(f"_trigger_say - {event_record}")
        else:
            print("_trigger_say - No event record")

        if event_record["matches"]["message"] == "block":
            event_record["line"].send = False
        else:
            event_record[
                "line"
            ].line = f"{event_record['matches']['object']} said something!!!!! ({event_record['matches']['message']})"

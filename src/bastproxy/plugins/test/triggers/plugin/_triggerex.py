# Project: bastproxy
# Filename: plugins/debug/apihelp/_apihelp.py
#
# File Description: a plugin to show api functions and details
#
# By: Bast
"""
A plugin to test mud triggers
"""
# Standard Library

# 3rd Party

# Project
from plugins._baseplugin import BasePlugin, RegisterPluginHook
from plugins.core.events import RegisterToEvent

class TriggerExPlugin(BasePlugin):
    """
    a plugin to test triggers
    """
    @RegisterPluginHook('initialize')  
    def _phook_triggerex_initialize(self):
        """
        """
        success, trigger = self.api('plugins.core.triggers:trigger.add')('test_say', r"^(?P<object>.*) says, \"(?P<message>.*)\"$" )
        if success:
            self.api('plugins.core.triggers:trigger.register')(trigger.trigger_id, self._trigger_say)

    def _trigger_say(self):
        """
        """
        if event_record := self.api(
            'plugins.core.events:get.current.event.record'
        )():
            print(f"_trigger_say - {event_record}")
        else:
            print("_trigger_say - No event record")

        if event_record['matches']['message'] == 'block':
            event_record['line'].send = False
        else:
            event_record['line'].line = f"{event_record['matches']['object']} said something!!!!! ({event_record['matches']['message']})"
    

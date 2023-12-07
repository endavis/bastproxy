# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/events/_init_.py
#
# File Description: a plugin to handle events
#
# By: Bast
"""
This plugin handles events.
  You can register/unregister with events, raise events

## Using
### Registering an event from a plugin
 * ```self.api('plugins.core.events:register.to.event')(event_name, function, prio=50)```

### Unregistering an event
 * ```self.api('plugins.core.events:unregister.from.event')(event_name, function)```

### Raising an event
 * ```self.api('plugins.core.events:raise.event')(event_name, eventdictionary)```
"""

# these 4 are required
PLUGIN_NAME = 'Event Handler'
PLUGIN_PURPOSE = 'Handle events'
PLUGIN_AUTHOR = 'Bast'
PLUGIN_VERSION = 1

PLUGIN_REQUIRED = True

__all__ = ['Plugin']

from ._events import EventsPlugin as Plugin

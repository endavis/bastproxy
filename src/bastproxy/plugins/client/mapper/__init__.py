# Project: bastproxy
# Filename: plugins/client/mapper/__init__.py
#
# File Description: a plugin that stores the map, finds paths and walks them
#
# By: Bast
"""Stores rooms, areas and exits, finds the cheapest path and walks it (ADR-0021).

A game plugin feeds it rooms with ``room.add``, tells it where the character is with
``room.current.set`` and registers how exit requirements and movement work. See
docs/client/mapper.md.
"""

# these 4 are required
PLUGIN_NAME = "Mapper"
PLUGIN_PURPOSE = "store the map, find paths and walk them"
PLUGIN_AUTHOR = "Bast"
PLUGIN_VERSION = 1

# plugins that must be loaded (and initialized) before this one
PLUGIN_DEPENDENCIES = ["plugins.core.sqldb", "plugins.core.commands"]

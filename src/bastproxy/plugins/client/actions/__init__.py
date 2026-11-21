# Project: bastproxy
# Filename: plugins/client/actions/__init__.py
#
# File Description: a plugin that runs commands when MUD output matches a regex
#
# By: Bast
"""Stores user actions and runs their commands when MUD output matches."""

# these 4 are required
PLUGIN_NAME = "Actions"
PLUGIN_PURPOSE = "run commands when a line of MUD output matches a regex"
PLUGIN_AUTHOR = "Bast"
PLUGIN_VERSION = 1

# plugins that must be loaded (and initialized) before this one
PLUGIN_DEPENDENCIES = ["plugins.core.commands", "plugins.core.triggers"]

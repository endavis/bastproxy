# Project: bastproxy
# Filename: plugins/client/substitutes/__init__.py
#
# File Description: a plugin that rewrites text in MUD output before it reaches the client
#
# By: Bast
"""Stores user substitutions and rewrites matching text in MUD output."""

# these 4 are required
PLUGIN_NAME = "Substitutes"
PLUGIN_PURPOSE = "rewrite text in MUD output before it reaches the client"
PLUGIN_AUTHOR = "Bast"
PLUGIN_VERSION = 1

# plugins that must be loaded (and initialized) before this one
PLUGIN_DEPENDENCIES = ["plugins.core.commands", "plugins.core.colors"]

# Project: bastproxy
# Filename: plugins/client/variables/__init__.py
#
# File Description: a plugin that stores user variables and expands them in client input
#
# By: Bast
"""Stores user variables and expands %{name} references in client input."""

# these 4 are required
PLUGIN_NAME = "Variables"
PLUGIN_PURPOSE = "store named values and expand them in client input"
PLUGIN_AUTHOR = "Bast"
PLUGIN_VERSION = 1

# plugins that must be loaded (and initialized) before this one
PLUGIN_DEPENDENCIES = ["plugins.core.commands"]

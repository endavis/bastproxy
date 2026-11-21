# Project: bastproxy
# Filename: plugins/client/loop/__init__.py
#
# File Description: a plugin that runs a line a number of times
#
# By: Bast
"""Runs a line a number of times through the input path."""

# these 4 are required
PLUGIN_NAME = "Loop"
PLUGIN_PURPOSE = "run a line a number of times"
PLUGIN_AUTHOR = "Bast"
PLUGIN_VERSION = 1

# plugins that must be loaded (and initialized) before this one
PLUGIN_DEPENDENCIES = ["plugins.core.commands"]

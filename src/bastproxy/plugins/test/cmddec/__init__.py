# Project: bastproxy
# Filename: plugins/test/cmddec/_init_.py
#
# File Description: a plugin to test command decorators
#
# By: Bast
"""This plugin is to test command decorators"""

# these 4 are required
PLUGIN_NAME = "Test command decorators"
PLUGIN_PURPOSE = "Test command decorators"
PLUGIN_AUTHOR = "Bast"
PLUGIN_VERSION = 1

__all__ = ["Plugin"]

from ._plugin import CMDDecPlugin as Plugin

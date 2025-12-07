# Project: bastproxy
# Filename: plugins/test/sqldb/_init_.py
#
# File Description: a plugin to test the sqldb plugin
#
# By: Bast
"""
This plugin is used to test the sqldb plugin
"""

# these 4 are required
PLUGIN_NAME = 'Test SQLDB plugin'
PLUGIN_PURPOSE = 'Test sqldb plugin'
PLUGIN_AUTHOR = 'Bast'
PLUGIN_VERSION = 1

__all__ = ['Plugin']

from ._plugin import SQLDBPlugin as Plugin

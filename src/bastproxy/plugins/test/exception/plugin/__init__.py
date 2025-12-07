# Project: bastproxy
# Filename: plugins/test/exception/_init_.py
#
# File Description: a plugin to test exception handling
#
# By: Bast
"""
This plugin is an example plugin to show how to use gmcp
"""

# these 4 are required
PLUGIN_NAME = 'Testing Exceptions'
PLUGIN_PURPOSE = 'Testing raising Exceptions'
PLUGIN_AUTHOR = 'Bast'
PLUGIN_VERSION = 1


__all__ = ['Plugin']

from ._plugin import ExceptionPlugin as Plugin

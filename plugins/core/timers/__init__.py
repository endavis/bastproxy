# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/timers/_init_.py
#
# File Description: a plugin to handle timers
#
# By: Bast
"""
this plugin has a timer interface for internal timers
"""

# these 4 are required
PLUGIN_NAME = 'timers'
PLUGIN_PURPOSE = 'handle timers'
PLUGIN_AUTHOR = 'Bast'
PLUGIN_VERSION = 1

PLUGIN_REQUIRED = True

__all__ = ['Plugin']

from ._plugin import TimersPlugin as Plugin

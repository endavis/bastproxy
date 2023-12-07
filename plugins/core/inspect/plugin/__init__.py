# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/inspect/_init_.py
#
# File Description: a plugin to inspect plugin internals
#
# By: Bast
"""
This plugin will show api functions and details
"""

# these 4 are required
PLUGIN_NAME = 'Inspect Proxy Internals'
PLUGIN_PURPOSE = 'see info about records and other internal proxy functions'
PLUGIN_AUTHOR = 'Bast'
PLUGIN_VERSION = 1

__all__ = ['Plugin']

from ._inspect import InspectPlugin as Plugin

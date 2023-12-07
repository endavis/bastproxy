# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/_pluginm/_init_.py
#
# File Description: holds the plugin manager
#
# By: Bast
"""
manages all plugins
"""

# these 4 are required
PLUGIN_NAME = 'Plugin Manager'
PLUGIN_PURPOSE = 'Manage plugins'
PLUGIN_AUTHOR = 'Bast'
PLUGIN_VERSION = 1

PLUGIN_REQUIRED = True

__all__ = ['Plugin']

from ._pluginm import PluginManager as Plugin

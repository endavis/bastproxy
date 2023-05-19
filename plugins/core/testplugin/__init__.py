# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/testplugin/_init_.py
#
# File Description: a plugin to test the new import functionality
#
# By: Bast

# these 4 are required
PLUGIN_NAME = 'Test Plugin'
PLUGIN_PURPOSE = 'a test plugin for new import functionality'
PLUGIN_AUTHOR = 'Bast'
PLUGIN_VERSION = 1

__all__ = ['Plugin']

from ._plugin import Plugin

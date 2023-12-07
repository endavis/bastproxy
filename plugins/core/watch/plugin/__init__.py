# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/watch/_init_.py
#
# File Description: a plugin to watch for commands from the client
#
# By: Bast
"""
This plugin will handle watching for commands coming from the client
"""
# these 4 are required
PLUGIN_NAME = 'Command Watch'
PLUGIN_PURPOSE = 'watch for specific commands from clients'
PLUGIN_AUTHOR = 'Bast'
PLUGIN_VERSION = 1

PLUGIN_REQUIRED = True

__all__ = ['Plugin']

from ._watch import WatchPlugin as Plugin

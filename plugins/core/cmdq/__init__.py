# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/cmdq/_init_.py
#
# File Description: a command queue plugin
#
# By: Bast
"""
this plugin creates a command queue

see the aardwolf eq plugin for examples of how to use it
"""
# these 4 are required
PLUGIN_NAME = 'Command Queue'
PLUGIN_PURPOSE = 'Queue commands to the mud'
PLUGIN_AUTHOR = 'Bast'
PLUGIN_VERSION = 1

PLUGIN_REQUIRED = True

__all__ = ['Plugin']

from ._plugin import CMDQPlugin as Plugin

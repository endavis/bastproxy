# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/managers/_init_.py
#
# File Description: a plugin to keep up with managers
#
# By: Bast
"""
This plugin holds keeps up with various managers
"""

# these 4 are required
PLUGIN_NAME = 'Managers'
PLUGIN_PURPOSE = 'keep up with managers'
PLUGIN_AUTHOR = 'Bast'
PLUGIN_VERSION = 1
PLUGIN_REQUIRED = True

__all__ = ['Plugin']

from ._plugin import ManagersPlugin as Plugin

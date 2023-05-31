# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/settings/__init__.py
#
# File Description: a plugin to manage all settings
#
# By: Bast
"""
This module handles commands and parsing input
"""

# these 4 are required
PLUGIN_NAME = 'Settings'
PLUGIN_PURPOSE = 'Plugin to handle settings'
PLUGIN_AUTHOR = 'Bast'
PLUGIN_VERSION = 1

__all__ = ['Plugin']

from ._settingsplugin import SettingsPlugin

class Plugin(SettingsPlugin):
    pass

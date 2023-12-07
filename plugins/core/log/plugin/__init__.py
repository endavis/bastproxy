# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/log/_init_.py
#
# File Description: a plugin to change logging settings
#
# By: Bast
"""
This module handles changing logging settings

see info/logging_notes.txt for more information about logging
"""

# these 4 are required
PLUGIN_NAME = 'Logging'
PLUGIN_PURPOSE = 'Handles changing and testing of logging configuration'
PLUGIN_AUTHOR = 'Bast'
PLUGIN_VERSION = 1

PLUGIN_REQUIRED = True

__all__ = ['Plugin']

from ._log import LogPlugin as Plugin

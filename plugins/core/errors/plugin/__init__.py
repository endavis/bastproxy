# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/errors/_init_.py
#
# File Description: a plugin to handle errors
#
# By: Bast
"""
This plugin shows and clears errors seen during plugin execution
"""

# these 4 are required
PLUGIN_NAME = 'Error Plugin'
PLUGIN_PURPOSE = 'show and manage errors'
PLUGIN_AUTHOR = 'Bast'
PLUGIN_VERSION = 1

PLUGIN_REQUIRED = True

__all__ = ['Plugin']

from ._errors import ErrorPlugin as Plugin

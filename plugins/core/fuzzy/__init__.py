# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/fuzzy/_init_.py
#
# File Description: a plugin to do fuzzy matching with strings
#
# By: Bast
"""
This plugin holds an api to do fuzzy matching
"""

# these 4 are required
PLUGIN_NAME = 'Fuzzy Match'
PLUGIN_PURPOSE = 'do fuzzy matching'
PLUGIN_AUTHOR = 'Bast'
PLUGIN_VERSION = 1

PLUGIN_REQUIRED = True

__all__ = ['Plugin']

from ._fuzzy import FuzzyPlugin as Plugin

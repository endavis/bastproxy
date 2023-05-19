# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/apihelp/_init_.py
#
# File Description: a plugin to show api functions and details
#
# By: Bast
"""
This plugin will show api functions and details
"""
# these 4 are required
PLUGIN_NAME = 'API help'
PLUGIN_PURPOSE = 'show info about the api'
PLUGIN_AUTHOR = 'Bast'
PLUGIN_VERSION = 1

__all__ = ['Plugin']

from ._plugin import APIHelpPlugin as Plugin

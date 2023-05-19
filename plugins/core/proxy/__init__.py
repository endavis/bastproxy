# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/proxy/_init_.py
#
# File Description: a plugin to handle settings and information about the proxy
#
# By: Bast
"""
This plugin will show information about connections to the proxy
"""

# these 4 are required
PLUGIN_NAME = 'Proxy Interface'
PLUGIN_PURPOSE = 'control the proxy'
PLUGIN_AUTHOR = 'Bast'
PLUGIN_VERSION = 1

PLUGIN_REQUIRED = True

__all__ = ['Plugin']

from ._plugin import ProxyPlugin as Plugin

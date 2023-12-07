# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/clients/_init_.py
#
# File Description: a plugin to hold information about clients
#
# By: Bast
"""
This plugin will show information about clients connected to the proxy
"""

# these 4 are required
PLUGIN_NAME = 'Clients'
PLUGIN_PURPOSE = 'manage clients'
PLUGIN_AUTHOR = 'Bast'
PLUGIN_VERSION = 1

PLUGIN_REQUIRED = True

__all__ = ['Plugin']

from ._clients import ClientPlugin as Plugin

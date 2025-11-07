# Project: bastproxy
# Filename: plugins/core/log/_init_.py
#
# File Description: a plugin to change logging settings
#
# By: Bast
"""
This plugin handles changing logging settings

see info/logging_notes.txt for more information about logging
"""

# these 4 are required
PLUGIN_NAME = 'Logging'
PLUGIN_PURPOSE = 'Handles changing and testing of logging configuration'
PLUGIN_AUTHOR = 'Bast'
PLUGIN_VERSION = 1

PLUGIN_REQUIRED = True

__ALL__ = ["formatTime_RFC3339", "formatTime_RFC3339_UTC", "get_toplevel"]

from .libs.tz import formatTime_RFC3339, formatTime_RFC3339_UTC
from .libs.utils import get_toplevel

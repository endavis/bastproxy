# Project: bastproxy
# Filename: plugins/core/log/_init_.py
#
# File Description: a plugin to change logging settings
#
# By: Bast
"""This plugin handles changing logging settings.

see info/logging_notes.txt for more information about logging
"""

# these 4 are required
PLUGIN_NAME = "Logging"
PLUGIN_PURPOSE = "Handles changing and testing of logging configuration"
PLUGIN_AUTHOR = "Bast"
PLUGIN_VERSION = 1

PLUGIN_REQUIRED = True

__ALL__ = ["format_time_rfc3339", "format_time_rfc3339_utc", "get_toplevel"]

from .libs.tz import format_time_rfc3339, format_time_rfc3339_utc
from .libs.utils import get_toplevel

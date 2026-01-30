# Project: bastproxy
# Filename: plugins/debug/async/_init_.py
#
# File Description: a test plugin
#
# By: Bast
"""This plugin is for testing things"""

import pprint

# these 4 are required
PLUGIN_NAME = "New tracking object test"
PLUGIN_PURPOSE = "a plugin to test the new tracking object"
PLUGIN_AUTHOR = "Bast"
PLUGIN_VERSION = 1


def log(msg, level="info"):
    """Log a message for the new tracking object test plugin."""
    if not isinstance(msg, str):
        pass
    else:
        print(msg)

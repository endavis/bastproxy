# Project: bastproxy
# Filename: plugins/debug/async/_init_.py
#
# File Description: a test plugin
#
# By: Bast
"""
This plugin is for testing things
"""
import pprint

# these 4 are required
PLUGIN_NAME = 'New tracking object test'
PLUGIN_PURPOSE = 'a plugin to test the new tracking object'
PLUGIN_AUTHOR = 'Bast'
PLUGIN_VERSION = 1

def log(msg, level='info'):
    if not isinstance(msg, str):
        pprint.pprint(msg)
    else:
        print(msg)

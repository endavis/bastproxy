# Project: bastproxy
# Filename: plugins/test/_sqldb/plugin/__init__.py
#
# File Description: a plugin to test the sqldb plugin
#
# By: Bast
__all__ = ["Plugin"]

from ._sqldb import SQLDBPlugin as Plugin

# Project: bastproxy
# Filename: plugins/debug/gmcp/plugin/__init__.py
#
# File Description: a plugin to inspect and send GMCP
#
# By: Bast
__all__ = ["Plugin"]

from ._gmcp import GMCPPlugin as Plugin

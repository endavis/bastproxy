# Project: bastproxy
# Filename: plugins/core/web/plugin/__init__.py
#
# File Description: a plugin that serves web pages for plugins
#
# By: Bast

__all__ = ["Plugin"]

from ._web import WebPlugin as Plugin

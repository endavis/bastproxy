# Project: bastproxy
# Filename: plugins/client/actions/plugin/__init__.py
#
# File Description: a plugin that runs commands when MUD output matches a regex
#
# By: Bast

__all__ = ["Plugin"]

from ._actions import ActionsPlugin as Plugin

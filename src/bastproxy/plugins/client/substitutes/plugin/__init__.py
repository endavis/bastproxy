# Project: bastproxy
# Filename: plugins/client/substitutes/plugin/__init__.py
#
# File Description: a plugin that rewrites text in MUD output before it reaches the client
#
# By: Bast

__all__ = ["Plugin"]

from ._substitutes import SubstitutesPlugin as Plugin

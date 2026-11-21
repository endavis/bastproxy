# Project: bastproxy
# Filename: plugins/client/aliases/plugin/__init__.py
#
# File Description: a plugin that stores user aliases and expands them in client input
#
# By: Bast

__all__ = ["Plugin"]

from ._aliases import AliasesPlugin as Plugin

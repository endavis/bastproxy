# Project: bastproxy
# Filename: plugins/client/variables/plugin/__init__.py
#
# File Description: a plugin that stores user variables and expands them in client input
#
# By: Bast

__all__ = ["Plugin"]

from ._variables import VariablesPlugin as Plugin

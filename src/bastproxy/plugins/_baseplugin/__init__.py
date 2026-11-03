# Project: bastproxy
# Filename: plugins/_baseplugin/__init__.py
#
# File Description: holds the BasePlugin class
#
# By: Bast
"""This module holds the class BasePlugin, which all plugins should have as.

their base class.
"""

__all__ = ["BasePlugin", "RegisterPluginHook"]

from ._base import Plugin
from .libs._commands import Commands
from .libs._pluginhooks import RegisterPluginHook
from .libs._settings import Settings


class BasePlugin(Plugin, Commands, Settings):
    pass

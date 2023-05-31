# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/_baseplugin/_init_.py
#
# File Description: holds the BasePlugin class
#
# By: Bast
"""
This module holds the class BasePlugin, which all plugins should have as
their base class.
"""

__all__ = ['BasePlugin', 'RegisterPluginHook', 'patch']

from ._base import Base
from ._commands import Commands
from ._pluginhooks import RegisterPluginHook
from ._patch import patch

class BasePlugin(Base, Commands):
    pass

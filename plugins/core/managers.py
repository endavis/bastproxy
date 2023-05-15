# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/managers.py
#
# File Description: a plugin to keep up with managers
#
# By: Bast
"""
This plugin holds keeps up with various managers
"""
# Standard Library

# 3rd Party

# Project
from plugins._baseplugin import BasePlugin

NAME = 'Managers'
SNAME = 'managers'
PURPOSE = 'keep up with managers'
AUTHOR = 'Bast'
VERSION = 1
REQUIRED = True

class Plugin(BasePlugin):
    """
    a plugin to test command parsing
    """
    def __init__(self, *args, **kwargs):
        """
        init the instance
        """
        super().__init__(*args, **kwargs)

        self.api('libs.api:add')(self.plugin_id, 'add', self._api_add)
        self.api('libs.api:add')(self.plugin_id, 'get', self._api_get)

    # get a manager
    def _api_get(self, name):
        """  get a manager
        @Yname@w  = the name of the manager to get

        this function returns the manager instance"""
        return self.api.MANAGERS[name] if name in self.api.MANAGERS else None

    # add a manager
    def _api_add(self, name, manager):
        """  add a manager
        @Yname@w  = the name of the manager
        @Ymanager@w  = the manager instance

        this function returns no values"""
        self.api.MANAGERS[name] = manager

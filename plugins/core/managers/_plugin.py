# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/managers/_plugin.py
#
# File Description: a plugin to keep up with managers
#
# By: Bast

# Standard Library

# 3rd Party

# Project
from plugins._baseplugin import BasePlugin
from libs.api import AddAPI

class ManagersPlugin(BasePlugin):
    """
    a plugin to test command parsing
    """
    @AddAPI('get', description='get a manager')
    def _api_get(self, name):
        """  get a manager
        @Yname@w  = the name of the manager to get

        this function returns the manager instance"""
        return self.api.MANAGERS[name] if name in self.api.MANAGERS else None

    @AddAPI('add', description='add a manager')
    def _api_add(self, name, manager):
        """  add a manager
        @Yname@w  = the name of the manager
        @Ymanager@w  = the manager instance

        this function returns no values"""
        self.api.MANAGERS[name] = manager

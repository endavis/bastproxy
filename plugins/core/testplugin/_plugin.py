# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/testplugin/_plugin.py
#
# File Description: a plugin to test the new import functionality
#
# By: Bast
from plugins._baseplugin import BasePlugin
from libs.commands import AddParser

class Plugin(BasePlugin):
    """
    a plugin to test new import functionality
    """
    @AddParser(description='a test command')
    def _command_test(self):
        """
        a test command
        """
        return True, ['@Rtest@w @x165command@w with @Gcolors@w and @x206colors@w']
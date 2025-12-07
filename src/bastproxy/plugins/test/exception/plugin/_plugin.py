# Project: bastproxy
# Filename: plugins/test/exception/_plugin.py
#
# File Description: a plugin to test exception handling
#
# By: Bast

from plugins._baseplugin import BasePlugin
from plugins.core.commands import AddParser

class ExceptionPlugin(BasePlugin):
    """
    a plugin to raise a test exception
    """
    @AddParser(description='raise an exception', add_help=False)
    def _command_raise(self):  # sourcery skip: raise-specific-error
        """
        test errors
        """
        raise Exception('@Rtest@w @x165error@w with @Gcolors@w and @x206colors@w')

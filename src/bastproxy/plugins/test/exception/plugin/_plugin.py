# Project: bastproxy
# Filename: plugins/test/exception/_plugin.py
#
# File Description: a plugin to test exception handling
#
# By: Bast

from bastproxy.plugins._baseplugin import BasePlugin
from bastproxy.plugins.core.commands import AddParser


class TestPluginError(Exception):
    """Raised when the exception test plugin is triggered."""


class ExceptionPlugin(BasePlugin):
    """a plugin to raise a test exception"""

    @AddParser(description="raise an exception", add_help=False)
    def _command_raise(self):  # sourcery skip: raise-specific-error
        """Test errors"""
        msg = "@Rtest@w @x165error@w with @Gcolors@w and @x206colors@w"
        raise TestPluginError(msg)

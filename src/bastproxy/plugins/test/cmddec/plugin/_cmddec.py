# Project: bastproxy
# Filename: plugins/test/cmddec/plugin/_cmddec.py
#
# File Description: a plugin to test command decorators
#
# By: Bast

# Standard Library

# 3rd Party

# Project
from bastproxy.plugins._baseplugin import BasePlugin
from bastproxy.plugins.core.commands import AddParser, CommandResult


class CMDDecPlugin(BasePlugin):
    """a plugin to test command decorators"""

    @AddParser(description="raise a test error")
    def _command_raise(self):
        """Test errors"""
        return CommandResult(True, ["@Rtest@w @x165error@w with @Gcolors@w and @x206colors@w"])

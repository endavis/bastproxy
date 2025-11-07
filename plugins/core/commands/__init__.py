# Project: bastproxy
# Filename: plugins/core/commands/_init_.py
#
# File Description: a plugin for handling command parsing and execution
#
# By: Bast
"""This plugin handles commands and parsing input.

All commands are #bp.[package].[plugin].[command] or #bp.[plugin].[command]

Commands are stored in a dictionary in the source plugin, use #bp.<plugin>.inspect -o data:commands -s
    to find what's in the dictionary
$cmd{'#bp.client.actions.inspect -o data.commands -s'}
"""

# these 4 are required
PLUGIN_NAME = "Commands"
PLUGIN_PURPOSE = "Parse and handle commands"
PLUGIN_AUTHOR = "Bast"
PLUGIN_VERSION = 1

PLUGIN_REQUIRED = True

__all__ = ["AddArgument", "AddCommand", "AddParser", "set_command_autoadd"]

from .libs._utils import AddArgument, AddCommand, AddParser, set_command_autoadd

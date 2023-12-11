# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/commands/plugin/_init_.py
#
# File Description: a plugin for handling command parsing and execution
#
# By: Bast
"""
This plugin handles commands and parsing input

All commands are #bp.[package].[plugin].[command] or #bp.[plugin].[command]

Commands are stored in a dictionary in the source plugin, use #bp.<plugin>.inspect -o data:commands -s
    to find what's in the dictionary
$cmd{'#bp.client.actions.inspect -o data.commands -s'}
"""
__all__ = ['Plugin']

from ._commands import CommandsPlugin as Plugin

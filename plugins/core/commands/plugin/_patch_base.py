# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/commands/plugin/_patch_base.py
#
# File Description: adds stats to the base plugin
#
# By: Bast

# Standard Library

# 3rd Party

# Project
from plugins._baseplugin import RegisterPluginHook

CANRELOAD = False

@RegisterPluginHook('stats')
def _phook_command_stats(self, **kwargs):    # pyright: ignore[reportInvalidTypeVarUse]
    """
    get statistics for commands
    """
    kwargs['stats']['Commands'] = {
        'Number of Commands': self.api(
            'plugins.core.commands:get.command.count'
        )(self.plugin_id),
        'showorder': ['Number of Commands'],
    }
    return kwargs

# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/debug/plugins/plugin/_plugins.py
#
# File Description: a plugin to debug other plugins
#
# By: Bast

# Standard Library

# 3rd Party

# Project
from plugins._baseplugin import BasePlugin
from plugins.core.commands import AddParser, AddArgument

class PluginsPlugin(BasePlugin):
    """
    a plugin to debug other plugins
    """
    @AddParser(description='dump the internals of a plugin')
    @AddArgument('plugin',
                    help='the plugin to inspect',
                    default='')
    @AddArgument('-o',
                    '--object',
                    help='show an object of the plugin, can be method or variable',
                    default='')
    @AddArgument('-s',
                    '--simple',
                    help='show a simple output',
                    action='store_true')
    def _command_dump(self):
        """
        dump a plugin object or attribute
        """
        args = self.api('plugins.core.commands:get.current.command.args')()

        if not args['plugin']:
            return False, ['Please enter a plugin name']

        if not self.api('libs.pluginloader:is.plugin.id')(args['plugin']):
            return True, [f'Plugin {args["plugin"]} not found']

        return True, self.api(f"{args['plugin']}:dump")(args['object'], args['simple'])[1]

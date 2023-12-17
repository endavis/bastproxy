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
            return False, ['Please enter a plugin id']

        if not self.api('libs.pluginloader:is.plugin.id')(args['plugin']):
            return True, [f'Plugin {args["plugin"]} not found']

        return True, self.api(f"{args['plugin']}:dump")(args['object'], args['simple'])[1]

    @AddParser(description='show internal plugin hooks')
    @AddArgument('plugin',
                    help='the plugin to show the hooks for',
                    default='')
    def _command_hooks(self):
        """
        @G%(name)s@w - @B%(cmdname)s@w
        show internal plugin hooks
        @CUsage@w: hooks
        """
        args = self.api('plugins.core.commands:get.current.command.args')()

        if not args['plugin']:
            return False, ['Please enter a plugin name']

        tmsg = []

        hooks = self.api(f'{args["plugin"]}:get.plugin.hooks')()

        tmsg.extend(self.api('plugins.core.commands:format.output.header')(f'Plugin Hooks for {args["plugin"]}'))

        for hook in hooks:
            tmsg.extend(self.api('plugins.core.commands:format.output.subheader')(f'{hook}'))
            priorities = hooks[hook].keys()
            priorities = sorted(list(priorities))
            for priority in priorities:
                tmsg.extend(f"{priority:<5} : {item}" for item in hooks[hook][priority])
            tmsg.append('')

        return True, tmsg

    @AddParser(description='show plugin stats')
    @AddArgument('plugin',
                    help='the plugin to show the hooks for',
                    default='')
    def _command_stats(self):
        """
        @G%(name)s@w - @B%(cmdname)s@w
        show stats, memory, profile, etc.. for this plugin
        @CUsage@w: stats
        """

        args = self.api('plugins.core.commands:get.current.command.args')()

        if not args['plugin']:
            return False, ['Please enter a plugin name']

        stats = self.api(f'{args["plugin"]}:get.stats')()
        tmsg = []
        for header in stats:
            tmsg.append(self.api('plugins.core.utils:center.colored.string')(header, '=', 60))
            tmsg.extend(
                f"{subtype:<20} : {stats[header][subtype]}"
                for subtype in stats[header]['showorder']
            )
            tmsg.append('')
        return True, tmsg

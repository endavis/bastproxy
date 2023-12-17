# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/_baseplugin/_commands.py
#
# File Description: holds commands for the base plugin
#
# By: Bast
# Standard Library
from typing import TypeVar, Protocol, Generic
import sys

# 3rd Party

# Project
from plugins.core.commands import AddCommand, AddParser, AddArgument, set_command_autoadd
from ._pluginhooks import RegisterPluginHook

t_Plugin = TypeVar('t_Plugin', bound='Plugin', contravariant=True) # pyright: ignore[reportUndefinedVariable]

class Commands(Protocol, Generic[t_Plugin]):
    @RegisterPluginHook('initialize')
    def _phook_base_post_initialize_add_reset_command(self: t_Plugin):
        """
        add commands to the plugin
        """
        if self.can_reset_f:
            set_command_autoadd(self._command_reset, True)

    @AddCommand(group='Base')
    @AddParser(description='show help info for this plugin')
    @AddArgument('-a',
                    '--api',
                    help='show functions this plugin has in the api',
                    action='store_true')
    @AddArgument('-c',
                    '--commands',
                    help='show commands in this plugin',
                    action='store_true')
    def _command_help(self: t_Plugin):
        """
        @G%(name)s@w - @B%(cmdname)s@w
        show the help for this plugin
        @CUsage@w: help
        """
        args = self.api('plugins.core.commands:get.current.command.args')()
        width = 25

        msg = [
            f"{'Plugin ID':<{width}} : {self.plugin_id}",
            f"{'Name':<{width}} : {self.plugin_info.name}",
            f"{'Purpose':<{width}} : {self.plugin_info.purpose}",
            f"{'Author':<{width}} : {self.plugin_info.author}",
            f"{'Version':<{width}} : {self.plugin_info.version}",
            f"{'Package':<{width}} : {self.plugin_info.package}",
            f"{'Full Plugin Path':<{width}} : {self.plugin_info.package_path}",
            f"{'Time Loaded':<{width}} : {self.loaded_time.strftime(self.api.time_format)}",
        ]

        import_location = self.plugin_info.package_import_location

        if doc := sys.modules[import_location].__doc__:
            msg.extend(doc.split('\n'))

        if msg[-1] == '' and msg[-2] == '':
            msg.pop()

        file_header = False
        for file in self.api('libs.pluginloader:plugin.get.changed.files')(self.plugin_id):
            if not file_header:
                file_header = True
                if msg[-1] != '':
                    msg.append('')
                msg.append(self.api('plugins.core.utils:center.colored.string')('@x86Files that have change since loading@w', '-', 60, filler_color='@B'))
            msg.append(f"    : {file}")
        if file_header:
            msg.append('@B' + '-' * 60 + '@w')

        file_header = False
        for file in self.api('libs.pluginloader:plugin.get.invalid.python.files')(self.plugin_id):
            if not file_header:
                file_header = True
                if msg[-1] != '':
                    msg.append('')
                msg.append(self.api('plugins.core.utils:center.colored.string')('@x86Files that are invalid python@w', '-', 60, filler_color='@B'))
            msg.append(f"    : {file}")
        if file_header:
            msg.append('@B' + '-' * 60 + '@w')

        if msg[-1] != '':
            msg.append('')

        if args['commands']:
            cmd_output = self.api('plugins.core.commands:list.commands.formatted')(self.plugin_id)
            msg.extend(cmd_output)
            msg.extend(('@G' + '-' * 60 + '@w', ''))
        if args['api']:
            if api_list := self.api('libs.api:list')(self.plugin_id):
                msg.extend((f"API functions in {self.plugin_id}", '@G' + '-' * 60 + '@w'))
                msg.extend(api_list)
        return True, msg

    @AddCommand(group='Base')
    @AddParser(description='save the plugin state')
    def _command_save(self: t_Plugin):
        """
        @G%(name)s@w - @B%(cmdname)s@w
        save plugin state
        @CUsage@w: save
        """
        self.api(f"{self.plugin_id}:save.state")()
        return True, ['Plugin settings saved']

    @AddCommand(group='Base', autoadd=False)
    @AddParser(description='reset the plugin')
    def _command_reset(self: t_Plugin):
        """
        @G%(name)s@w - @B%(cmdname)s@w
          reset the plugin
          @CUsage@w: reset
        """
        if self.can_reset_f:
            plugins_that_acted = self.api(f"{self.plugin_id}:reset")()
            msg = [
                    'Plugin reset',
                    '',
                    f"Plugins that {self.plugin_id}'s data was reset for:",
                    *[f"    {plugin}" for plugin in plugins_that_acted]
            ]
            return True, msg

        return True, ['This plugin cannot be reset']


# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/settings/_set_cmd.py
#
# File Description: holds the set command to add to BasePlugin
#
# By: Bast

# Standard Library
import textwrap

# 3rd Party

# Project
import libs.argp as argp
from libs.api import AddAPI
from plugins._baseplugin import RegisterPluginHook
from libs.commands import AddCommand, AddParser, AddArgument

@AddCommand(group='Base', name='set', show_in_history=False)
@AddParser(formatter_class=argp.RawDescriptionHelpFormatter,
        description=textwrap.dedent("""
            change a setting in the plugin

            if there are no arguments or 'list' is the first argument then
            it will list the settings for the plugin"""))
@AddArgument('name',
                help='the setting name',
                default='list',
                nargs='?')
@AddArgument('value',
                help='the new value of the setting',
                default='',
                nargs='?')
def _command_settings_plugin_set(self):
    """
    @G%(name)s@w - @B%(cmdname)s@w
    List or set vars
    @CUsage@w: var @Y<varname>@w @Y<varvalue>@w
        @Yname@w    = The setting to set
        @Yvalue@w   = The value to set it to
        if there are no arguments or 'list' is the first argument then
        it will list the settings for the plugin
    """
    args = self.api('plugins.core.commands:get.current.command.args')()

    if not args['name'] or args['name'] == 'list':
        return True, self.api('plugins.core.settings:get.all.settings.formatted')(self.plugin_id)

    arg_string = f"-p {self.plugin_id} {args.arg_string}"
    return self.api('plugins.core.commands:run')('plugins.core.settings', 'sets', argument_string=arg_string)

@RegisterPluginHook('reset')
def _settings_plugin_reset(self):
    """
    reset settings data
    """
    if self.can_reset_f:
        self.reset_f = True
        self.api('plugins.core.settings:reset')(self.plugin_id)
        self.reset_f = False

@RegisterPluginHook('post_initialize', priority=5)
def _settings_plugin_hook_post_initialize(self):
    """
    setup the settings for the plugin
    """
    self.reset_f = False

    self.api('plugins.core.settings:initialize.plugin.settings')(self.plugin_id)
    self.api('plugins.core.settings:raise.event.all.settings')(self.plugin_id)

@RegisterPluginHook('save')
def _settings_plugin_save(self):
    """
    save all settings for the plugin
    """
    self.api('plugins.core.settings:save.plugin')(self.plugin_id)

@AddAPI('setting.get', description='get the value of a setting')
def _api_settings_plugin_get(self, setting):
    return self.api('plugins.core.settings:get')(self.plugin_id, setting)

@AddAPI('setting.change', description='change the value of a setting')
def _api_settings_plugin_change(self, setting, value):
    return self.api('plugins.core.settings:change')(self.plugin_id, setting, value)

@AddAPI('setting.add', description='add a setting to the plugin')
def _api_settings_plugin_add(self, name, default, stype, help, **kwargs):
    self.api('plugins.core.settings:add')(self.plugin_id, name, default=default, stype=stype, help=help, **kwargs)

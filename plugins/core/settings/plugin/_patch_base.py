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
from plugins._baseplugin import RegisterPluginHook
from plugins.core.events import RegisterToEvent
from plugins.core.commands import AddCommand, AddParser, AddArgument

CANRELOAD = False

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
    retval, return_string = self.api('plugins.core.commands:run')('plugins.core.settings',
                                                                  'pset',
                                                                  argument_string=arg_string)

    return True, return_string

@RegisterPluginHook('reset')
def _phook_settings_reset(self):
    """
    reset settings data
    """
    if self.can_reset_f:
        self.reset_f = True
        self.api('plugins.core.settings:reset')(self.plugin_id)
        self.reset_f = False

@RegisterPluginHook('initialize', priority=75)
def _phook_settings_post_initialize(self):
    """
    setup the settings for the plugin
    """
    self.reset_f = False

    self.api('plugins.core.settings:initialize.plugin.settings')(self.plugin_id)

@RegisterToEvent(event_name="ev_{plugin_id}_initialized")
def _eventcb_raise_event_all_settings(self):
    """
    raise all events for settings
    """
    self.api('plugins.core.settings:raise.event.all.settings')(self.plugin_id)

@RegisterPluginHook('save')
def _phook_settings_save(self):
    """
    save all settings for the plugin
    """
    self.api('plugins.core.settings:save.plugin')(self.plugin_id)

@RegisterPluginHook('uninitialize', priority=100)
def _phook_settings_uninitialize(self):
    """
    remove the settings for the plugin
    """
    self.api('plugins.core.settings:remove.plugin.settings')(self.plugin_id)

# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/_baseplugin/_settings.py
#
# File Description: holds the settings implementation
#
# By: Bast

# Standard Library
from typing import TypeVar
from pathlib import Path
import contextlib
import textwrap

# 3rd Party

# Project
import libs.argp as argp
from libs.api import AddAPI
from libs.persistentdict import PluginPersistentDict
from libs.commands import AddCommand, AddParser, AddArgument
from ._pluginhooks import RegisterPluginHook

Base = TypeVar('Base', bound='Base')

class Settings:
    @RegisterPluginHook('post_base_init', priority=1)
    def _loadevent_post_initialize_add_settings(self: Base): # pyright: ignore[reportInvalidTypeVarUse]
        """
        add settings to the plugin
        """
        self.settings_file: Path = self.data_directory / 'settingvalues.txt'

        self.reset_f = True

        self.settings = {}
        self.setting_values = PluginPersistentDict(self.plugin_id, self.settings_file, 'c')
        self.setting_values.pload()

    @AddAPI('setting.get', description='get the value of a setting')
    def _api_setting_get(self: Base, setting): # pyright: ignore[reportInvalidTypeVarUse]
        """  get the value of a setting
        @Ysetting@w = the setting value to get
        @Yplugin@w = the plugin to get the setting from (optional)

        returns:
          the value of the setting, None if not found"""
        with contextlib.suppress(KeyError):
            return (
                self.api('plugins.core.utils:verify.value')(
                    self.setting_values[setting],
                    self.settings[setting]['stype'],
                )
                if self.api('libs.api:has')('plugins.core.utils:verify.value')
                else self.setting_values[setting]
            )

        return None

    @AddAPI('setting.change', description='change the value of a setting')
    def _api_setting_change(self: Base, setting, value): # pyright: ignore[reportInvalidTypeVarUse]
        """  change a setting
        @Ysetting@w    = the name of the setting to change
        @Yvalue@w      = the value to set it as

        returns:
          True if the value was changed, False otherwise"""
        if value == 'default':
            value = self.settings[setting]['default']
        if setting in self.settings:
            if self.api('libs.pluginloader:is.plugin.loaded')('utils'):
                value = self.api('plugins.core.utils:verify.value')(
                    value,
                    self.settings[setting]['stype'])

            self.setting_values[setting] = value
            self.setting_values.sync()
            return True

        return False

    @AddAPI('setting.add', description='add a setting to the plugin')
    def _api_setting_add(self: Base, name, default, stype, shelp, **kwargs): # pyright: ignore[reportInvalidTypeVarUse]
        """  remove a command
        @Yname@w     = the name of the setting
        @Ydefault@w  = the default value of the setting
        @Ystype@w    = the type of the setting
        @Yshelp@w    = the help associated with the setting
        Keyword Arguments
          @Ynocolor@w    = if True, don't parse colors when showing value
          @Yreadonly@w   = if True, can't be changed by a client
          @Yhidden@w     = if True, don't show in @Ysettings@w command"""

        nocolor_f = kwargs.get('nocolor', False)
        readonly_f = kwargs.get('readonly', False)
        hidden_f = kwargs.get('hidden', False)
        if name not in self.setting_values:
            self.setting_values[name] = default
        self.settings[name] = {
            'default':default,
            'help':shelp,
            'stype':stype,
            'nocolor':nocolor_f,
            'readonly':readonly_f,
            'hidden':hidden_f
        }

    @AddAPI('setting.is.hidden', description='get the value of a setting')
    def _api_setting_is_hidden(self: Base, setting): # pyright: ignore[reportInvalidTypeVarUse]
        """  get the value of a setting
        @Ysetting@w = the setting value to get
        @Yplugin@w = the plugin to get the setting from (optional)

        returns:
          the value of the setting, None if not found"""
        if setting in self.settings:
            return self.settings[setting]['hidden']

    def _list_vars(self: Base): # pyright: ignore[reportInvalidTypeVarUse]
        """
        returns:
         a list of strings that list all settings
        """
        tmsg = []
        if not self.setting_values:
            tmsg.append('There are no settings defined')
        else:
            for i in self.settings:
                if self.settings[i]['hidden']:
                    continue
                columnwidth = 15
                val = self.setting_values[i]
                help = self.settings[i]['help']
                if 'nocolor' in self.settings[i] and self.settings[i]['nocolor']:
                    val = val.replace('@', '@@')
                elif self.settings[i]['stype'] == 'color':
                    tlen = len(val)
                    columnwidth = 18 + tlen
                    help = f"{val}{help}@w"
                    val = f"{val}{val.replace('@', '@@')}@w"
                elif self.settings[i]['stype'] == 'timelength':
                    val = self.api('plugins.core.utils:format.time')(
                        self.api('plugins.core.utils:verify.value')(val, 'timelength'))
                tmsg.append(f"{i:<20} : {val:<{columnwidth}} - {help}")
        return tmsg

    @RegisterPluginHook('reset')
    def _settings_reset(self: Base): # pyright: ignore[reportInvalidTypeVarUse]
        """
        internal function to reset settings data
        """
        if self.can_reset_f:
            self.reset_f = True
            self.setting_values.clear()
            for i in self.settings:
                self.setting_values[i] = self.settings[i]['default']
            self.setting_values.sync()
            self.reset_f = False

    @RegisterPluginHook('pre_initialize')
    def _load_hook_pre_initialize(self: Base): # pyright: ignore[reportInvalidTypeVarUse]
        """
        initialize the plugin, do most things here
        """
        self.api('plugins.core.events:register.to.event')('ev_libs.net.mud_muddisconnect', self._eventcb_baseplugin_disconnect)

        self.reset_f = False

        for i in self.settings:
            self.api('plugins.core.events:add.event')(f"ev_{self.plugin_id}_var_{i}_modified", self.plugin_id,
                                description=f"An event to modify the setting {i}",
                                arg_descriptions={'var':'the variable that was modified',
                                                    'newvalue':'the new value',
                                                    'oldvalue':'the old value'})

    @RegisterPluginHook('post_initialize')
    def _load_hook_post_initialize_raise_all_settings(self):
        # go through each variable and raise var_%s_changed
        self.setting_values.raiseall()

    @RegisterPluginHook('save')
    def _settings_save(self):
        """
        save all settings for the plugin
        make sure to call this in any methods
        of a subclass that overrides this
        """
        self.setting_values.sync()

    @AddCommand(group='Base', show_in_history=False)
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
    def _command_set(self: Base): # pyright: ignore[reportInvalidTypeVarUse]
        """
        @G%(name)s@w - @B%(cmdname)s@w
        List or set vars
        @CUsage@w: var @Y<varname>@w @Y<varvalue>@w
          @Ysettingname@w    = The setting to set
          @Ysettingvalue@w   = The value to set it to
          if there are no arguments or 'list' is the first argument then
          it will list the settings for the plugin
        """
        args = self.api('plugins.core.commands:get.current.command.args')()
        msg = []
        if args['name'] == 'list':
            return True, self._list_vars()
        elif args['name'] and args['value']:
            var = args['name']
            if var in self.settings:
                if 'readonly' in self.settings[var] \
                          and self.settings[var]['readonly']:
                    return True, [f"{var} is a readonly setting"]
                val = args['value']
                try:
                    self.api(f"{self.plugin_id}:setting.change")(var, val)
                    tvar = self.setting_values[var]
                    if self.settings[var]['nocolor']:
                        tvar = tvar.replace('@', '@@')
                    elif self.settings[var]['stype'] == 'color':
                        tvar = f"{tvar}{tvar.replace('@', '@@')}@w"
                    elif self.settings[var]['stype'] == 'timelength':
                        tvar = self.api('plugins.core.utils:format.time')(
                            self.api('plugins.core.utils:verify.value')(tvar, 'timelength'))
                    return True, [f"{var} is now set to {tvar}"]
                except ValueError:
                    msg = [f"Cannot convert {val} to {self.settings[var]['stype']}"]
                    return True, msg

            else:
                msg = [f"plugin setting {var} does not exist"]
        return False, msg


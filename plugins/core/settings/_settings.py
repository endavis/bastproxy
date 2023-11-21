# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/example/_settings.py
#
# File Description: an example plugin
#
# By: Bast
# Standard Library
import contextlib
import textwrap
from pathlib import Path

# 3rd Party

# Project
from libs.api import AddAPI
import libs.argp as argp
from libs.persistentdict import PersistentDict, convert
from libs.records import LogRecord
from libs.commands import AddParser, AddArgument, AddCommand
from plugins._baseplugin import BasePlugin, patch
from . import _patch_base

# patch the base class with any function in the _patch_base module
patch(_patch_base)

class SettingsPlugin(BasePlugin):
    """
    a test plugin
    """
    def __init__(self, *args, **kwargs):
        """
        initialize the instance through common __init__ method
        """
        super().__init__(*args, **kwargs)
        self.settings_map = {}
        self.settings_info = {}
        self.settings_values = {}

    @AddAPI('add', description='add a setting to a plugin')
    def _api_add(self, plugin_id, setting_name, default, stype, help, **kwargs):
        """
        @Yplugin_id@w     = the plugin_id of the owner of the setting
        @Ysetting_name@w  = the name of the setting
        @Ydefault@w    = the default value of the setting
        @Ystype@w      = the type of the setting
        @Yshelp@w      = the help associated with the setting
        Keyword Arguments
          @Ynocolor@w    = if True, don't parse colors when showing value
          @Yreadonly@w   = if True, can't be changed by a client
          @Yhidden@w     = if True, don't show in @Ysettings@w command
          @Yaftersetmessage@w = message to send to client after setting is changed
        """
        if plugin_id not in self.settings_info:
            self.settings_info[plugin_id] = {}
        if setting_name in self.settings_info[plugin_id]:
            LogRecord(f"setting {plugin_id}.{setting_name} already exists", level='error',
                      sources=[self.plugin_id])()
            return

        setting_info = {
            'default': default,
            'help': help,
            'stype': stype,
            'nocolor': kwargs.get('nocolor', False),
            'readonly': kwargs.get('readonly', False),
            'hidden': kwargs.get('hidden', False),
            'aftersetmessage': kwargs.get('aftersetmessage', '')
        }

        if not setting_info['hidden']:
            if setting_name in self.settings_map:
                LogRecord(f"setting {setting_name} already exists in {self.settings_map[setting_name]}", level='error',
                      sources=[self.plugin_id])()

                return

            self.settings_map[setting_name] = plugin_id

        if plugin_id not in self.settings_values:
            data_directory = self.api(f"{plugin_id}:get.data.directory")()
            settings_file: Path = data_directory / 'settingvalues.txt'
            self.settings_values[plugin_id] = PersistentDict(plugin_id, settings_file, 'c')

        if setting_name not in self.settings_values[plugin_id]:
            self.settings_values[plugin_id][setting_name] = setting_info['default']

        self.settings_info[plugin_id][setting_name] = setting_info

    @AddAPI('get', description='get the value of a setting')
    def _api_setting_get(self, plugin_id, setting):
        """  get the value of a setting
        @Ysetting@w = the setting value to get
        @Yplugin@w = the plugin to get the setting from (optional)

        returns:
          the value of the setting, None if not found"""

        returnval = None

        with contextlib.suppress(KeyError):
            returnval = (
                self.api('plugins.core.utils:verify.value')(
                    self.settings_values[plugin_id][setting],
                    self.settings_info[plugin_id][setting]['stype'],
                )
                if self.api('libs.api:has')('plugins.core.utils:verify.value')
                else self.settings_values[plugin_id][setting]
            )

        return returnval

    @AddAPI('reset', description='reset all settings for a plugin to their default values')
    def _api_reset(self, plugin_id):
        """
        reset all settings for a plugin to their default values
        """
        self.settings_values[plugin_id].clear()
        for i in self.settings_info[plugin_id]:
            self.settings_values[plugin_id][i] = self.settings_info[plugin_id][i]['default']
        self.settings_values[plugin_id].sync()

    @AddAPI('change', description='change the value of a setting')
    def _api_setting_change(self, plugin_id, setting, value):
        """  change a setting
        @Yplugin_id@w     = the plugin_id of the owner of the setting
        @Ysetting@w    = the name of the setting to change
        @Yvalue@w      = the value to set it as

        returns:
          True if the value was changed, False otherwise"""
        if plugin_id not in self.settings_info:
            return False

        if setting not in self.settings_info[plugin_id]:
            return False

        if value == 'default':
            value = self.settings_info[plugin_id][setting]['default']
        elif self.api('libs.pluginloader:is.plugin.loaded')('plugins.core.utils'):
            value = self.api('plugins.core.utils:verify.value')(
                        value,
                        self.settings_info[plugin_id][setting]['stype'])

        old_value =  self.api("plugins.core.settings:get")(plugin_id, setting)

        if old_value == value:
            return True

        self.settings_values[plugin_id][setting] = value
        self.settings_values[plugin_id].sync()

        if (self.api(f"{plugin_id}:is.initialized")()
                or self.api(f"{plugin_id}:is.instantiated")()
                or self.api("plugins.core.settings:is.setting.hidden")(plugin_id, setting)):
            return True
        if self.api.startup:
            return True

        new_value = self.api("plugins.core.settings:get")(plugin_id, setting)

        event_name = f"ev_{plugin_id}_var_{setting}_modified"

        if self.api('libs.api:has')('plugins.core.events:raise.event'):
                self.api('plugins.core.events:raise.event')(
                    event_name,
                    {'var':setting,
                    'newvalue':new_value,
                    'oldvalue':old_value})

        return True

    @AddAPI('get.setting.info', description='get the info for a setting')
    def _api_get_setting_info(self, plugin_id, setting):
        """
        get the info for a setting
        """
        if plugin_id not in self.settings_info:
            return None
        if setting not in self.settings_info[plugin_id]:
            return None
        return self.settings_info[plugin_id][setting]

    @AddAPI('initialize.plugin.settings', description='initialize the settings for a plugin')
    def _api_initialize_plugin_settings(self, plugin_id):
        """
        initialize the settings for a plugin
        """
        LogRecord(f"initializing settings for {plugin_id}", level='debug', sources=[self.plugin_id, plugin_id])()
        if plugin_id not in self.settings_info:
            self.settings_info[plugin_id] = {}

        for i in self.settings_info[plugin_id]:
            if self.api("plugins.core.settings:is.setting.hidden")(plugin_id, i):
                continue
            self.api('plugins.core.events:add.event')(f"ev_{plugin_id}_var_{i}_modified", plugin_id,
                                description=[f"An event to modify the setting {i}"],
                                arg_descriptions={'var':'the variable that was modified',
                                                    'newvalue':'the new value',
                                                    'oldvalue':'the old value'})

    @AddAPI('remove.plugin.settings', description='remove the settings for a plugin')
    def _api_remove_plugin_settings(self, plugin_id):
        """
        removing the settings for a plugin
        """
        LogRecord(f"Removing settings for {plugin_id}", level='debug', sources=[self.plugin_id, plugin_id])()
        if plugin_id not in self.settings_info:
            self.settings_info[plugin_id] = {}

        for i in self.settings_info[plugin_id]:
            if i in self.settings_map:
                del self.settings_map[i]

        del self.settings_info[plugin_id]

        self.settings_values[plugin_id].close()
        del self.settings_values[plugin_id]

    @AddAPI('save.plugin', description='save the settings for a plugin')
    def _api_save_plugin(self, plugin_id):
        """
        save the settings for a plugin
        """
        self.settings_values[plugin_id].sync()

    @AddAPI('get.all.for.plugin', description='get all settings for a plugin')
    def _api_get_all_for_plugin(self, plugin_id):
        """
        get all settings info for a plugin
        """
        return self.settings_info[plugin_id]

    @AddAPI('raise.event.all.settings', description='raise an event for all settings')
    def _api_raise_event_all_settings(self, plugin_id):
        """
        raise an event for all settings
        """
        LogRecord(f"Raising events for all settings in {plugin_id}", level='debug', sources=[self.plugin_id, plugin_id])()
        old_value = '__init__'
        for i in self.settings_info[plugin_id]:
            if self.api("plugins.core.settings:is.setting.hidden")(plugin_id, i):
                continue
            event_name = f"ev_{plugin_id}_var_{i}_modified"
            new_value = self.api("plugins.core.settings:get")(plugin_id, i)

            self.api('plugins.core.events:raise.event')(
                event_name,
                {'var':i,
                'newvalue':new_value,
                'oldvalue':old_value})

    @AddAPI('is.setting.hidden', description='check if a plugin setting is flagged hidden')
    def _api_is_setting_hidden(self, plugin_id, setting):
        """
        check if a plugin setting is hidden
        """
        return self.settings_info[plugin_id][setting]['hidden']

    @AddAPI('add.setting.to.map', description='add a setting to the settings map')
    def _api_add_setting_to_map(self, plugin_id, setting_name):
        """
        add a setting to the settings map
        """
        if setting_name in self.settings_map:
            LogRecord(f"setting {plugin_id}.{setting_name} conflicts {self.settings_map[setting_name]}:{setting_name}", level='error')
            return
        self.settings_map[setting_name] = plugin_id

    def format_setting_for_print(self, plugin_id, setting_name):
        """
        format a setting for printing
        """
        value = self.api(f"{self.plugin_id}:get")(plugin_id, setting_name)
        setting_info = self.api(f"{self.plugin_id}:get.setting.info")(plugin_id, setting_name)
        if setting_info['nocolor']:
            value = value.replace('@', '@@')
        elif setting_info['stype'] == 'color':
            value = f"{value}{value.replace('@', '@@')}@w"
        elif setting_info['stype'] == 'timelength':
            value = self.api('plugins.core.utils:format.time')(
                self.api('plugins.core.utils:verify.value')(value, 'timelength'))

        return str(value)

    @AddAPI('format.setting', description='format a setting')
    def _api_format_setting(self, plugin_id, setting_name):
        """
        format a setting
        """
        val = self.api(f"{self.plugin_id}:get")(plugin_id, setting_name)
        info = self.api(f"{self.plugin_id}:get.setting.info")(plugin_id, setting_name)

        if info['hidden']:
            return ""

        value_column_width = 15
        help = info['help']
        value_string = self.format_setting_for_print(plugin_id, setting_name)
        if info['stype'] == 'color':
            tlen = len(val)
            value_column_width = value_column_width + 3 + tlen
            help = f"{val}{help}@w"

        return f"{setting_name:<22} : {value_string:<{value_column_width}} - {help}"

    @AddAPI('get.all.settings.formatted', description='get all settings formatted')
    def _api_get_all_settings_formatted(self, plugin_id):
        """
        get all settings formatted
        """
        tmsg = []
        if not self.settings_info[plugin_id]:
            return [f'There are no settings defined in {plugin_id}']

        for i in self.settings_info[plugin_id]:
            if formatted_setting := self.api(
                'plugins.core.settings:format.setting'
            )(plugin_id, i):
                tmsg.append(formatted_setting)

        return tmsg or [f'There are no settings defined in {plugin_id}']

    @AddCommand(group='Settings', show_in_history=False)
    @AddParser(description="List all settings")
    @AddArgument('search',
                    help='only list settings with the included string',
                    default='',
                    nargs='?')
    @AddArgument('-p', '--plugin',
                    help='onyl show settings in the specific plugin',
                    default='',
                    nargs='?')
    def _command_list(self):
        """
        list all settings
        """
        args = self.api('plugins.core.commands:get.current.command.args')()
        line_length = self.api('plugins.core.commands:get.output.line.length')()
        header_color = self.api('plugins.core.settings:get')('plugins.core.commands', 'output_header_color')
        loaded_plugins = self.api('libs.pluginloader:get.loaded.plugins.list')()

        default_message = ['No settings found']

        settings = {}
        if args['plugin']:
            default_message = [f"No settings found for {args['plugin']}"]
            if self.api('libs.pluginloader:is.plugin.loaded')(args['plugin']):
                settings[args['plugin']] = self.api(f"{self.plugin_id}:get.all.for.plugin")(args['plugin'])
            else:
                return True, ['Plugin does not exist']
        else:
            for plugin_id in loaded_plugins:
                settings[plugin_id] = self.api(f"{self.plugin_id}:get.all.for.plugin")(plugin_id)

        if not settings:
            return True, ['No settings found']

        message = [
            f"{'Plugin ID':<30} {'Setting':<22} : {'Value':<15} - Help",
            header_color + '-' * line_length + '@w',
        ]
        plugin_message = []
        for plugin_id in settings:
            for setting_name in settings[plugin_id]:
                if args['search'] and args['search'] not in setting_name:
                    continue
                if settings[plugin_id][setting_name]['readonly']:
                    continue
                if setting_format := self.api(f'{self.plugin_id}:format.setting')(
                    plugin_id, setting_name
                ):
                    plugin_message.append(f"{plugin_id:<30} {setting_format}")

        if not plugin_message:
            return True, default_message

        message.extend(plugin_message)
        return True, message

    @AddCommand(group='Settings', name='pset', show_in_history=False)
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
    @AddArgument('-p', '--plugin',
                    help='the plugin of the setting',
                    default='',
                    nargs='?')
    def _command_settings_plugin_sets(self):
        """
        command to set a plugin setting
        """
        args = self.api('plugins.core.commands:get.current.command.args')()

        if not args['value']:
            return False, ["please specify a value to set the setting to"]

        setting_name = args['name']

        if setting_name not in self.settings_map:
            return True, [f"plugin setting {setting_name} does not exist"]

        plugin_id = args['plugin'] or self.settings_map[setting_name]

        if setting_info := self.api('plugins.core.settings:get.setting.info')(
            plugin_id, setting_name
        ):
            if setting_info['hidden']:
                return True, [f"plugin setting {setting_name} does not exist"]
            if setting_info['readonly']:
                return True, [f"{setting_name} is a readonly setting"]

            val = args['value']
            try:
                self.api("plugins.core.settings:change")(plugin_id, setting_name, val)
                tsetting_name = self.format_setting_for_print(plugin_id, setting_name)
                tmsg = [f"{plugin_id} : {setting_name} is now set to {tsetting_name}"]
                if setting_info['aftersetmessage']:
                    tmsg.extend(['\n',setting_info['aftersetmessage']])
                return True, tmsg
            except ValueError:
                msg = [f"Cannot convert {val} to {setting_info['stype']}"]
                return True, msg

        else:
            msg = [f"plugin setting {plugin_id} {setting_name} does not exist"]

        return False, ['How did you get here?']

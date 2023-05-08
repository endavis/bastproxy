# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/_baseplugin.py
#
# File Description: holds the baseplugin class
#
# By: Bast
"""
This module holds the class BasePlugin, which all plugins should have as
their base class.
"""

import contextlib
# Standard Library
import os
import sys
import textwrap
import pprint
import inspect
import datetime
from pathlib import Path

# 3rd Party
try:
    from dumper import dumps
except ImportError:
    print('Please install required libraries. dumper is missing.')
    print('From the root of the project: pip(3) install -r requirements.txt')
    sys.exit(1)

# Project
import libs.argp as argp
from libs.persistentdict import PersistentDictEvent
from libs.api import API
from libs.records import LogRecord


class BasePlugin(object): # pylint: disable=too-many-instance-attributes
    """
    a base class for plugins
    """
    def __init__(self, name, plugin_path: Path, base_plugin_dir: Path,
                 full_import_location, plugin_id):    # pylint: disable=too-many-arguments
        """
        initialize the instance
        The only things that should be done are:
              initializing class variables and initializing the class
              only use api:add, api:overload, dependency:add, setting.add
              anything that needs to be done so another plugin can interact with this plugin

        Arguments and examples:
          name : 'Actions' - from plugin file variable NAME (long name)
          plugin_path : pathlib.Path : '/client/actions.py' - path relative to the plugins directory
          base_plugin_dir : pathlib.Path : '/home/src/games/bastproxy/bp/plugins' -
                            the full path to the plugins directory
          full_import_location : 'plugins.client.actions' - import location
          plugin_id : 'client.actions' - guaranteed to be unique
        """
        self.name = name
        self.plugin_id = plugin_id
        self.initializing_f = True
        self.author = ''
        self.purpose = ''
        self.version = 0
        self.priority = 100

        self.api = API(owner_id=self.plugin_id)
        self.full_import_location = full_import_location
        self.plugin_path = plugin_path
        self.base_plugin_dir = base_plugin_dir
        self.full_plugin_path: Path = base_plugin_dir / plugin_path
        self.plugin_directory: Path  = self.full_plugin_path.parent
        self.save_directory: Path = self.api.BASEDATAPLUGINPATH / self.plugin_id
        self.settings_file: Path = self.save_directory / 'settingvalues.txt'
        # add any dependencies that are not REQUIRED plugins to this list
        self.dependencies = []
        with contextlib.suppress(ValueError):
            self.dependencies.remove(self.plugin_id)
        self.version_functions = {}
        self.reload_dependents_f = False
        self.summary_template = "%20s : %s"
        self.can_reload_f = True
        self.can_reset_f = True
        self.reset_f = True
        self.auto_initialize_f = True
        self.is_character_active_priority = None
        self.loaded_time =  datetime.datetime.now(datetime.timezone.utc)


        os.makedirs(self.save_directory, exist_ok=True)

        self.package = self.plugin_id.rsplit('.', 1)[0]

        self.settings = {}
        self.data = {}
        self.setting_values = PersistentDictEvent(self.plugin_id, self.settings_file, 'c')
        self.setting_values.pload()

        self._dump_shallow_attrs = ['api']

        self.api('libs.api:add')(self.plugin_id, 'dependency.add', self._api_dependency_add)
        self.api('libs.api:add')(self.plugin_id, 'setting.add', self._api_setting_add)
        self.api('libs.api:add')(self.plugin_id, 'setting.get', self._api_setting_gets)
        self.api('libs.api:add')(self.plugin_id, 'setting.change', self._api_setting_change)
        self.api('libs.api:add')(self.plugin_id, 'data.get', self._api_get_data)
        self.api('libs.api:add')(self.plugin_id, 'data.update', self._api_update_data)
        self.api('libs.api:add')(self.plugin_id, 'save.state', self._api_savestate)

    # get the value of a setting
    def _api_setting_gets(self, setting, plugin=None):
        """  get the value of a setting
        @Ysetting@w = the setting value to get
        @Yplugin@w = the plugin to get the setting from (optional)

        returns:
          the value of the setting, None if not found"""
        if not plugin:
            with contextlib.suppress(KeyError):
                return (
                    self.api('plugins.core.utils:verify.value')(
                        self.setting_values[setting],
                        self.settings[setting]['stype'],
                    )
                    if self.api('libs.api:has')('plugins.core.utils:verify.value')
                    else self.setting_values[setting]
                )
        elif plugin_instance := self.api('plugins.core.pluginm:get.plugin.instance')(
            plugin
        ):
            return self.api(f"{plugin_instance.plugin_id}:setting.get")(setting)

        return None

    # get the data for a specific datatype
    def _api_get_data(self, datatype, plugin_id=None):
        """  get the data of a specific type from this plugin
        @Ydatatype@w = the datatype to get
        @Yplugin@w   = the plugin to get the data from (optional)

        returns:
          the data for the specified datatype, None if not found"""
        if plugin_id:
            if self.api('plugins.core.pluginm:is.plugin.id')(plugin_id):
                return self.api(f"{plugin_id}:data.get")(datatype)

        elif datatype in self.data:
            return self.data[datatype]

        return None

    # update the data for a specific datatype
    def _api_update_data(self, datatype, newdata, plugin_id=None):
        """  get the data of a specific type from this plugin
        @Ydatatype@w = the datatype to get
        @Yplugin@w   = the plugin to get the data from (optional)

        returns:
          True if updated, False if not"""
        if not plugin_id:
            self.data[datatype] = newdata
            return True

        else:
            if self.api('plugins.core.pluginm:is.plugin.id')(plugin_id):
                return self.api(f"{plugin_id}:data.update")(datatype, newdata)

        return False

    # add a plugin dependency
    def _api_dependency_add(self, dependency):
        """  add a depencency
        @Ydependency@w    = the name of the plugin that will be a dependency"""
        if dependency not in self.dependencies:
            self.dependencies.append(dependency)

    # change the value of a setting
    def _api_setting_change(self, setting, value):
        """  change a setting
        @Ysetting@w    = the name of the setting to change
        @Yvalue@w      = the value to set it as

        returns:
          True if the value was changed, False otherwise"""
        if value == 'default':
            value = self.settings[setting]['default']
        if setting in self.settings:
            if self.api('plugins.core.pluginm:is.plugin.loaded')('utils'):
                value = self.api('plugins.core.utils:verify.value')(
                    value,
                    self.settings[setting]['stype'])

            self.setting_values[setting] = value
            self.setting_values.sync()
            return True

        return False

    # add a setting to the plugin
    def _api_setting_add(self, name, default, stype, shelp, **kwargs):
        """  remove a command
        @Yname@w     = the name of the setting
        @Ydefault@w  = the default value of the setting
        @Ystype@w    = the type of the setting
        @Yshelp@w    = the help associated with the setting
        Keyword Arguments
          @Ynocolor@w    = if True, don't parse colors when showing value
          @Yreadonly@w   = if True, can't be changed by a client"""

        nocolor_f = kwargs.get('nocolor', False)
        readonly_f = kwargs.get('readonly', False)
        if name not in self.setting_values:
            self.setting_values[name] = default
        self.settings[name] = {
            'default':default,
            'help':shelp,
            'stype':stype,
            'nocolor':nocolor_f,
            'readonly':readonly_f
        }

    def _cmd_inspect(self): # pylint: disable=too-many-branches
        """
        show the plugin as it currently is in memory

        args dictionary:
          method - inspect specified method
          object - inspect specified object
                      to get to nested objects or dictionary keys use .
                      Ex. data.commands.stats.parser.description

          simple - only dump topllevel attributes
        """
        args = self.api('plugins.core.commands:get.current.command.args')()
        message = []
        found_list = []
        if args['method']:
            try:
                found_method = getattr(self, args['method'])
                text_list, _ = inspect.getsourcelines(found_method)
                for i in text_list:
                    message.append(i.rstrip('\n'))
                message.append('')
                message.append('@M' + '-' * 60 + '@x')
                message.append(f"Defined in {inspect.getfile(found_method)}")
            except AttributeError:
                message.append(f"There is no method named {args['method']}")

        elif args['object']:
            found_full_item = True
            object_string = args['object']
            next_item = None

            if '.' not in object_string:
                items_to_get = [object_string]
            else:
                items_to_get = object_string.split('.')

            obj = self
            while True:
                next_item = items_to_get.pop(0)
                # check to see if next_item is an attribute
                try:
                    obj = getattr(obj, next_item)
                    found_list.append(':'.join(['attr', next_item]))
                    if items_to_get:
                        continue
                    else:
                        break
                except AttributeError:
                    # check if obj is a dict and then check both the string next_item and integer next_item
                    if isinstance(obj, dict):
                        if next_item not in obj:
                            try:
                                next_item = int(next_item)
                            except ValueError:
                                pass
                        if next_item in obj:
                            obj = obj[next_item]
                            found_list.append(':'.join(['key', next_item]))
                            if items_to_get:
                                continue
                            else:
                                break
                found_full_item = False
                break

            if found_list:
                if not found_full_item:
                    message.append(f"There is no item named {object_string}")
                    message.append(f"found up to : {'.'.join(found_list)}")
                else:
                    if args['simple']:
                        tvars = pprint.pformat(obj)
                    else:
                        tvars = str(dumps(obj))

                    message.append(f"found: {'.'.join(found_list)}")
                    message.append(tvars)
            else:
                message.append(f"There is no item named {args['object']}")

        else:
            if args['simple']:
                tvars = pprint.pformat(vars(self))
            else:
                tvars = str(dumps(self))

            message.append('@M' + '-' * 60 + '@x')
            message.append('Variables')
            message.append('@M' + '-' * 60 + '@x')
            message.append(tvars)
            message.append('@M' + '-' * 60 + '@x')
            message.append('Methods')
            message.append('@M' + '-' * 60 + '@x')
            message.append(pprint.pformat(inspect.getmembers(self, inspect.ismethod)))

        return True, message

    def _cmd_stats(self):
        """
        @G%(name)s@w - @B%(cmdname)s@w
        show stats, memory, profile, etc.. for this plugin
        @CUsage@w: stats
        """
        stats = self.get_stats()
        tmsg = []
        for header in stats:
            tmsg.append(self.api('plugins.core.utils:center.colored.string')(header, '=', 60))
            tmsg.extend(
                f"{subtype:<20} : {stats[header][subtype]}"
                for subtype in stats[header]['showorder']
            )
        return True, tmsg

    def _cmd_api(self):
        """
        list functions in the api for a plugin
        """
        args = self.api('plugins.core.commands:get.current.command.args')()
        tmsg = []

        if args['api']:
            tmsg.extend(self.api('libs.api:detail')(f"{self.plugin_id}:{args['api']}"))
        elif api_list := self.api('libs.api:list')(self.plugin_id):
            tmsg.extend(api_list)
        else:
            tmsg.append('nothing in the api')

        return True, tmsg

    def _cmd_set(self):
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

    def _cmd_reset(self):
        """
        @G%(name)s@w - @B%(cmdname)s@w
          reset the plugin
          @CUsage@w: reset
        """
        if self.can_reset_f:
            self.reset()
            return True, ['Plugin reset']

        return True, ['This plugin cannot be reset']

    def _cmd_help(self):
        """
        @G%(name)s@w - @B%(cmdname)s@w
        show the help for this plugin
        @CUsage@w: help
        """
        args = self.api('plugins.core.commands:get.current.command.args')()
        width = 25

        msg = [
            f"{'Plugin ID':<{width}} : {self.plugin_id}",
            f"{'Plugin Command Prefix':<{width}} : {self.plugin_id}",
            f"{'Purpose':<{width}} : {self.purpose}",
            f"{'Author':<{width}} : {self.author}",
            f"{'Version':<{width}} : {self.version}",
            f"{'Plugin Path':<{width}} : {self.plugin_path}",
            f"{'Time Loaded':<{width}} : {self.loaded_time.strftime(self.api.time_format)}",
            f"{'Modified Time':<{width}} : {datetime.datetime.fromtimestamp(os.path.getmtime(self.full_plugin_path), tz=datetime.timezone.utc).strftime(self.api.time_format)}",
        ]
        if self.is_changed_on_disk():
            msg.append(f"{' ':<{width}} : @RThe plugin has been modified on disk since it was loaded@w")

        if '.__init__' in self.full_import_location:
            import_location = self.full_import_location.replace('.__init__', '')
        else:
            import_location = self.full_import_location

        if sys.modules[import_location].__doc__:
            msg.extend(sys.modules[import_location].__doc__.split('\n'))
        if args['commands']:
            if cmd_list := self.api(
                'plugins.core.commands:get.commands.for.plugin.formatted'
            )(self.plugin_id):
                msg.extend(cmd_list)
                msg.extend(('@G' + '-' * 60 + '@w', ''))
        if args['api']:
            if api_list := self.api('libs.api:list')(self.plugin_id):
                msg.extend((f"API functions in {self.plugin_id}", '@G' + '-' * 60 + '@w'))
                msg.extend(api_list)
        return True, msg

    def _add_commands(self):
        """
        add base commands
        """
        parser = argp.ArgumentParser(
            add_help=False,
            formatter_class=argp.RawDescriptionHelpFormatter,
            description=textwrap.dedent("""
              change a setting in the plugin

              if there are no arguments or 'list' is the first argument then
              it will list the settings for the plugin"""))
        parser.add_argument('name',
                            help='the setting name',
                            default='list',
                            nargs='?')
        parser.add_argument('value',
                            help='the new value of the setting',
                            default='',
                            nargs='?')
        self.api('plugins.core.commands:command.add')('set',
                                              self._cmd_set,
                                              parser=parser,
                                              group='Base',
                                              show_in_history=False)

        if self.can_reset_f:
            parser = argp.ArgumentParser(add_help=False,
                                         description='reset the plugin')
            self.api('plugins.core.commands:command.add')('reset',
                                                  self._cmd_reset,
                                                  parser=parser,
                                                  group='Base')

        parser = argp.ArgumentParser(add_help=False,
                                     description='save the plugin state')
        self.api('plugins.core.commands:command.add')('save',
                                              self._cmd_save,
                                              parser=parser,
                                              group='Base')

        parser = argp.ArgumentParser(add_help=False,
                                     description='show plugin stats')
        self.api('plugins.core.commands:command.add')('stats',
                                              self._cmd_stats,
                                              parser=parser,
                                              group='Base')

        parser = argp.ArgumentParser(add_help=False,
                                     description='inspect a plugin')
        parser.add_argument('-m',
                            '--method',
                            help='get code for a method',
                            default='')
        parser.add_argument('-o',
                            '--object',
                            help='show an object of the plugin, can be method or variable',
                            default='')
        parser.add_argument('-s',
                            '--simple',
                            help='show a simple output',
                            action='store_true')
        self.api('plugins.core.commands:command.add')('inspect',
                                              self._cmd_inspect,
                                              parser=parser,
                                              group='Base')

        parser = argp.ArgumentParser(add_help=False,
                                     description='show help info for this plugin')
        parser.add_argument('-a',
                            '--api',
                            help='show functions this plugin has in the api',
                            action='store_true')
        parser.add_argument('-c',
                            '--commands',
                            help='show commands in this plugin',
                            action='store_true')
        self.api('plugins.core.commands:command.add')('help',
                                              self._cmd_help,
                                              parser=parser,
                                              group='Base')

        parser = argp.ArgumentParser(add_help=False,
                                     description='list functions in the api')
        parser.add_argument('api',
                            help='api to get details of',
                            default='',
                            nargs='?')
        self.api('plugins.core.commands:command.add')('api',
                                              self._cmd_api,
                                              parser=parser,
                                              group='Base')

    def _list_vars(self):
        """
        returns:
         a list of strings that list all settings
        """
        tmsg = []
        if not self.setting_values:
            tmsg.append('There are no settings defined')
        else:
            for i in self.settings:
                columnwidth = 15
                val = self.setting_values[i]
                if 'nocolor' in self.settings[i] and self.settings[i]['nocolor']:
                    val = val.replace('@', '@@')
                elif self.settings[i]['stype'] == 'color':
                    tlen = len(val)
                    columnwidth = 18 + tlen
                    val = f"{val}{val.replace('@', '@@')}@w"
                elif self.settings[i]['stype'] == 'timelength':
                    val = self.api('plugins.core.utils:format.time')(
                        self.api('plugins.core.utils:verify.value')(val, 'timelength'))
                tmsg.append(f"{i:<20} : {val:<{columnwidth}} - {self.settings[i]['help']}")
        return tmsg

    def _update_version(self, old_plugin_version, new_plugin_version):
        """
        update plugin data

        arguments:
          required:
            old_plugin_version - the version in the savestate file
            new_plugin_version - the latest version from the module
        """
        if old_plugin_version != new_plugin_version and new_plugin_version > old_plugin_version:
            for version in range(old_plugin_version + 1, new_plugin_version + 1):
                LogRecord(f"_update_version: upgrading to version {version}", level='info',
                          sources=[self.plugin_id, 'plugin_upgrade'])()
                if version in self.version_functions:
                    self.version_functions[version]()
                else:
                    LogRecord(f"_update_version: no function to upgrade to version {version}",
                              level='error', sources=[self.plugin_id, 'plugin_upgrade'])()

        self.setting_values['_version'] = self.version

        self.setting_values.sync()

    def _cmd_save(self, _=None):
        """
        @G%(name)s@w - @B%(cmdname)s@w
        save plugin state
        @CUsage@w: save
        """
        self.savestate()
        return True, ['Plugin settings saved']

    def savestate(self):
        """
        save all settings for the plugin
        make sure to call this in any methods
        of a subclass that overrides this
        """
        self.setting_values.sync()

    _api_savestate = savestate
    evc_savestate = savestate

    def evc_baseplugin_plugin_initialized(self):
        """
        do something after the initialize function is run
        """
        # go through each variable and raise var_%s_changed
        self.setting_values.raiseall()

        mud = self.api('plugins.core.managers:get')('mud')

        if mud and mud.connected and self.api('libs.api:is.character.active')():
            self.evc_after_character_is_active()
        else:
            self.api('plugins.core.events:register.to.event')('ev_libs.api_character_active', self.evc_after_character_is_active,
                                                      prio=self.is_character_active_priority)
        self.initializing_f = False

    def evc_baseplugin_disconnect(self):
        """
        re-register to character active event on disconnect
        """
        LogRecord(f"ev_baseplugin_disconnect: baseplugin.{self.plugin_id}", level='debug', sources=[self.plugin_id])()
        self.api('plugins.core.events:register.to.event')('ev_libs.api_character_active', self.evc_after_character_is_active)

    def evc_after_character_is_active(self):
        """
        tasks to do after character is active
        """
        LogRecord(f"ev_after_character_is_active: baseplugin.{self.plugin_id}", level='debug', sources=[self.plugin_id])()
        if self.api('plugins.core.events:is.registered.to.event')('ev_libs.api_character_active', self.evc_after_character_is_active):
            self.api('plugins.core.events:unregister.from.event')('ev_libs.api_character_active', self.evc_after_character_is_active)

    def get_stats(self):
        """
        get the stats for the plugin

        returns:
          a dict of statistics
        """
        stats = {'Base Sizes': {}}
        stats['Base Sizes']['showorder'] = ['Class', 'Variables', 'Api']
        stats['Base Sizes']['Variables'] = f"{sys.getsizeof(self.setting_values)} bytes"
        stats['Base Sizes']['Class'] = f"{sys.getsizeof(self)} bytes"
        stats['Base Sizes']['Api'] = f"{sys.getsizeof(self.api)} bytes"

        return stats

    def uninitialize(self, _=None):
        """
        uninitialize stuff
        """
        # remove anything out of the api
        self.api('libs.api:remove')(self.plugin_id)

        #save the state
        self.savestate()

    def is_changed_on_disk(self):
        """
        check to see if the file this plugin is based on has changed on disk

        return:
          True if the plugin is changed on disk, False otherwise
        """
        file_modified_time = datetime.datetime.fromtimestamp(os.path.getmtime(self.full_plugin_path), tz=datetime.timezone.utc)
        return file_modified_time > self.loaded_time

    def reset(self):
        """
        internal function to reset data
        """
        if self.can_reset_f:
            self.reset_f = True
            self.setting_values.clear()
            for i in self.settings:
                self.setting_values[i] = self.settings[i]['default']
            self.setting_values.sync()
            self.reset_f = False

    def initialize(self):
        """
        initialize the plugin, do most things here
        """
        if '_version' in self.setting_values and \
                self.setting_values['_version'] != self.version:
            self._update_version(self.setting_values['_version'], self.version)

        if self.auto_initialize_f: # don't initialize when auto_initialize_f is False

            self._add_commands()

            self.api('plugins.core.events:register.to.event')(f"ev_{self.plugin_id}_initialized",
                                                      self.evc_baseplugin_plugin_initialized, prio=1)

            self.api('plugins.core.events:register.to.event')('ev_libs.net.mud_muddisconnect', self.evc_baseplugin_disconnect)

            self.reset_f = False
            self.setting_values.raiseall()

        for i in self.settings:
            self.api('plugins.core.events:add.event')(f"ev_{self.plugin_id}_var_{i}_modified", self.plugin_id,
                                description=f"An event to modify the setting {i}",
                                arg_descriptions={'var':'the variable that was modified',
                                                    'newvalue':'the new value',
                                                    'oldvalue':'the old value'})

        self.api('plugins.core.events:add.event')(f"ev_{self.plugin_id}_savestate", self.plugin_id,
                                    description='An event to save the state of the plugin',
                                    arg_descriptions={'None': None})

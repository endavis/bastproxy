# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/_baseplugin/_baseplugin.py
#
# File Description: holds the BasePlugin class
#
# By: Bast

# Standard Library
import contextlib
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
from libs.commands import AddCommand, AddParser, AddArgument


class Base: # pylint: disable=too-many-instance-attributes
    """
    a base class for plugins
    """
    def __init__(self, name, full_plugin_path: Path, base_plugin_dir: Path,
                 full_import_location, plugin_id):    # pylint: disable=too-many-arguments
        """
        initialize the instance
        The only things that should be done are:
              initializing class variables and initializing the class
              only use api:add, dependency:add, setting.add
              anything that needs to be done so another plugin can interact with this plugin

        Arguments and examples:
          name : 'Actions' - from plugin file variable NAME (long name)
          full_plugin_path : pathlib.Path : '/plugins/client/actions' - full path to the plugin
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
        self.base_plugin_dir = base_plugin_dir
        self.full_plugin_path: Path = full_plugin_path
        self.plugin_directory: Path  = self.full_plugin_path.parent
        self.data_directory: Path = self.api.BASEDATAPLUGINPATH / self.plugin_id
        self.settings_file: Path = self.data_directory / 'settingvalues.txt'
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


        os.makedirs(self.data_directory, exist_ok=True)

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
        self.api('libs.api:add')(self.plugin_id, 'dump', self._api_dump)

    # add a dump_object method that is just dumps
    # don't have to worry about importing dumper everywhere
    def dump_object_as_string(self, object):
        """ dump an object as a string """
        return dumps(object)

    def __baseclass__post__init__(self):
        """
        do things after all __init__ methods have been called

        DO NOT OVERRIDE THIS METHOD
        """
        self.api('libs.api:add.apis.for.object')(self.plugin_id, self)

    def __init_subclass__(cls, *args, **kwargs):
        """
        hook into __init__ mechanism so that a post __init__
        method can be called
        """
        super().__init_subclass__(*args, **kwargs)
        def new_init(self, *args, init=cls.__init__, **kwargs):
            init(self, *args, **kwargs)
            if cls is type(self):
                self.__baseclass__post__init__()
        cls.__init__ = new_init

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
        elif plugin_instance := self.api('libs.pluginloader:get.plugin.instance')(
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
            if self.api('libs.pluginloader:is.plugin.id')(plugin_id):
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
            if self.api('libs.pluginloader:is.plugin.id')(plugin_id):
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
            if self.api('libs.pluginloader:is.plugin.loaded')('utils'):
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

    def _find_attribute(self, attribute_name):
        """
        find an attribute of this plugin and dump it as a string

        attr.some_attr_or_dict_key.child_attr_or_dict_key

        will look for any attr in the plugin and then
        search for attributes or dictionary keys that match the name
        and return the value of the last one
        """
        obj = None
        next_item = None

        if '.' not in attribute_name:
            items_to_get = [attribute_name]
        else:
            items_to_get = attribute_name.split('.')

        obj = self

        while items_to_get:
            next_item = items_to_get.pop(0)
            # check to see if next_item is an attribute
            try:
                obj = getattr(obj, next_item)
                if not items_to_get:
                    return obj
            except AttributeError:
                # check if obj is a dict and then check both the string next_item and integer next_item
                if isinstance(obj, dict):
                    if next_item not in obj:
                        with contextlib.suppress(ValueError):
                            next_item = int(next_item)
                    if next_item in obj:
                        obj = obj[next_item]
                        if not items_to_get:
                            return obj

        return None

    def _api_dump(self, attribute_name, simple=False):
        """  dump self or an attribute of self to a string
        @Yobj@w    = the object to inspect
        @Ymethod@w = the method to inspect

        returns:
          the object or method"""

        if not attribute_name:
            if simple:
                tvars = pprint.pformat(vars(self))
            else:
                tvars = self.dump_object_as_string(self)

            message = []
            message.append('@M' + '-' * 60 + '@x')
            message.append('Attributes')
            message.append('@M' + '-' * 60 + '@x')
            message.append(tvars)
            message.append('@M' + '-' * 60 + '@x')
            message.append('Methods')
            message.append('@M' + '-' * 60 + '@x')
            message.append(pprint.pformat(inspect.getmembers(self, inspect.ismethod)))

        else:
            attr = self._find_attribute(attribute_name)

            if not attr:
                return False, [f"Could not find attribute {attribute_name}"]

            message = [f"Object: {attribute_name}"]

            if callable(attr):
                text_list, _ = inspect.getsourcelines(attr)
                message.extend([i.rstrip('\n') for i in text_list])
                message.extend(
                    ('', '@M' + '-' * 60 + '@x', f"Defined in {inspect.getfile(attr)}")
                )
            elif simple:
                message.append(pprint.pformat(attr))
            else:
                message.extend(self.dump_object_as_string(attr).split('\n'))

        return True, message

    @AddCommand(group='Base')
    @AddParser(description='inspect a plugin')
    @AddArgument('-o',
                    '--object',
                    help='show an object of the plugin, can be method or variable',
                    default='')
    @AddArgument('-s',
                    '--simple',
                    help='show a simple output',
                    action='store_true')
    def _command_inspect(self): # pylint: disable=too-many-branches
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

        return True, self.api(f"{self.plugin_id}:dump")(args['object'], simple=args['simple'])[1]

    @AddCommand(group='Base')
    @AddParser(description='show plugin stats')
    def _command_stats(self):
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

    @AddCommand(group='Base')
    @AddParser(description='list functions in the api')
    @AddArgument('api',
                    help='api to get details of',
                    default='',
                    nargs='?')
    def _command_api(self):
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
    def _command_set(self):
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

    @AddCommand(group='Base', autoadd=False)
    @AddParser(description='reset the plugin')
    def _command_reset(self):
        """
        @G%(name)s@w - @B%(cmdname)s@w
          reset the plugin
          @CUsage@w: reset
        """
        if self.can_reset_f:
            self.reset()
            return True, ['Plugin reset']

        return True, ['This plugin cannot be reset']

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
    def _command_help(self):
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
            f"{'Full Plugin Path':<{width}} : {self.full_plugin_path}",
            f"{'Time Loaded':<{width}} : {self.loaded_time.strftime(self.api.time_format)}",
        ]

        if '.__init__' in self.full_import_location:
            import_location = self.full_import_location.replace('.__init__', '')
        else:
            import_location = self.full_import_location

        if sys.modules[import_location].__doc__:
            msg.extend(sys.modules[import_location].__doc__.split('\n'))

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
        if self.can_reset_f:
            self.api('plugins.core.commands:add.command.by.func')(self._command_reset, force=True)

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

    @AddCommand(group='Base')
    @AddParser(description='save the plugin state')
    def _command_save(self, _=None):
        """
        @G%(name)s@w - @B%(cmdname)s@w
        save plugin state
        @CUsage@w: save
        """
        self.savestate()
        return True, ['Plugin settings saved']

    # save the plugin state
    def savestate(self):
        """
        save all settings for the plugin
        make sure to call this in any methods
        of a subclass that overrides this
        """
        self.setting_values.sync()

    _api_savestate = savestate
    evc_savestate = savestate

    def _eventcb_baseplugin_plugin_initialized(self):
        """
        do something after the initialize function is run
        """
        # add newly created api functions, this will happen if the plugin (in its
        # initialize function) creates new objects that have apis
        # an example is the plugins.core.proxy plugin initialziing
        # new ssc objects in the initialize function
        self.api('libs.api:add.apis.for.object')(self.plugin_id, self)

        # go through each variable and raise var_%s_changed
        self.setting_values.raiseall()

        mud = self.api('plugins.core.managers:get')('mud')

        if mud and mud.connected and self.api('libs.api:is.character.active')():
            self._eventcb_baseplugin_after_character_is_active()
        else:
            self.api('plugins.core.events:register.to.event')('ev_libs.api_character_active', self._eventcb_baseplugin_after_character_is_active,
                                                      prio=self.is_character_active_priority)
        self.initializing_f = False

    def _eventcb_baseplugin_disconnect(self):
        """
        re-register to character active event on disconnect
        """
        LogRecord(f"ev_baseplugin_disconnect: baseplugin.{self.plugin_id}", level='debug', sources=[self.plugin_id])()
        self.api('plugins.core.events:register.to.event')('ev_libs.api_character_active', self._eventcb_baseplugin_after_character_is_active)

    def _eventcb_baseplugin_after_character_is_active(self):
        """
        tasks to do after character is active
        """
        LogRecord(f"ev_after_character_is_active: baseplugin.{self.plugin_id}", level='debug', sources=[self.plugin_id])()
        if self.api('plugins.core.events:is.registered.to.event')('ev_libs.api_character_active', self._eventcb_baseplugin_after_character_is_active):
            self.api('plugins.core.events:unregister.from.event')('ev_libs.api_character_active', self._eventcb_baseplugin_after_character_is_active)

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
                                                      self._eventcb_baseplugin_plugin_initialized, prio=1)

            self.api('plugins.core.events:register.to.event')('ev_libs.net.mud_muddisconnect', self._eventcb_baseplugin_disconnect)

            self.reset_f = False

        for i in self.settings:
            self.api('plugins.core.events:add.event')(f"ev_{self.plugin_id}_var_{i}_modified", self.plugin_id,
                                description=f"An event to modify the setting {i}",
                                arg_descriptions={'var':'the variable that was modified',
                                                    'newvalue':'the new value',
                                                    'oldvalue':'the old value'})

        self.api('plugins.core.events:add.event')(f"ev_{self.plugin_id}_savestate", self.plugin_id,
                                    description='An event to save the state of the plugin',
                                    arg_descriptions={'None': None})

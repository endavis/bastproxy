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
import pprint
import inspect
import types
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
from libs.api import API, AddAPI
from libs.records import LogRecord
from ._pluginhooks import RegisterPluginHook

class Base: # pylint: disable=too-many-instance-attributes
    """
    a base class for plugins
    """
    def __init__(self, plugin_id, plugin_info):
        """
        initialize the instance
        The only things that should be done are:
              initializing class variables and initializing the class
              only use api:add, dependency:add, setting.add
              anything that needs to be done so another plugin can interact with this plugin

        Arguments and examples:
          plugin_id : 'client.actions' - guaranteed to be unique
          plugin_info: The plugin info object
        """
        self.plugin_id = plugin_id
        self.plugin_info = plugin_info

        self.api = API(owner_id=self.plugin_id)

        self.instantiating_f = True
        self.initializing_f = True
        self.can_reload_f = True
        self.can_reset_f = True
        self.reload_dependents_f = False

        # add any dependencies that are not in the packages plugins.core or plugins.client to this list
        self.dependencies = []
        with contextlib.suppress(ValueError):
            self.dependencies.remove(self.plugin_id)

        self.version_functions = {}
        self.summary_template = "%20s : %s"
        self.is_character_active_priority = None
        self.loaded_time =  datetime.datetime.now(datetime.timezone.utc)

        os.makedirs(self.plugin_info.data_directory, exist_ok=True)

        self.data = {}

        self._dump_shallow_attrs = ['api']

        self._process_plugin_hook('post_base_init')

    @RegisterPluginHook('post_base_init', priority=1)
    def _load_hook_add_apis(self):
        """
        load any apis that were added in the __init__ method
        """
        self.api('libs.api:add.apis.for.object')(self.plugin_id, self)

    @RegisterPluginHook('post_init', priority=1)
    def _load_hook_post_instantiate(self):
        self.api('libs.api:add.apis.for.object')(self.plugin_id, self)

        self.instantiating_f = False

    def _process_plugin_hook(self, load_hook, **kwargs) -> dict:
        """
        process a loading hook
        """
        LogRecord(f"_process_plugin_hook: {load_hook}", level='debug',
                sources=[self.plugin_id])()

        functions = self._get_load_hook_functions(self, load_hook)
        sorted_keys = sorted(functions.keys())
        for key in sorted_keys:
            for func in functions[key]:
                LogRecord(f"calling function {func.__name__}", level='debug',
                        sources=[self.plugin_id, 'plugin_upgrade'])()
                if not kwargs:
                    func()
                else:
                    kwargs = func(**kwargs)

        return kwargs

    def _get_load_hook_functions(self, obj, load_hook, recurse=True) -> dict:
        """
        recursively search for functions that are commands in a plugin instance
        and it's attributes that are registered to a load hook
        """
        function_list = {}
        for item in dir(obj):
            if item.startswith('__'):
                continue
            try:
                item = getattr(self, item)
            except AttributeError:
                continue
            if isinstance(item, types.MethodType) and hasattr(item, 'load_hooks'):
                if load_hook in item.load_hooks:  # pyright: ignore[reportGeneralTypeIssues]
                    if item.load_hooks[load_hook] not in function_list: # pyright: ignore[reportGeneralTypeIssues]
                        function_list[item.load_hooks[load_hook]] = [] # pyright: ignore[reportGeneralTypeIssues]
                    function_list[item.load_hooks[load_hook]].append(item) # pyright: ignore[reportGeneralTypeIssues]
            # elif recurse:
            #     new_list = self.get_load_hook_functions(item, load_hook, recurse=False)
            #     for key, value in new_list.items():
            #         if key not in function_list:
            #             function_list[key] = []
            #         function_list[key].extend(value)

        return function_list

    # add a dump_object method that is just dumps
    # don't have to worry about importing dumper everywhere
    def dump_object_as_string(self, object):
        """ dump an object as a string """
        return dumps(object)

    def __init_subclass__(cls, *args, **kwargs):
        """
        hook into __init__ mechanism so that the
        post_init load hook can be processed
        """
        super().__init_subclass__(*args, **kwargs)
        def new_init(self, *args, init=cls.__init__, **kwargs):
            init(self, *args, **kwargs)
            if cls is type(self):
                self._process_plugin_hook('post_init')
        cls.__init__ = new_init

    @AddAPI('data.get', description='get the data for a specific datatype')
    def _api_data_get(self, datatype, plugin_id=None):
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

    @AddAPI('data.update', description='update the data for a specific datatype')
    def _api_data_update(self, datatype, newdata, plugin_id=None):
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

    @AddAPI('dependency.add', description='add a dependency for this plugin')
    def _api_dependency_add(self, dependency):
        """  add a depencency
        @Ydependency@w    = the name of the plugin that will be a dependency"""
        if dependency not in self.dependencies:
            self.dependencies.append(dependency)

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

    @AddAPI('dump', description='dump an object or attribute of an object to a string')
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

    def _update_version(self):
        """
        update plugin data

        arguments:
          required:
            old_plugin_version - the version in the savestate file
            new_plugin_version - the latest version from the module
        """
        old_plugin_version = self.api(f"{self.plugin_id}:setting.get")('_version')

        new_plugin_version = self.plugin_info.version

        if old_plugin_version != new_plugin_version and new_plugin_version > old_plugin_version:
            for version in range(old_plugin_version + 1, new_plugin_version + 1):
                LogRecord(f"_update_version: upgrading to version {version}", level='info',
                          sources=[self.plugin_id, 'plugin_upgrade'])()
                if version in self.version_functions:
                    self.version_functions[version]()
                else:
                    LogRecord(f"_update_version: no function to upgrade to version {version}",
                              level='error', sources=[self.plugin_id, 'plugin_upgrade'])()

            self.api(f"{self.plugin_id}:setting.change")('_version', new_plugin_version)

            self.api(f"{self.plugin_id}:save.state")()


    @RegisterPluginHook('post_initialize')
    def _load_hook_post_initialize_base_setup(self):
        """
        do something after the initialize function is run
        """
        # add newly created api functions, this will happen if the plugin (in its
        # initialize function) creates new objects that have apis
        # an example is the plugins.core.proxy plugin initialziing
        # new ssc objects in the initialize function
        self.api('libs.api:add.apis.for.object')(self.plugin_id, self)

        mud = self.api('plugins.core.managers:get')('mud')

        if mud and mud.connected and self.api('libs.api:is.character.active')():
            self._eventcb_baseplugin_after_character_is_active()
        else:
            self.api('plugins.core.events:register.to.event')('ev_libs.api_character_active', self._eventcb_baseplugin_after_character_is_active,
                                                      prio=self.is_character_active_priority)
        self.initializing_f = False

    def is_initialized(self):
        return self.initializing_f

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

    def _base_get_stats(self):
        """
        get the stats for the plugin

        returns:
          a dict of statistics
        """
        stats = {'Base Sizes': {'showorder': ['Class', 'Api']}}
        stats['Base Sizes']['Class'] = f"{sys.getsizeof(self)} bytes"
        stats['Base Sizes']['Api'] = f"{sys.getsizeof(self.api)} bytes"

        return_kwargs = self._process_plugin_hook('stats', stats=stats)

        return return_kwargs.get('stats', stats)

    def uninitialize(self, _=None):
        """
        uninitialize stuff
        """
        #save the state
        self.api(f"{self.plugin_id}:save.state")()

        # remove anything out of the api
        self.api('libs.api:remove')(self.plugin_id)

    @RegisterPluginHook('pre_initialize')
    def _load_hook_pre_initialize(self):
        """
        initialize the plugin, do most things here
        """
        self.api(f"{self.plugin_id}:setting.add")('_version', 0, int, 'The version of the plugin', hidden=True)

        self._update_version()

        self.api('plugins.core.events:register.to.event')('ev_libs.net.mud_muddisconnect', self._eventcb_baseplugin_disconnect)

        self.api('plugins.core.events:add.event')(f"ev_{self.plugin_id}_savestate", self.plugin_id,
                                    description='An event to save the state of the plugin',
                                    arg_descriptions={'None': None})

    def initialize(self):
        """
        initialize the plugin, do most things here
        """
        pass

    def initialize_with_hooks(self):
        self._process_plugin_hook('pre_initialize')

        if hasattr(self, 'initialize'):
            self.initialize()

        self._process_plugin_hook('post_initialize')

    @AddAPI('save.state', 'Save the state of the plugin')
    def _api_save_state(self):
        """
        save the state of the plugin
        """
        self._process_plugin_hook('save')

    @AddAPI('reset', 'reset the plugin')
    def _api_reset(self):
        """
        reset the plugin
        """
        self._process_plugin_hook('reset')

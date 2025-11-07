# Project: bastproxy
# Filename: plugins/_baseplugin/_baseplugin.py
#
# File Description: holds the BasePlugin class
#
# By: Bast

# Standard Library
import contextlib
import datetime
import inspect
import os
import pprint
import sys
import types

# 3rd Party
# Project
from libs.api import API, AddAPI
from libs.records import LogRecord

from ._pluginhooks import RegisterPluginHook


class Plugin: # pylint: disable=too-many-instance-attributes
    """
    a base class for plugins
    """
    def __init__(self, plugin_id, plugin_info):
        """
        initialize the instance
        The only things that should be done are:
              initializing class variables and initializing the class
              only use libs.api:add
              anything that needs to be done so another plugin can interact with this plugin

        Arguments and examples:
          plugin_id : 'plugins.core.commands' - guaranteed to be unique
          plugin_info: The plugin info object
        """
        self.plugin_id = plugin_id
        self.plugin_info = plugin_info

        self.api = API(owner_id=self.plugin_id)

        self.is_reloading_f = False
        self.can_reload_f = True
        self.can_reset_f = True
        self.reload_dependents_f = False

        self.attributes_to_save_on_reload = []

        # add any dependencies that are not in the packages plugins.core or plugins.client to this list
        self.dependencies = []
        with contextlib.suppress(ValueError):
            self.dependencies.remove(self.plugin_id)

        self.version_functions = {}
        self.is_character_active_priority = None
        self.loaded_time =  datetime.datetime.now(datetime.UTC)

        os.makedirs(self.plugin_info.data_directory, exist_ok=True)

        self.data = {}

        self._dump_shallow_attrs = ['api']

        self._process_plugin_hook('__init__')

    @RegisterPluginHook('__init__', priority=1)
    def _phook_base_init_add_apis(self):
        """
        load any apis that were added in the __init__ method
        """
        self.api('libs.api:add.apis.for.object')(self.plugin_id, self)

    @RegisterPluginHook('__init__', priority=75)
    def _phook_base_init(self):
        self.api('libs.api:add.apis.for.object')(self.plugin_id, self)

        # load anything in the reload cache
        cache = self.api('libs.plugins.reloadutils:get.plugin.cache')(self.plugin_id)
        for item in cache:
            LogRecord(f"loading {item} from cache", level='debug',
                      sources=[self.plugin_id])()
            self.__setattr__(item, cache[item])
        self.api('libs.plugins.reloadutils:remove.plugin.cache')(self.plugin_id)

    def _process_plugin_hook(self, plugin_hook, **kwargs) -> dict:
        """
        process a loading hook
        """
        LogRecord(f"_process_plugin_hook: {plugin_hook}", level='debug',
                sources=[self.plugin_id])()

        functions = self._get_plugin_hook_functions(self, plugin_hook)
        sorted_keys = sorted(functions.keys())
        for key in sorted_keys:
            for func in functions[key]:
                LogRecord(f"phook {plugin_hook} calling function {func.__name__}", level='debug',
                        sources=[self.plugin_id, 'plugin_upgrade'])()
                if not kwargs:
                    func()
                else:
                    kwargs = func(**kwargs)

        return kwargs

    def _get_all_plugin_hook_functions(self) -> dict:
        """
        recursively search for functions that are commands in a plugin instance
        and it's attributes that are registered to a load hook
        """
        function_list = {}
        for item in dir(self):
            try:
                item = getattr(self, item)
            except AttributeError:
                continue
            if isinstance(item, types.MethodType):
                if item_plugin_hooks := getattr(item, 'plugin_hooks', None):
                    for plugin_hook in item_plugin_hooks:
                        if plugin_hook not in function_list:
                            function_list[plugin_hook] = {}
                        if item_plugin_hooks[plugin_hook] not in function_list[plugin_hook]:
                            function_list[plugin_hook][item_plugin_hooks[plugin_hook]] = []
                        function_list[plugin_hook][item_plugin_hooks[plugin_hook]].append(item)

        return function_list

    def _get_plugin_hook_functions(self, obj, plugin_hook, recurse=True) -> dict:
        """
        recursively search for functions that are commands in a plugin instance
        and it's attributes that are registered to a load hook
        """
        function_list = {}
        for item in dir(obj):
            if not item.startswith('_phook_'):
                continue
            try:
                item = getattr(self, item)
            except AttributeError:
                continue
            if (isinstance(item, types.MethodType)
                and hasattr(item, 'plugin_hooks')
                and plugin_hook in item.plugin_hooks):  # pyright: ignore[reportGeneralTypeIssues, reportAttributeAccessIssue]
                    if item.plugin_hooks[plugin_hook] not in function_list: # pyright: ignore[reportGeneralTypeIssues, reportAttributeAccessIssue]
                        function_list[item.plugin_hooks[plugin_hook]] = [] # pyright: ignore[reportGeneralTypeIssues, reportAttributeAccessIssue]
                    function_list[item.plugin_hooks[plugin_hook]].append(item) # pyright: ignore[reportGeneralTypeIssues, reportAttributeAccessIssue]

        return function_list

    # add a dump_object method that is just dumps
    # don't have to worry about importing dumper everywhere
    def dump_object_as_string(self, object):
        """ dump an object as a string """
        return self.api('plugins.core.utils:dump.object.as.string')(object)


    @AddAPI('data.get', description='get the data for a specific datatype')
    def _api_data_get(self, datatype, plugin_id=None):
        """  get the data of a specific type from this plugin
        @Ydatatype@w = the datatype to get
        @Yplugin@w   = the plugin to get the data from (optional)

        returns:
          the data for the specified datatype, None if not found"""
        if plugin_id:
            if self.api('libs.plugins.loader:is.plugin.id')(plugin_id):
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
            if self.api('libs.plugins.loader:is.plugin.id')(plugin_id):
                return self.api(f"{plugin_id}:data.update")(datatype, newdata)

        return False

    @AddAPI('dependency.add', description='add a dependency for this plugin')
    def _api_dependency_add(self, dependency):
        """  add a depencency
        @Ydependency@w    = the name of the plugin that will be a dependency"""
        if dependency not in self.dependencies:
            self.dependencies.append(dependency)

    @AddAPI('get.data.directory', description='get the data directory for this plugin')
    def _api_get_data_directory(self):
        """ get the data directory for this plugin """
        return self.plugin_info.data_directory

    @AddAPI('set.reload', description='set the reload flag')
    def _api_set_reload(self):
        """ set the reload flag """
        self.is_reloading_f = True

    @AddAPI('get.plugin.hooks', description='get the plugin hooks for this plugin')
    def _api_get_plugin_hooks(self):
        """ get the plugin hooks for this plugin """
        return self._get_all_plugin_hook_functions()

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

    @AddAPI('dump', description='dump this plugin or a specific attribute to a string')
    def _api_dump(self, attribute_name, detailed=False):
        """  dump this plugin or a specific attribute to a string
        @Yobj@w    = the object to inspect
        @Ymethod@w = the method to inspect

        returns:
          the object or method"""

        line_length = self.api('plugins.core.commands:get.output.line.length')()
        header_color = self.api('plugins.core.settings:get')('plugins.core.commands', 'output_header_color')
        header = header_color + '-' * line_length + '@x'

        if not attribute_name:
            if detailed:
                tvars = self.dump_object_as_string(self)
            else:
                tvars = pprint.pformat(vars(self))

            message = [
                header,
                'Attributes',
                header,
                tvars,
                header,
                'Methods',
                header,
                pprint.pformat(inspect.getmembers(self, inspect.ismethod)),
            ]
        else:
            attr = self._find_attribute(attribute_name)

            if not attr:
                return False, [f"Could not find attribute {attribute_name}"]

            message = []

            if detailed:
                message.extend(self.dump_object_as_string(attr).splitlines())
            else:
                message.append(pprint.pformat(attr))

            with contextlib.suppress(TypeError):
                if callable(attr):
                    message.extend(
                        (header,
                        f"Defined in {inspect.getfile(attr)}",
                        header,
                        '')
                    )
                    text_list, _ = inspect.getsourcelines(attr)
                    message.extend([i.replace('@', '@@').rstrip('\n') for i in text_list])

        return True, message

    @RegisterPluginHook('initialize', priority=90)
    def _phook_base_post_initialize_update_version(self):
        """
        update plugin data

        arguments:
          required:
            old_plugin_version - the version in the savestate file
            new_plugin_version - the latest version from the module
        """
        old_plugin_version = self.api('plugins.core.settings:get')(self.plugin_id, '_version')

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

            self.api('plugins.core.settings:change')(self.plugin_id, '_version', new_plugin_version)

            self.api(f"{self.plugin_id}:save.state")()

    @RegisterPluginHook('initialize', priority=91)
    def _phook_base_post_initialize_setup(self):
        """
        do something after the initialize function is run
        """
        # add newly created api functions, this will happen if the plugin (in its
        # initialize function) creates new objects that have apis
        # an example is the plugins.core.proxy plugin initialziing
        # new ssc objects in the initialize function
        self.api('libs.api:add.apis.for.object')(self.plugin_id, self)

        if self.api('plugins.core.proxy:is.mud.connected') and self.api('libs.api:is.character.active')():
            self._eventcb_baseplugin_after_character_is_active()
        else:
            self.api('plugins.core.events:register.to.event')('ev_libs.api_character_active', self._eventcb_baseplugin_after_character_is_active,
                                                      prio=self.is_character_active_priority)

        self.api('libs.plugins.loader:set.plugin.is.loaded')(self.plugin_id)

        self.api('plugins.core.events:add.event')(f"ev_{self.plugin_id}_loaded", self.plugin_id,
                                                    description=[f"Raised when {self.plugin_id} is finished loading"],
                                                    arg_descriptions={'None': None})
        self.api('plugins.core.events:add.event')(f"ev_{self.plugin_id}_unloaded", self.plugin_id,
                                                    description=[f"Raised when {self.plugin_id} is finished unloading"],
                                                    arg_descriptions={'None': None})

        if not self.api.startup:
            self.api('plugins.core.events:raise.event')(f"ev_{self.plugin_id}_loaded")
            self.api('plugins.core.events:raise.event')("ev_plugin_loaded",
                                                     event_args={'plugin_id':self.plugin_id})

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

    @RegisterPluginHook('uninitialize', priority=100)
    def _phook_base_unitialize_hook(self):
        """
        unitialize the plugin

        should be the last thing done in uninitialize
        """
        #save the state
        self.api(f"{self.plugin_id}:save.state")()

        # save data for reloading
        if self.is_reloading_f:
            for item in self.attributes_to_save_on_reload:
                self.api('libs.plugins.reloadutils:add.cache')(self.plugin_id, item, self.__getattribute__(item))

        self.api('plugins.core.events:raise.event')(f"ev_{self.plugin_id}_unloaded")
        self.api('plugins.core.events:raise.event')("ev_plugin_unloaded",
                                                    event_args={'plugin_id':self.plugin_id})

        # remove anything out of the api
        self.api('libs.api:remove')(self.plugin_id)

    def uninitialize(self, _=None):
        """
        uninitialize stuff
        """
        self._process_plugin_hook('uninitialize')

    @RegisterPluginHook('initialize', priority=1)
    def _phook_base_initialize(self):
        """
        initialize the plugin, do most things here
        """
        self.api('plugins.core.settings:add')(self.plugin_id, '_version', 1, int, 'The version of the plugin', hidden=True)

        self.api('plugins.core.events:register.to.event')('ev_libs.net.mud_muddisconnect', self._eventcb_baseplugin_disconnect)

        self.api('plugins.core.events:add.event')(f"ev_{self.plugin_id}_savestate", self.plugin_id,
                                    description=['An event to save the state of the plugin'],
                                    arg_descriptions={'None': None})

    def initialize(self):
        self._process_plugin_hook('initialize')

    @AddAPI('save.state', 'Save the state of the plugin')
    def _api_save_state(self):
        """
        save the state of the plugin
        """
        self._process_plugin_hook('save')
        self.api('plugins.core.events:raise.event')(f"ev_{self.plugin_id}_save")
        self.api('plugins.core.events:raise.event')("ev_plugin_save",
                                                    event_args={'plugin_id':self.plugin_id})

    @AddAPI('reset', 'reset the plugin')
    def _api_reset(self):
        """
        reset the plugin
        """
        event_record = self.api('plugins.core.events:raise.event')("ev_plugin_reset", event_args={'plugin_id':self.plugin_id,
                                                                                   'plugins_that_acted': []})

        return event_record['plugins_that_acted']

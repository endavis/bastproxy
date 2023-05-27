# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/pluginloader.py
#
# File Description: holds the plugin loading mechanics
# and plugin info
#
# By: Bast
"""
holds the plugin loading mechanics and plugin info

it loads core and client plugins, and then passes off
loading all other plugins to plugins.core.pluginm
"""
# Standard Library
import sys
import traceback
import datetime

# 3rd Party

# Project
from libs.dependency import PluginDependencyResolver
from libs.api import API
import libs.imputils as imputils
from plugins._baseplugin import BasePlugin
from libs.records import LogRecord
from libs.info import PluginInfo

class PluginLoader:
    """
    a class to manage plugins
    """
    def __init__(self):
        """
        initialize the instance
        """
        self.api = API(owner_id=__name__)

        self.plugins_info: dict[str, PluginInfo] = {}
        self.base_plugin_dir = API.BASEPLUGINPATH

        self.api('libs.api:add')(__name__, 'is.plugin.loaded', self._api_is_plugin_loaded)
        self.api('libs.api:add')(__name__, 'is.plugin.id', self._api_is_plugin_id)
        self.api('libs.api:add')(__name__, 'does.plugin.exist', self._api_does_plugin_exist)
        self.api('libs.api:add')(__name__, 'get.plugin.instance', self._api_get_plugin_instance)
        self.api('libs.api:add')(__name__, 'get.plugin.module', self._api_get_plugin_module)
        self.api('libs.api:add')(__name__, 'get.loaded.plugins.list', self._api_get_loaded_plugins_list)
        self.api('libs.api:add')(__name__, 'get.packages.list', self._api_get_packages_list)
        self.api('libs.api:add')(__name__, 'get.plugin.info', self._api_get_plugin_info)
        self.api('libs.api:add')(__name__, 'get.all.plugins', self._api_get_all_plugins)
        self.api('libs.api:add')(__name__, 'get.not.loaded.plugins', self._api_get_not_loaded_plugins)
        self.api('libs.api:add')(__name__, 'get.plugins.in.package', self._api_get_plugins_in_package)
        self.api('libs.api:add')(__name__, 'get.all.short.names', self._api_get_all_short_names)
        self.api('libs.api:add')(__name__, 'short.name.convert.plugin.id', self._api_short_name_convert_plugin_id)
        self.api('libs.api:add')(__name__, 'plugin.get.files', self._api_plugin_get_files)
        self.api('libs.api:add')(__name__, 'plugin.get.changed.files', self._api_plugin_get_changed_files)
        self.api('libs.api:add')(__name__, 'plugin.get.invalid.python.files', self._api_plugin_get_invalid_python_files)
        self.api('libs.api:add')(__name__, 'load.plugins', self._api_load_plugins)

    def _api_get_not_loaded_plugins(self):
        """
        get a list of plugins that are not loaded
        """
        if self.update_all_plugin_information():
            LogRecord('conflicts with plugins, see console and correct', level='error', sources=[__name__])()

        all_plugins_by_id = list(self.plugins_info.keys())

        loaded_plugins_by_id = self.api(f"{__name__}:get.loaded.plugins.list")()

        pdiff = set(all_plugins_by_id) - set(loaded_plugins_by_id)

        return list(sorted(pdiff))

    def _api_get_all_plugins(self):
        """
        get all plugins
        """
        return self.plugins_info.keys()

    def _api_get_plugin_info(self, plugin_id):
        """
        get the plugin info for a plugin
        """
        return self.plugins_info[plugin_id]

    def _api_does_plugin_exist(self, plugin_id):
        """
        check if a plugin exists
        """
        return plugin_id in self.plugins_info

    def _api_plugin_get_files(self, plugin_id):
        """
        get the files for a plugin
        """
        return self.plugins_info[plugin_id].get_files()

    def _api_plugin_get_changed_files(self, plugin):
        """
        return a list of files that have changed since loading
        """
        return self.plugins_info[plugin].get_changed_files()

    def _api_plugin_get_invalid_python_files(self, plugin):
        """
        return a list of files that have invalid python syntax
        """
        return self.plugins_info[plugin].get_invalid_python_files()

    # convert a short name to a plugin_id
    def _api_short_name_convert_plugin_id(self, short_name):
        """
        convert a short_name to a plugin_id
        Note: short_names are not guaranteed to be unique
        """
        short_name_list = []
        plugin_id_list = []
        for plugin_id in self.api(f"{__name__}:get.loaded.plugins.list")():
            plugin_info = self.plugins_info[plugin_id]
            short_name_list.append(plugin_info.short_name)
            plugin_id_list.append(plugin_info.plugin_id)

        if found_short_name := self.api('plugins.core.fuzzy:get.best.match')(
            short_name, short_name_list
        ):
            short_name_index = short_name_list.index(found_short_name)
            return plugin_id_list[short_name_index]

        return None

    # get a list of loaded plugins
    def _api_get_loaded_plugins_list(self):
        """
        get the list of loaded plugins

        returns: list of plugin_ids
        """
        return [plugin_info.plugin_id for plugin_info in self.plugins_info.values() if plugin_info.loaded_info.is_loaded]

    # return all short names
    def _api_get_all_short_names(self):
        """
        return a list of all short names
        for loaded plugins
        """
        return [self.plugins_info[plugin_id].short_name for plugin_id in self.api(f"{__name__}:get.loaded.plugins.list")()]

    # get a list of all packages
    def _api_get_packages_list(self):
        """
        return the list of packages
        """
        packages = [plugin_info.package for plugin_info in self.plugins_info.values()]
        packages = list(set(packages))

        return packages

    def _api_get_plugins_in_package(self, package):
        """
        get the list of plugins in a package that have been loaded

        returns: list of plugin_ids
        """
        return [plugin_id for plugin_id in self.api(f"{__name__}:get.loaded.plugins.list")() if self.plugins_info[plugin_id].package == package]

    # get a plugin instance
    def _api_get_plugin_module(self, pluginname):
        """  returns the module of a plugin
        @Ypluginname@w  = the plugin to check for

        returns:
          the module for a plugin"""
        if self.api(f"{__name__}:is.plugin.id")(pluginname) and self.plugins_info[pluginname].loaded_info.is_loaded:
            return self.plugins_info[pluginname].loaded_info.module

        return None

    # get a plugin instance
    def _api_get_plugin_instance(self, plugin_name) -> BasePlugin | None:
        """  get a loaded plugin instance
        @Ypluginname@w  = the plugin to get

        returns:
          if the plugin exists, returns a plugin instance, otherwise returns None"""

        plugin_instance = None

        if isinstance(plugin_name, str):
            if plugin_name in self.plugins_info and self.plugins_info[plugin_name].loaded_info.is_loaded:
                plugin_instance = self.plugins_info[plugin_name].loaded_info.plugin_instance
        elif isinstance(plugin_name, BasePlugin):
            plugin_instance = plugin_name

        if not plugin_instance and not self.api.startup:
            LogRecord(f"api_get_plugin_instance - plugin not found: {plugin_name}", level="debug", sources=[__name__], stack_info=True)()

        return plugin_instance

    # get a plugin instance
    def _api_is_plugin_id(self, plugin_id):
        """  get a loaded plugin instance
        @Ypluginname@w  = the plugin to get

        returns:
          if the plugin exists, returns a plugin instance, otherwise returns None"""
        return bool(
            self.api(f"{__name__}:get.plugin.instance")(plugin_id)
        )

    # check if a plugin is loaded
    def _api_is_plugin_loaded(self, pluginname):
        """  check if a plugin is loaded
        @Ypluginname@w  = the plugin to check for

        returns:
          True if the plugin is loaded, False if not"""
        return bool(
            self.api(f"{__name__}:get.plugin.instance")(pluginname)
        )

    def update_all_plugin_information(self):
        """
        read all plugins and basic info

        returns:
          a bool, True if conflicts with short name were found, False if not
        """
        LogRecord('Read all plugin information', level='info', sources=[__name__])()

        _, plugins, errors = imputils.find_packages_and_plugins(self.base_plugin_dir, 'plugins.')

        old_plugins_info = self.plugins_info
        self.plugins_info = {}

        # go through the plugins and read information from them
        for found_plugin in plugins:
            LogRecord(f'{found_plugin["plugin_id"]:<30} : Reading plugin information', level='info', sources=[__name__])()
            if found_plugin['plugin_id'] in old_plugins_info:
                plugin_info = old_plugins_info[found_plugin['plugin_id']]
                plugin_info.is_plugin = True
                plugin_info.files = {}
            else:
                plugin_info = PluginInfo(plugin_id=found_plugin['plugin_id'])
            plugin_info.full_init_file_path = found_plugin['full_init_file_path']
            plugin_info.full_package_path = found_plugin['full_package_path']
            plugin_info.full_import_location = found_plugin['full_import_location']
            plugin_info.update_from_init()

            if plugin_info.package == 'plugins.core':
                plugin_info.is_required = True

            if plugin_info.full_import_location in errors:
                plugin_info.import_errors.append(errors[plugin_info.full_import_location])

            plugin_info.get_files()

            # print(dumps(info))

            self.plugins_info[plugin_info.plugin_id] = plugin_info

        # warn about plugins whose path is no longer valid
        removed_plugins = set(old_plugins_info.keys()) - set(self.plugins_info.keys())
        for plugin_id in removed_plugins:
            if plugin_id in old_plugins_info and old_plugins_info[plugin_id].loaded_info:
                LogRecord([f'Loaded Plugin {plugin_id}\'s path is no longer valid: {old_plugins_info[plugin_id].full_package_path}',
                           'If this plugin is no longer valid, please unload it'], level='error', sources=[__name__])()

    def _import_single_plugin(self, plugin_id, exit_on_error: bool = False):
        """
        import a plugin module

        arguments:
          required:
            fullpath - the full path to the file on disk

          optional:
            exit_on_error - if True, the program will exit on an error

        returns:
          True if the plugin was imported, False otherwise
        """
        # import the plugin
        LogRecord(f"{plugin_id:<30} : attempting import", level='info', sources=[__name__])()
        return_info = \
              imputils.importmodule(plugin_id)
        plugin_info = self.plugins_info[plugin_id]
        if (not return_info['success']
                or not return_info['module']
                or not return_info['full_import_location']):
            plugin_info.loaded_info.is_imported = False

            if return_info['message'] == 'error':
                exc_msg = [line.strip() for line in traceback.format_exception(return_info['exception']) if line.strip() not in  ['\n', '']]

                msg = [f"Could not import plugin {plugin_id}",
                        *exc_msg]
                LogRecord(msg, level='error', sources=[__name__])()
                if exit_on_error:
                    sys.exit(1)

            return False

        plugin_info.loaded_info.module = return_info['module']
        plugin_info.loaded_info.is_imported = True
        plugin_info.loaded_info.imported_time =  datetime.datetime.now(datetime.timezone.utc)
        LogRecord(f"{plugin_id:<30} : imported successfully", level='info', sources=[__name__])()
        return True

    def _instantiate_single_plugin(self, plugin_id, exit_on_error=False):
        """
        instantiate a single plugin

        arguments:
          required:
            plugin_id - the plugin to load

          optional:
            exit_on_error - if True, the program will exit on an error

        returns:
          True if the plugin was instantiated, False otherwise
        """
        plugin_info = self.plugins_info[plugin_id]
        LogRecord(f"{plugin_id:<30} : creating instance", level='info', sources=[__name__])()

        if not plugin_info.loaded_info.module:
            LogRecord(f"Could not find module for {plugin_id}", level='error',
                      sources=[__name__])()
            if exit_on_error:
                sys.exit(1)
            else:
                return False
        try:
            plugin_instance = plugin_info.loaded_info.module.Plugin(
                                                plugin_info.name,
                                                plugin_info.full_package_path,
                                                self.base_plugin_dir,
                                                plugin_info.full_import_location,
                                                plugin_info.plugin_id)
        except Exception: # pylint: disable=broad-except
            LogRecord(f"Could not instantiate plugin {plugin_id}", level='error',
                      sources=[__name__], exc_info=True)()
            if exit_on_error:
                sys.exit(1)
            else:
                return False

        plugin_instance.author =  plugin_info.author
        plugin_instance.purpose = plugin_info.purpose
        plugin_instance.version = plugin_info.version

        # set the plugin instance
        plugin_info.loaded_info.plugin_instance = plugin_instance
        plugin_info.loaded_info.is_initialized = False

        LogRecord(f"{plugin_id:<30} : instance created successfully", level='info', sources=[__name__])()

        return True

    # initialize a plugin
    def _initialize_single_plugin(self, plugin_id: str, exit_on_error=False):
        """
        run the initialize method for a plugin

        arguments:
          required:
            plugin - the plugin to initialize, the dict from loaded_plugins

          optional:
            exit_on_error - if True, the program will exit on an error

        returns:
          True if the plugin was initialized, False otherwise
        """
        # don't do anything if the plugin has already been initialized
        plugin_info = self.plugins_info[plugin_id]
        if plugin_info.loaded_info.is_initialized:
            return True
        LogRecord(f"{plugin_info.plugin_id:<30} : attempting to initialize ({plugin_info.name})", level='info',
                  sources=[__name__, plugin_info.plugin_id])()

        if not plugin_info.loaded_info.plugin_instance:
            LogRecord(f"{plugin_info.plugin_id:<30} : plugin instance is None, not initializing", level='error',
                        sources=[__name__, plugin_info.plugin_id])()
            return False

        # run the initialize function
        try:
            plugin_info.loaded_info.plugin_instance.initialize_with_hooks()
            plugin_info.loaded_info.is_initialized = True

        except Exception: # pylint: disable=broad-except
            LogRecord(f"could not run the initialize function for {plugin_info.plugin_id}", level='error',
                      sources=[__name__, plugin_info.plugin_id], exc_info=True)()
            if exit_on_error:
                LogRecord(f"{plugin_info.plugin_id:<30} : DID NOT INITIALIZE", level='error',
                          sources=[__name__, plugin_info.plugin_id])()
                sys.exit(1)
            return False

        LogRecord(f"{plugin_info.plugin_id:<30} : successfully initialized ({plugin_info.name})", level='info',
                    sources=[__name__, plugin_info.plugin_id])()

        LogRecord(f"{plugin_info.plugin_id:<30} : successfully loaded", level='info',
                  sources=[__name__, plugin_info.plugin_id])()

        plugin_info.loaded_info.is_loaded = True

        return True

    def _api_load_plugins(self, plugins_to_load, exit_on_error=False, check_dependencies=True):
        """
        load a list of plugins
        """
        plugins_not_loaded = [plugin_id for plugin_id in plugins_to_load if not self.plugins_info[plugin_id].loaded_info.is_loaded]
        already_loaded_plugins = set(plugins_to_load) - set(plugins_not_loaded)

        bad_plugins = []

        # import plugins
        for plugin_id in plugins_not_loaded:
            LogRecord(f"{plugin_id:<30} : attempting to load", level='info', sources=[__name__])()
            if not self._import_single_plugin(plugin_id, exit_on_error=exit_on_error):
                bad_plugins.append(plugin_id)

        plugins_not_loaded = [plugin_id for plugin_id in plugins_not_loaded if plugin_id not in bad_plugins]

        # instantiate plugins
        for plugin_id in plugins_not_loaded:
            if not self._instantiate_single_plugin(plugin_id, exit_on_error=exit_on_error):
                bad_plugins.append(plugin_id)

        plugins_not_loaded = [plugin_id for plugin_id in plugins_not_loaded if plugin_id not in bad_plugins]

        # check dependencies
        # if check_dependencies:
        #     if plugin_instance := self.loaded_plugins_info[
        #         plugin_id
        #     ].plugininstance:
        #         dependencies = plugin_instance.dependencies
        #     else:
        #         dependencies = []

        #     for dependency in dependencies:
        #         # import and instantiate dependencies and add their dependencies to list
        #         return_value, new_dependencies = self.preinitialize_plugin(dependency)
        #         if return_value:
        #             all_dependencies.append(dependency)
        #             all_dependencies.extend(new_dependencies)
        #

        plugins_not_loaded = [plugin_id for plugin_id in plugins_not_loaded if plugin_id not in bad_plugins]

        # initialize plugins
        for plugin_id in plugins_not_loaded:
            if not self._initialize_single_plugin(plugin_id, exit_on_error=exit_on_error):
                bad_plugins.append(plugin_id)

        loaded_plugins = [plugin_id for plugin_id in plugins_not_loaded if plugin_id not in bad_plugins]

        # clean up plugins that were not imported, initialized, or instantiated
        for plugin_id in plugins_to_load:
            plugin_info = self.plugins_info[plugin_id]
            if not plugin_info.loaded_info.is_loaded:
                if plugin_info.loaded_info.plugin_instance:
                    del plugin_info.loaded_info.plugin_instance
                    plugin_info.loaded_info.plugin_instance = None
                if plugin_info.loaded_info.module:
                    # TODO: unload all the modules in a plugin
                    del plugin_info.loaded_info.module
                    plugin_info.loaded_info.module = None

        if bad_plugins and exit_on_error:
            sys.exit(1)

        return {'loaded_plugins': loaded_plugins, 'bad_plugins': bad_plugins, 'already_loaded_plugins': already_loaded_plugins}

    def _unload_single_plugin(self, plugin_id):
        """
        unload a plugin
          1) run uninitialize function
          2) destroy instance
          3) remove all files in package from sys.modules
          4) set the appropriate plugin_info.loaded_info attributes to None

        arguments:
          required:
            plugin_id - the plugin to unload

          optional:
            exit_on_error - if True, the program will exit on an error

        returns:
          True if the plugin was unloaded, False otherwise
        """
        try:
            plugin_info = self.plugins_info[plugin_id]
        except Exception:
            return False

        if plugin_info.loaded_info.plugin_instance and not plugin_info.loaded_info.plugin_instance.can_reload_f:
            LogRecord(f"{plugin_info.plugin_id:<30} : this plugin cannot be unloaded ({plugin_info.name})",
                        level='error', sources=[__name__, plugin_info.plugin_id])()
            return False

        try:
            # run the uninitialize function if it exists
            if plugin_info.loaded_info.plugin_instance:
                if plugin_info.loaded_info.is_initialized:
                        plugin_info.loaded_info.plugin_instance.uninitialize()

                LogRecord(f"{plugin_info.plugin_id:<30} : successfully unitialized ({plugin_info.name})", level='info',
                        sources=[__name__, plugin_info.plugin_id])()
            else:
                LogRecord(f"{plugin_info.plugin_id:<30} : plugin instance not found ({plugin_info.name})", level='info',
                        sources=[__name__, plugin_info.plugin_id])()

        except Exception: # pylint: disable=broad-except
            LogRecord(f"unload: error running the uninitialize method for {plugin_info.plugin_id}", level='error',
                        sources=[__name__, plugin_info.plugin_id], exc_info=True)()
            return False

        # # remove from pluginstoload so it doesn't load at startup
        # plugins_to_load = self.api(f"{self.plugin_id}:setting.get")('pluginstoload')
        # if plugin_info.plugin_id in plugins_to_load:
        #     plugins_to_load.remove(plugin_info.plugin_id)
        #     self.api(f"{self.plugin_id}:setting.change")('pluginstoload', plugins_to_load)

        if plugin_info.loaded_info.plugin_instance:
            # delete the instance
            del plugin_info.loaded_info.plugin_instance

        if plugin_info.loaded_info.is_imported:
            # TODO: remove all the modules in a plugin from sys.modules
            if imputils.deletemodule(
                plugin_info.full_import_location
            ):
                LogRecord(f"{plugin_info.plugin_id:<30} : deleting imported module was successful ({plugin_info.name})",
                            level='info', sources=[__name__, plugin_info.plugin_id])()
            else:
                LogRecord(f"{plugin_info.plugin_id:<30} : deleting imported module failed ({plugin_info.name})",
                            level='error', sources=[__name__, plugin_info.plugin_id])()

        # set the appropriate plugin_info.loaded_info attributes to None
        plugin_info.reset_loaded_info()

        return True

    def _load_core_and_client_plugins_on_startup(self):
        """
        load plugins on startup
        start with plugins that have REQUIRED=True, then move
        to plugins that were loaded in the config
        """
        if self.update_all_plugin_information():
            LogRecord(
                "conflicts with plugins, see console and correct",
                level='error',
                sources=[__name__],
            )(actor = f"{__name__}.read_all_plugin_information")
            sys.exit(1)

        # load all core plugins first
        core_plugins = [plugin_info.plugin_id for plugin_info in self.plugins_info.values() \
                                           if plugin_info.package in ['plugins.core', 'plugins.client']]

        # load plugin manager and then log plugin first
        core_plugins.remove('plugins.core.log')
        core_plugins.insert(0, 'plugins.core.log')

        core_plugins.remove('plugins.core.pluginm')
        core_plugins.insert(0, 'plugins.core.pluginm')

        # print(f"loading core plugins: {core_plugins}")
        self.api(f"{__name__}:load.plugins")(core_plugins, exit_on_error=True, check_dependencies=False)

    def initialize(self):
        """
        initialize the plugin loader
        """
        LogRecord('Loading core and client plugins', level='info', sources=[__name__])()
        self._load_core_and_client_plugins_on_startup()

        self.api('plugins.core.managers:add')('plugins', self)

        self.api('plugins.core.events:raise.event')(f"ev_{__name__}_post_startup_plugins_initialize")

        # warn about plugins that had import errors
        for plugin_info in self.plugins_info.values():
            if plugin_info.import_errors:
                for error in plugin_info.import_errors:
                    traceback_message = traceback.format_exception(error[1])
                    traceback_message = [item.strip() for item in traceback_message if item and item != '\n']
                    LogRecord([f'Plugin {plugin_info.plugin_id} had an import error: ', *traceback_message],
                                level='warning', sources=[__name__])()

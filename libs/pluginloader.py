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
import weakref
import contextlib
from functools import partial

# 3rd Party

# Project
from libs.dependency import PluginDependencyResolver
from libs.api import API, AddAPI
import libs.imputils as imputils
from plugins._baseplugin import BasePlugin, patch
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

        self.weak_references_to_modules = {}

        self.plugins_info: dict[str, PluginInfo] = {}
        self.base_plugin_dir = API.BASEPLUGINPATH

        self.api('libs.api:add.apis.for.object')(__name__, self)

    @AddAPI('get.unloaded.plugins.in.memory', description='get all plugins')
    def _api_get_unloaded_plugins_in_memory(self):
        """
        get a list of unloaded plugins that have not been garbage collected
        """
        return self.weak_references_to_modules.keys()

    def remove_weakref(self, weakref_obj, module_import_path):
        """
        remove a weak reference to a module
        """
        old_object = weakref_obj()
        if not old_object and not self.api.shutdown:
            LogRecord(f"{module_import_path} was garbage collected", level='info', sources=[__name__])()
            if module_import_path in self.weak_references_to_modules:
                del self.weak_references_to_modules[module_import_path]

    @AddAPI('get.not.loaded.plugins', description='get a list of plugins that are not loaded')
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

    @AddAPI('get.all.plugins', description='get all plugins')
    def _api_get_all_plugins(self):
        """
        get all plugins
        """
        return self.plugins_info.keys()

    @AddAPI('get.plugin.info', description='get the plugin info for a plugin')
    def _api_get_plugin_info(self, plugin_id):
        """
        get the plugin info for a plugin
        """
        return self.plugins_info[plugin_id]

    @AddAPI('does.plugin.exist', description='check if a plugin exists')
    def _api_does_plugin_exist(self, plugin_id):
        """
        check if a plugin exists
        """
        return plugin_id in self.plugins_info

    @AddAPI('plugin.get.changed.files', description='get the list of files that have changed since loading for a plugin')
    def _api_plugin_get_changed_files(self, plugin):
        """
        return a list of files that have changed since loading
        """
        return self.plugins_info[plugin].get_changed_files()

    @AddAPI('plugin.get.invalid.python.files', description='get the list of files that have invalid python syntax for a plugin')
    def _api_plugin_get_invalid_python_files(self, plugin):
        """
        return a list of files that have invalid python syntax
        """
        return self.plugins_info[plugin].get_invalid_python_files()

    @AddAPI('get.loaded.plugins.list', description='get the list of loaded plugins')
    def _api_get_loaded_plugins_list(self):
        """
        get the list of loaded plugins

        returns: list of plugin_ids
        """
        return [plugin_info.plugin_id for plugin_info in self.plugins_info.values() if plugin_info.runtime_info.is_loaded]

    @AddAPI('get.packages.list', description='get the list of packages')
    def _api_get_packages_list(self, active_only=False):
        """
        return the list of packages
        """
        if active_only:
            packages = [plugin_info.package for plugin_info in self.plugins_info.values() if plugin_info.runtime_info.is_loaded]
        else:
            packages = [plugin_info.package for plugin_info in self.plugins_info.values()]

        packages = list(set(packages))

        return packages

    @AddAPI('get.plugins.in.package', description='get the list of plugins in a package that have been loaded')
    def _api_get_plugins_in_package(self, package):
        """
        get the list of plugins in a package that have been loaded

        returns: list of plugin_ids
        """
        return [plugin_id for plugin_id in self.api(f"{__name__}:get.loaded.plugins.list")() if self.plugins_info[plugin_id].package == package]

    @AddAPI('get.plugin.instance', description='get a loaded plugin instance')
    def _api_get_plugin_instance(self, plugin_name) -> BasePlugin | None:
        """  get a loaded plugin instance
        @Ypluginname@w  = the plugin to get

        returns:
          if the plugin exists, returns a plugin instance, otherwise returns None"""

        plugin_instance = None

        if isinstance(plugin_name, str):
            if plugin_name in self.plugins_info and self.plugins_info[plugin_name].runtime_info.is_loaded:
                plugin_instance = self.plugins_info[plugin_name].runtime_info.plugin_instance
        elif isinstance(plugin_name, BasePlugin):
            plugin_instance = plugin_name

        if not plugin_instance and not self.api.startup:
            LogRecord(f"api_get_plugin_instance - plugin not found: {plugin_name}", level="debug", sources=[__name__], stack_info=True)()

        return plugin_instance

    @AddAPI('is.plugin.id', description='check if a str is a plugin id')
    def _api_is_plugin_id(self, plugin_id):
        """  check if a string is a plugin id
        @Yplugin_id@w  = the string id to check

        returns:
          returns True if the plugin is an id, False if not"""

        return plugin_id in self.plugins_info

    @AddAPI('is.plugin.loaded', description='check if a plugin is loaded')
    def _api_is_plugin_loaded(self, pluginname):
        """  check if a plugin is loaded
        @Ypluginname@w  = the plugin to check for

        returns:
          True if the plugin is loaded, False if not"""
        plugin_instance = self.api(f"{__name__}:get.plugin.instance")(pluginname)

        return bool(plugin_instance and plugin_instance.is_inititalized_f)

    def update_all_plugin_information(self):
        """
        read all plugins and basic info

        returns:
          a bool, True if conflicts with short name were found, False if not
        """
        LogRecord('Read all plugin information', level='info', sources=[__name__])()

        _, plugins, errors = imputils.find_packages_and_plugins(self.base_plugin_dir, 'plugins.')

        LogRecord('Done finding plugins', level='debug', sources=[__name__])()

        old_plugins_info = self.plugins_info
        new_plugins_info = {}

        # go through the plugins and read information from them
        for found_plugin in plugins:
            LogRecord(f'{found_plugin["plugin_id"]:<30} : Reading plugin information', level='info', sources=[__name__])()
            if found_plugin['plugin_id'] in old_plugins_info:
                plugin_info = old_plugins_info[found_plugin['plugin_id']]
                plugin_info.is_plugin = True
                plugin_info.files = {}
            else:
                plugin_info = PluginInfo(plugin_id=found_plugin['plugin_id'])
            plugin_info.package_init_file_path = found_plugin['package_init_file_path']
            plugin_info.package_path = found_plugin['package_path']
            plugin_info.package_import_location = found_plugin['package_import_location']
            plugin_info.data_directory = self.api.BASEDATAPLUGINPATH / plugin_info.plugin_id

            plugin_info.update_from_init()

            if plugin_info.package == 'plugins.core':
                plugin_info.is_required = True

            if plugin_info.package_import_location in errors:
                plugin_info.import_errors.append(errors[plugin_info.package_import_location])

            plugin_info.get_file_data()

            new_plugins_info[plugin_info.plugin_id] = plugin_info

        self.plugins_info = new_plugins_info

        # warn about plugins whose path is no longer valid
        removed_plugins = set(old_plugins_info.keys()) - set(self.plugins_info.keys())
        for plugin_id in removed_plugins:
            if plugin_id in old_plugins_info and old_plugins_info[plugin_id].runtime_info:
                LogRecord([f'Loaded Plugin {plugin_id}\'s path is no longer valid: {old_plugins_info[plugin_id].package_path}',
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
        plugin_info = self.plugins_info[plugin_id]
        return_info = \
              imputils.importmodule(plugin_info.plugin_class_import_location)
        if (not return_info['success']
                or not return_info['module']
                or not return_info['full_import_location']):
            plugin_info.runtime_info.is_imported = False

            if return_info['message'] == 'error':
                exc_msg = [line.strip() for line in traceback.format_exception(return_info['exception']) if line.strip() not in  ['\n', '']]

                msg = [f"Could not import plugin {plugin_id}",
                        *exc_msg]
                LogRecord(msg, level='error', sources=[__name__])()
                if exit_on_error:
                    sys.exit(1)

            return False

        plugin_info.runtime_info.is_imported = True
        plugin_info.runtime_info.imported_time =  datetime.datetime.now(datetime.timezone.utc)

        LogRecord(f"{plugin_id:<30} : imported successfully", level='info', sources=[__name__])()

        # check for patches to the base plugin
        if (patch_file:= plugin_info.find_file_by_name('_patch_base.py')) and not plugin_info.has_been_reloaded:
            if len(patch_file) > 1:
                LogRecord(f"{plugin_id:<30} : found more than one _patch_base.py file, only the first will be used", level='warning', sources=[__name__])()
            patch_file = patch_file[0]
            LogRecord(f"{plugin_id:<30} : attempting to patch base", level='info', sources=[__name__])()
            if patch(patch_file['full_import_location']):
                LogRecord(f"{plugin_id:<30} : patching base successful", level='info', sources=[__name__])()
            else:
                LogRecord(f"{plugin_id:<30} : patching base failed", level='error', sources=[__name__])()

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

        if not plugin_info.plugin_class_import_location:
            LogRecord(f"Could not find module for {plugin_id}", level='error',
                      sources=[__name__])()
            if exit_on_error:
                sys.exit(1)
            else:
                return False
        try:
            plugin_module = sys.modules[str(plugin_info.plugin_class_import_location)]
            plugin_instance = plugin_module.Plugin(
                                                plugin_info.plugin_id,
                                                plugin_info)
        except Exception: # pylint: disable=broad-except
            LogRecord(f"Could not instantiate plugin {plugin_id}", level='error',
                      sources=[__name__], exc_info=True)()
            if exit_on_error:
                sys.exit(1)
            else:
                self.api(f'{__name__}:unload.plugin')(plugin_id)
                return False

        # set the plugin instance
        plugin_info.runtime_info.plugin_instance = plugin_instance
        plugin_info.runtime_info.is_loaded = False

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
        if plugin_info.runtime_info.is_loaded:
            return True
        LogRecord(f"{plugin_info.plugin_id:<30} : attempting to initialize ({plugin_info.name})", level='info',
                  sources=[__name__, plugin_info.plugin_id])()

        if not plugin_info.runtime_info.plugin_instance:
            LogRecord(f"{plugin_info.plugin_id:<30} : plugin instance is None, not initializing", level='error',
                        sources=[__name__, plugin_info.plugin_id])()
            return False

        # run the initialize function
        try:
            plugin_info.runtime_info.plugin_instance.initialize()

        except Exception: # pylint: disable=broad-except
            LogRecord(f"could not run the initialize function for {plugin_info.plugin_id}", level='error',
                      sources=[__name__, plugin_info.plugin_id], exc_info=True)()
            if exit_on_error:
                LogRecord(f"{plugin_info.plugin_id:<30} : DID NOT INITIALIZE", level='error',
                          sources=[__name__, plugin_info.plugin_id])()
                sys.exit(1)
            self.api(f'{__name__}:unload.plugin')(plugin_id)
            return False

        LogRecord(f"{plugin_info.plugin_id:<30} : successfully initialized ({plugin_info.name})", level='info',
                    sources=[__name__, plugin_info.plugin_id])()

        LogRecord(f"{plugin_info.plugin_id:<30} : successfully loaded", level='info',
                  sources=[__name__, plugin_info.plugin_id])()

        return True

    @AddAPI('load.plugins', 'load a list of plugins')
    def _api_load_plugins(self, plugins_to_load, exit_on_error=False, check_dependencies=True):
        """
        load a list of plugins
        """
        plugins_not_loaded = [plugin_id for plugin_id in plugins_to_load if not self.plugins_info[plugin_id].runtime_info.is_loaded]
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
            if not plugin_info.runtime_info.is_loaded:
                if plugin_info.runtime_info.plugin_instance:
                    del plugin_info.runtime_info.plugin_instance
                    plugin_info.runtime_info.plugin_instance = None
                for item in plugin_info.files:
                    with contextlib.suppress(Exception):
                        del sys.modules[item['full_import_location']]
                with contextlib.suppress(Exception):
                    del sys.modules[plugin_info.package_import_location]

        if bad_plugins and exit_on_error:
            sys.exit(1)

        return {'loaded_plugins': loaded_plugins, 'bad_plugins': bad_plugins, 'already_loaded_plugins': already_loaded_plugins}

    @AddAPI('reload.plugin', 'reload a plugin')
    def _api_reload_plugin(self, plugin_id):
        """
        reload a single plugin
        """
        return (
            self.api(f'{__name__}:load.plugins')(
                [plugin_id], exit_on_error=False, check_dependencies=True
            )
            if self.api(f'{__name__}:unload.plugin')(plugin_id)
            else False
        )

    @AddAPI('set.plugin.is.loaded', 'set the initialized flag for a plugin')
    def _api_set_plugin_is_loaded(self, plugin_id):
        """
        set the is loaded flag for a plugin
        """
        self.plugins_info[plugin_id].runtime_info.is_loaded = True

    @AddAPI('unload.plugin', 'unload a plugin')
    def _api_unload_plugin(self, plugin_id):
        """
        unload a plugin
          1) run uninitialize function
          2) destroy instance
          3) remove all files in package from sys.modules
          4) set the appropriate plugin_info.runtime_info attributes to None

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

        if plugin_info.runtime_info.plugin_instance and not plugin_info.runtime_info.plugin_instance.can_reload_f:
            LogRecord(f"{plugin_info.plugin_id:<30} : this plugin cannot be unloaded ({plugin_info.name})",
                        level='error', sources=[__name__, plugin_info.plugin_id])()
            return False

        try:
            # run the uninitialize function if it exists
            if plugin_info.runtime_info.plugin_instance:
                if plugin_info.runtime_info.is_loaded:
                        plugin_info.runtime_info.plugin_instance.uninitialize()

                LogRecord(f"{plugin_info.plugin_id:<30} : successfully unitialized ({plugin_info.name})", level='info',
                        sources=[__name__, plugin_info.plugin_id])()
            else:
                LogRecord(f"{plugin_info.plugin_id:<30} : plugin instance not found ({plugin_info.name})", level='info',
                        sources=[__name__, plugin_info.plugin_id])()

        except Exception: # pylint: disable=broad-except
            LogRecord(f"unload: error running the uninitialize method for {plugin_info.plugin_id}", level='error',
                        sources=[__name__, plugin_info.plugin_id], exc_info=True)()
            return False

        # remove from pluginstoload so it doesn't load at startup
        plugins_to_load = self.api('plugins.core.settings:get')('plugins.core.pluginm', 'pluginstoload')
        if plugin_info.plugin_id in plugins_to_load:
            plugins_to_load.remove(plugin_info.plugin_id)
            self.api('plugins.core.settings:change')('plugins.core.pluginm', 'pluginstoload', plugins_to_load)

        if plugin_info.runtime_info.plugin_instance:
            # delete the instance
            del plugin_info.runtime_info.plugin_instance

        modules_to_delete = []
        if plugin_info.runtime_info.is_imported:
            modules_to_delete.extend(
                item
                for item in sys.modules.keys()
                if item.startswith(plugin_info.package_import_location) and getattr(sys.modules[item], 'CANRELOAD', True)
            )

        for item in modules_to_delete:
            cb_weakref = partial(self.remove_weakref, module_import_path=item)
            self.weak_references_to_modules[item] = weakref.ref(sys.modules[item], cb_weakref)
            if imputils.deletemodule(
                item
            ):
                LogRecord(f"{plugin_info.plugin_id:<30} : deleting imported module {item} was successful ({plugin_info.name})",
                            level='info', sources=[__name__, plugin_info.plugin_id])()
            else:
                LogRecord(f"{plugin_info.plugin_id:<30} : deleting imported module {item} failed ({plugin_info.name})",
                            level='error', sources=[__name__, plugin_info.plugin_id])()

        plugin_info.has_been_reloaded = True

        # set the appropriate plugin_info.runtime_info attributes to None
        plugin_info.reset_runtime_info()

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

        # print(f"loading core plugins: {core_plugins}")
        self.api(f"{__name__}:load.plugins")(core_plugins, exit_on_error=True, check_dependencies=False)

    def initialize(self):
        """
        initialize the plugin loader
        """
        LogRecord('Loading core and client plugins', level='info', sources=[__name__])()
        self._load_core_and_client_plugins_on_startup()

        LogRecord(f'ev_{__name__}_post_startup_plugins_initialize: Started', level='debug', sources=[__name__])()

        self.api('plugins.core.events:raise.event')(f"ev_{__name__}_post_startup_plugins_initialize")

        LogRecord(f'ev_{__name__}_post_startup_plugins_initialize: Finish', level='debug', sources=[__name__])()

        # warn about plugins that had import errors
        for plugin_info in self.plugins_info.values():
            if plugin_info.import_errors:
                for error in plugin_info.import_errors:
                    traceback_message = traceback.format_exception(error[1])
                    traceback_message = [item.strip() for item in traceback_message if item and item != '\n']
                    LogRecord([f'Plugin {plugin_info.plugin_id} had an import error: ', *traceback_message],
                                level='warning', sources=[__name__])()

        LogRecord('Finished Loading core and client plugins', level='info', sources=[__name__])()

    @AddAPI('fuzzy.match.plugin.id', description='find a plugin id from a string')
    def _api_fuzzy_match_plugin_id(self, plugin_id_string: str, active_only = False) -> tuple[str, str]:
        """
        find a command from the client
        return bool (found), package. plugin_id, message
        """
        LogRecord(f"find_plugin: {plugin_id_string}",
                  level='debug',
                  sources=[__name__])()

        psplit = plugin_id_string.split('.', 1)

        if len(psplit) not in [2, 3]:
            return '', ''

        if len(psplit) == 2:
            tmp_package = f"plugins.{psplit[0]}"
            tmp_plugin = psplit[1]
        else:
            tmp_package = f"plugins.{psplit[1]}"
            tmp_plugin = psplit[2]

        loaded_list = self.api(f'{__name__}:get.loaded.plugins.list')()
        package_list = self.api(f"{__name__}:get.packages.list")(active_only)

        # try and find the package
        new_package = self.api('plugins.core.fuzzy:get.best.match')(tmp_package, tuple(package_list),
                                                                scorer='token_set_ratio')

        if not new_package:
            return '', ''

        # try and find the plugin
        new_plugin = self.api('plugins.core.fuzzy:get.best.match')(f"{new_package}.{tmp_plugin}",
                                                                   tuple(loaded_list),
                                                                   scorer='token_set_ratio')

        return new_package, new_plugin

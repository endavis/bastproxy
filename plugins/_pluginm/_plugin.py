# pylint: disable=too-many-lines
# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/_manager/_plugin.py
#
# File Description: holds the plugin manager
#
# By: Bast
"""
manages all plugins
"""
# Standard Library
import sys
import signal
import traceback
import datetime
from pathlib import Path

# 3rd Party

# Project
from libs.dependency import PluginDependencyResolver
from libs.api import API
import libs.imputils as imputils
from plugins._baseplugin import BasePlugin
from libs.records import LogRecord
from libs.info import PluginInfo
from libs.commands import AddParser, AddArgument
from libs.event import RegisterToEvent

class PluginManager(BasePlugin):
    """
    a class to manage plugins
    """
    def __init__(self):
        """
        initialize the instance
        """
        super().__init__('Plugin Manager', #name,
                      Path(sys.modules[__name__].__file__), #plugin_path
                      API.BASEPLUGINPATH, # base_plugin_dir
                      'plugins._pluginm', # full_import_location
                      'plugins.core.pluginm' # plugin_id
            )

        self.author = 'Bast'
        self.purpose = 'Manage plugins'
        self.can_reload = False
        self.version = 1

        self.plugins_info: dict[str, PluginInfo] = {}

        self.plugin_info_line_format = "{plugin_id:<30} : {name:<25} {author:<10} {version:<5} {purpose}@w"

        self.api('libs.api:add')(self.plugin_id, 'is.plugin.loaded', self._api_is_plugin_loaded)
        self.api('libs.api:add')(self.plugin_id, 'is.plugin.id', self._api_is_plugin_id)
        self.api('libs.api:add')(self.plugin_id, 'get.plugin.instance', self._api_get_plugin_instance)
        self.api('libs.api:add')(self.plugin_id, 'get.plugin.module', self._api_get_plugin_module)
        self.api('libs.api:add')(self.plugin_id, 'get.all.plugin.info', self._api_get_all_plugin_info)
        self.api('libs.api:add')(self.plugin_id, 'save.all.plugins.state', self._api_save_all_plugins_state)
        self.api('libs.api:add')(self.plugin_id, 'get.loaded.plugins.list', self._api_get_loaded_plugins_list)
        self.api('libs.api:add')(self.plugin_id, 'get.packages.list', self._api_get_packages_list)
        self.api('libs.api:add')(self.plugin_id, 'get.plugins.in.package', self._api_get_plugins_in_package)
        self.api('libs.api:add')(self.plugin_id, 'get.all.short.names', self._api_get_all_short_names)
        self.api('libs.api:add')(self.plugin_id, 'short.name.convert.plugin.id', self._api_short_name_convert_plugin_id)
        self.api('libs.api:add')(self.plugin_id, 'plugin.get.files', self._api_plugin_get_files)
        self.api('libs.api:add')(self.plugin_id, 'plugin.get.changed.files', self._api_plugin_get_changed_files)
        self.api('libs.api:add')(self.plugin_id, 'plugin.get.invalid.python.files', self._api_plugin_get_invalid_python_files)

        self.api(f"{self.plugin_id}:setting.add")('pluginstoload', [], list,
                                'plugins to load on startup',
                                readonly=True)

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
        for plugin_id in self.api('plugins.core.pluginm:get.loaded.plugins.list')():
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
        return [self.plugins_info[plugin_id].short_name for plugin_id in self.api('plugins.core.pluginm:get.loaded.plugins.list')()]

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
        return [plugin_id for plugin_id in self.api('plugins.core.pluginm:get.loaded.plugins.list')() if self.plugins_info[plugin_id].package == package]

    # return the dictionary of all plugins
    def _api_get_all_plugin_info(self):
        """
        return the plugin_info dictionary

        returns:
          a dictionary with keys of plugin_id
        """
        return self.plugins_info

    def find_loaded_plugin(self, plugin):
        """
        find a plugin

        arguments:
          required:
            plugin - the plugin to find

        returns:
          if found, returns a plugin object, else returns None
        """
        return self.api(f"{self.plugin_id}:get.plugin.instance")(plugin)

    # get a plugin instance
    def _api_get_plugin_module(self, pluginname):
        """  returns the module of a plugin
        @Ypluginname@w  = the plugin to check for

        returns:
          the module for a plugin"""
        if self.api(f"{self.plugin_id}:is.plugin.id")(pluginname) and self.plugins_info[pluginname].loaded_info.is_loaded:
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
            LogRecord(f"api_get_plugin_instance - plugin not found: {plugin_name}", level="debug", sources=[self.plugin_id], stack_info=True)()

        return plugin_instance

    # get a plugin instance
    def _api_is_plugin_id(self, plugin_id):
        """  get a loaded plugin instance
        @Ypluginname@w  = the plugin to get

        returns:
          if the plugin exists, returns a plugin instance, otherwise returns None"""
        return bool(
            self.api(f"{self.plugin_id}:get.plugin.instance")(plugin_id)
        )

    # check if a plugin is loaded
    def _api_is_plugin_loaded(self, pluginname):
        """  check if a plugin is loaded
        @Ypluginname@w  = the plugin to check for

        returns:
          True if the plugin is loaded, False if not"""
        return bool(
            self.api(f"{self.plugin_id}:get.plugin.instance")(pluginname)
        )

    def _command_helper_format_plugin_list(self, plugins, header='', columnheader=True,
                                           required_color_line=True) -> list[str]:
        """
        format a list of loaded plugins to return to client

        plugins = a list of plugin_info objects
        """
        required_color = '@x75'
        msg = []

        if columnheader:
            msg.extend([
                self.api('plugins.core.utils:center.colored.string')(
                    f'@x86{header}@w', '-', 80, filler_color='@B'
            )])
            msg.append(self.plugin_info_line_format.format(
                        **{'plugin_id':'Id/Location', 'name':'Name', 'author':'Author',
                          'version':'Vers', 'purpose':'Purpose'}))
        msg.append('-' * 75)

        foundrequired = False
        for plugin_id in plugins:
            plugin_info = self.plugins_info[plugin_id]
            plugin_color = required_color if (plugin_info.plugin_id in self.plugins_info
                and plugin_info.is_required) else ''
            if plugin_color:
                foundrequired = True
            msg.append(
                ''.join([plugin_color,
                    self.plugin_info_line_format.format(**plugin_info.__dict__)])
        )

        if foundrequired and required_color_line:
            msg.extend(('', f'* {required_color}Required plugins appear in this color@w'))
        return msg

    # get a message of plugins in a package
    def _get_package_plugins(self, package):
        """
        create a message of loaded plugins in a package

        arguments:
          required:
            package - the package name

        returns:
          a list of strings of loaded plugins in the specified package
        """
        msg = []
        if 'plugins' not in package:
            if package.startswith('.'):
                package = f"plugins{package}"
            else:
                package = f"plugins.{package}"

        loaded_plugins = self.api('plugins.core.pluginm:get.loaded.plugins.list')()
        if plist := [
            plugin_id
            for plugin_id in loaded_plugins
            if self.plugins_info[plugin_id].package == package
        ]:
            plugins = sorted(plist)
            mod = __import__(package)
            try:
                desc = getattr(mod, package).PACKAGE_DESCRIPTION
            except AttributeError:
                desc = ''
            msg.extend(self._command_helper_format_plugin_list(plugins,
                                                    f"Plugins in {package}{f' - {desc}' if desc else ''}"))
        else:
            msg.append('That is not a valid package')

        return msg

    # create a message of all plugins
    def _build_all_plugins_message(self):
        """
        create a message of all plugins

        returns:
          a list of strings
        """
        msg = []
        packages_list = self.api(f"{self.plugin_id}:get.packages.list")()
        packages = {
            package: self.api(f"{self.plugin_id}:get.plugins.in.package")(package)
            for package in packages_list
        }
        msg.extend(self._command_helper_format_plugin_list(packages['plugins.core'],
                                                            required_color_line=False))
        del packages['plugins.core']
        for package in packages:
            if packages[package]:
                msg.extend(self._command_helper_format_plugin_list(packages[package],
                                                                   required_color_line=False,
                                                                   columnheader=False))

        return msg

    # get plugins that are change on disk
    def _get_changed_plugins(self):
        """
        create a message of loaded plugins that are changed on disk
        """
        loaded_plugins_info = [self.plugins_info[plugin_id] for plugin_id in self.api('plugins.core.pluginm:get.loaded.plugins.list')()]

        msg = []
        if list_to_format := [
            plugin_info.plugin_id
            for plugin_info in loaded_plugins_info
            if plugin_info.get_changed_files()
        ]:
            msg = self._command_helper_format_plugin_list(list_to_format, "Changed Plugins")

        return msg or ['No plugins are changed on disk.']

    def _get_invalid_plugins(self):
        """
        create a message of plugins that are invalid python code
        """
        msg = []
        if list_to_format := [
            plugin_info.plugin_id
            for plugin_info in self.plugins_info.values()
            if plugin_info.get_invalid_python_files()
        ]:
            msg = self._command_helper_format_plugin_list(list_to_format, "Plugins with invalid python code")

        return msg or ['All plugins are valid python code.']

    # get all not loaded plugins
    def _get_not_loaded_plugins(self):
        """
        create a message of all not loaded plugins
        """
        msg = []
        if self.update_all_plugin_information():
            LogRecord('conflicts with plugins, see console and correct', level='error', sources=[self.plugin_id])()

        all_plugins_by_id = list(self.plugins_info.keys())

        loaded_plugins_by_id = self.api('plugins.core.pluginm:get.loaded.plugins.list')()

        if pdiff := set(all_plugins_by_id) - set(loaded_plugins_by_id):
            list_to_format = list(sorted(pdiff))
            msg = self._command_helper_format_plugin_list(list_to_format, "Not Loaded Plugins")

        return msg or ['There are no plugins that are not loaded']

    @AddParser(description='list plugins')
    @AddArgument('-n',
                    '--notloaded',
                    help='list plugins that are not loaded',
                    action='store_true')
    @AddArgument('-c',
                    '--changed',
                    help='list plugins that are loaded but are changed on disk',
                    action='store_true')
    @AddArgument('-i',
                    '--invalid',
                    help='list plugins that have files with invalid python code',
                    action='store_true')
    @AddArgument('package',
                    help='the package of the plugins to list',
                    default='',
                    nargs='?')
    def _command_list(self):
        """
        @G%(name)s@w - @B%(cmdname)s@w
          List plugins
          @CUsage@w: list
        """
        args = self.api('plugins.core.commands:get.current.command.args')()
        msg = []

        if args['notloaded']:
            msg.extend(self._get_not_loaded_plugins())
        elif args['changed']:
            msg.extend(self._get_changed_plugins())
        elif args['invalid']:
            msg.extend(self._get_invalid_plugins())
        elif args['package']:
            msg.extend(self._get_package_plugins(args['package']))
        else:
            msg.extend(self._build_all_plugins_message())
        return True, msg

    def update_self_plugin_info(self):
        """
        update info for this plugin since it doesn't get loaded
        through the normal load routine
        """
        plugin_info = self.plugins_info['plugins._pluginm']
        del self.plugins_info['plugins._pluginm']
        plugin_info.plugin_id = self.plugin_id
        plugin_info.short_name = 'pluginm'
        plugin_info.is_required = True
        plugin_info.package = 'plugins.core'
        plugin_info.loaded_info.is_imported = True
        plugin_info.loaded_info.is_initialized = True
        plugin_info.loaded_info.is_loaded = True
        plugin_info.loaded_info.plugin_instance = self
        plugin_info.loaded_info.module = sys.modules[self.full_import_location]
        plugin_info.loaded_info.imported_time = self.loaded_time
        self.plugins_info['plugins.core.pluginm'] = plugin_info

    def update_all_plugin_information(self):
        """
        read all plugins and basic info

        returns:
          a bool, True if conflicts with short name were found, False if not
        """
        LogRecord('Read all plugin information', level='info', sources=[self.plugin_id])()

        _, plugins, errors = imputils.find_packages_and_plugins(self.base_plugin_dir, 'plugins.')

        old_plugins_info = self.plugins_info
        self.plugins_info = {}

        # go through the plugins and read information from them
        for found_plugin in plugins:
            LogRecord(f'Reading plugin information for {found_plugin["plugin_id"]}', level='info', sources=[self.plugin_id])()
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

        self.update_self_plugin_info()

        # warn about plugins whose path is no longer valid
        removed_plugins = set(old_plugins_info.keys()) - set(self.plugins_info.keys())
        for plugin_id in removed_plugins:
            if plugin_id in old_plugins_info and old_plugins_info[plugin_id].loaded_info:
                LogRecord([f'Loaded Plugin {plugin_id}\'s path is no longer valid: {old_plugins_info[plugin_id].full_package_path}',
                           'If this plugin is no longer valid, please unload it'], level='error', sources=[self.plugin_id])()

    def load_single_plugin(self, plugin_id, exit_on_error=False, run_initialize=True, check_dependencies=True):
        """
        load a plugin
          1) import Plugin - _import_single_plugin via preinitialize_plugin
          2) instantiate Plugin - _instantiate_plugin via preinitialize_plugin
          3) check for dependencies - load_plugin
              import all dependencies
                instantiate all dependencies
                add to dependency list
          4) run initialize function in dependency order
              single - initialize_plugin
              multiple - initialize_multiple_plugins

        arguments:
          required:
            plugin_id - the plugin to load

          optional:
            exit_on_error - if True, the program will exit on an error

        returns:
          True if the plugin was loaded, False otherwise
        """
        # if the plugin is required, set exit_to_error to True
        exit_on_error = exit_on_error or self.plugins_info[plugin_id].is_required

        # preinitialize plugin (imports and instantiates)
        return_value, dependencies = self.preinitialize_plugin(plugin_id,
                                                               exit_on_error=exit_on_error,
                                                               check_dependencies=check_dependencies)
        if not return_value:
            LogRecord(f"Could not preinitialize plugin {plugin_id}",
                      level='error', sources=[self.plugin_id, plugin_id])()
            if exit_on_error:
                signal.raise_signal( signal.SIGINT )
            return False

        # # build dependencies
        # new_dependencies = set(dependencies)
        # plugin_classes = [
        #     self.loaded_plugins_info[tplugin_id] for tplugin_id in new_dependencies
        # ]
        # plugin_classes.append(self.loaded_plugins_info[plugin_id])

        # # get broken plugins that didn't import
        # broken_modules = [tplugin_id for tplugin_id in new_dependencies \
        #                           if tplugin_id in self.loaded_plugins_info \
        #                             and not self.loaded_plugins_info[tplugin_id].isimported and \
        #                             not self.loaded_plugins_info[tplugin_id].dev]

        # # find the order the dependencies should be loaded
        # if check_dependencies:
        #     dependency_solver = PluginDependencyResolver(plugin_classes, broken_modules)
        #     plugin_load_order, unresolved_dependencies = dependency_solver.resolve()
        #     # print(f"{plugin_id} dependencies plugin_load_order:")
        #     # print(pprint.pformat(plugin_load_order))
        #     if unresolved_dependencies:
        #         LogRecord(f"The following dependencies could not be loaded for plugin {plugin_id}:",
        #                   level='error', sources=[self.plugin_id])()
        #         for dep in unresolved_dependencies:
        #             LogRecord(f"  {dep}", level='error', sources=[self.plugin_id])()
        #         if exit_on_error:
        #             sys.exit(1)
        #         return False
        # else:
        #    plugin_load_order = [plugin_id]

        plugin_load_order = [plugin_id]

        # initialize all plugins
        if run_initialize:
            return self.initialize_multiple_plugins(
                plugin_load_order, exit_on_error=exit_on_error
            )

        self.plugins_info[plugin_id].loaded_info.is_loaded = True

        return True

    def preinitialize_plugin(self, plugin_id, exit_on_error=False, check_dependencies=True):
        """
        import a plugin
        instantiate a plugin instance
        return the dependencies

        arguments:
          required:
            plugin_id - the plugin to preinitialize

          optional:
            exit_on_error - if True, the program will exit on an error

        returns:
          a tuple of two items
          1) a bool that specifies if the plugin was preinitialized
          2) a list of other plugins that the plugin depends on
        """
        if plugin_id in self.plugins_info:
            if (self.plugins_info[plugin_id].loaded_info
                and (plugin_instance := self.plugins_info[plugin_id].loaded_info.plugin_instance)):
                return True, plugin_instance.dependencies

        LogRecord(f"{plugin_id:<30} : attempting to load", level='info', sources=[self.plugin_id])()

        plugin_info = None
        try:
            plugin_info = self.plugins_info[plugin_id]
        except KeyError:
            LogRecord('Could not find plugin {plugin_id}', level='error', sources=[self.plugin_id])()
            return False, []

        if (
            plugin_info
            and self._import_single_plugin(
                plugin_info.full_import_location, exit_on_error
            )
            and self._instantiate_plugin(plugin_info.plugin_id, exit_on_error)
        ):
            all_dependencies = []

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

            return True, all_dependencies

        print(f"Plugin {plugin_id} got all the way to the end without preinitializing")
        return False, []

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
        success, msg, module, full_import_location = \
              imputils.importmodule(plugin_id,
                                self)
        plugin_info = self.plugins_info[plugin_id]
        if not success or not module or not full_import_location:
            plugin_info.loaded_info.is_imported = False

            if msg == 'error':
                LogRecord(f"Could not import plugin {plugin_id}", level='error', sources=[self.plugin_id])()
                if exit_on_error:
                    sys.exit(1)

            return False

        if msg == 'dev module':
            plugin_info.is_dev = True

        plugin_info.loaded_info.module = module
        plugin_info.loaded_info.is_imported = True
        plugin_info.loaded_info.imported_time =  datetime.datetime.now(datetime.timezone.utc)
        return True

    def _instantiate_plugin(self, plugin_id, exit_on_error=False):
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

        if not plugin_info.loaded_info.module:
            LogRecord(f"Could not find module for {plugin_id}", level='error',
                      sources=[self.plugin_id])()
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
                      sources=[self.plugin_id], exc_info=True)()
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

        # add plugin to lookups
        # self.plugin_lookup_by_full_import_location[plugin_info.full_import_location] = plugin_id
        # self.plugin_lookup_by_plugin_filepath[plugin_instance.plugin_path] = plugin_id

        # update plugins to load at startup
        plugins_to_load = self.api(f"{self.plugin_id}:setting.get")('pluginstoload')
        if plugin_id not in plugins_to_load and not plugin_info.is_dev:
            plugins_to_load.append(plugin_id)
            self.api(f"{self.plugin_id}:setting.change")('pluginstoload', plugins_to_load)

        LogRecord(f"{plugin_id:<30} : instance created successfully", level='info', sources=[self.plugin_id])()

        return True

    def _load_plugins_on_startup(self):
        """
        load plugins on startup
        start with plugins that have REQUIRED=True, then move
        to plugins that were loaded in the config
        """
        if self.update_all_plugin_information():
            LogRecord(
                "conflicts with plugins, see console and correct",
                level='error',
                sources=[self.plugin_id],
            )(actor = f"{self.plugin_id}.read_all_plugin_information")
            sys.exit(1)

        plugins_to_load_setting = self.api(f"{self.plugin_id}:setting.get")('pluginstoload')

        # load all core plugins first
        core_plugins = [plugin_info.plugin_id for plugin_info in self.plugins_info.values() \
                                           if plugin_info.package == 'plugins.core']

        ## load all core plugins first
        # print(f"loading core plugins: {core_plugins}")

        # load the log plugin first
        core_plugins.remove('plugins.core.log')
        core_plugins.insert(0, 'plugins.core.log')

        # print(f"loading core plugins: {core_plugins}")
        self.load_multiple_plugins(core_plugins, check_dependencies=False, run_initialize=False)
        self.initialize_multiple_plugins(core_plugins)

        # find plugins that are marked to load at startup but are not core plugins
        plugins_to_load = set(plugins_to_load_setting) - set(core_plugins)

        if plugins_not_found := [
            plugin
            for plugin in plugins_to_load
            if plugin not in self.plugins_info
        ]:
            for plugin in plugins_not_found:
                LogRecord(f"plugin {plugin} was marked to load at startup and no longer exists, removing from startup",
                          level='error', sources=[self.plugin_id])()
                plugins_to_load_setting.remove(plugin)
                plugins_to_load.remove(plugin)
            self.api(f"{self.plugin_id}:setting.change")('pluginstoload', plugins_to_load_setting)

        # print('Loading the following plugins')
        # print(pprint.pformat(plugins_to_load))
        self.load_multiple_plugins(plugins_to_load)

        found = False
        # clean up plugins that were not imported, initialized, or instantiated
        for plugin_info in self.plugins_info.values():
            if not plugin_info.loaded_info.is_loaded:
                if plugin_info.loaded_info.plugin_instance:
                    del plugin_info.loaded_info.plugin_instance
                    plugin_info.loaded_info.plugin_instance = None
                if plugin_info.loaded_info.module:
                    del plugin_info.loaded_info.module
                    plugin_info.loaded_info.module = None

        if found:
            sys.exit(1)

    def load_multiple_plugins(self, plugins_to_load, exit_on_error=False, run_initialize=True, check_dependencies=True):
        """
        load a list of plugins

        arguments:
          required:
            plugins_to_load - a list of plugin_ids to load
              plugins_to_load example:
                ['core.errors', 'core.events', 'core.msg', 'core.commands',
                'core.colors', 'core.utils', 'core.timers']

          optional:
            exit_on_error - if True, the program will exit on an error
        """
        loaded_plugins = [plugin_info.plugin_id for plugin_info in self.plugins_info.values() if plugin_info.loaded_info.is_loaded]
        for plugin in plugins_to_load:
            if plugin not in loaded_plugins:
                self.load_single_plugin(plugin, exit_on_error, run_initialize=run_initialize, check_dependencies=check_dependencies)

    def initialize_multiple_plugins(self, plugins, exit_on_error=False):
        """
        run the load function for a list of plugins

        arguments:
          required:
            plugins - a list of plugin_ids to initialize
              plugins example:
              ['core.errors', 'core.events', 'core.msg', 'core.commands',
              'core.colors', 'core.utils', 'core.timers']
          optional:
            exit_on_error - if True, the program will exit on an error

        return True if all plugins were initialized, False otherwise
        """
        all_plugins_initialized = True
        for tplugin in plugins:
            success = self.initialize_plugin(self.plugins_info[tplugin], exit_on_error)
            all_plugins_initialized = all_plugins_initialized and success

        return all_plugins_initialized

    # initialize a plugin
    def initialize_plugin(self, plugin_info: PluginInfo, exit_on_error=False):
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
        if plugin_info.loaded_info.is_initialized:
            return True
        LogRecord(f"{plugin_info.plugin_id:<30} : attempting to initialize ({plugin_info.name})", level='info',
                  sources=[self.plugin_id, plugin_info.plugin_id])()

        if not plugin_info.loaded_info.plugin_instance:
            LogRecord(f"{plugin_info.plugin_id:<30} : plugin instance is None, not initializing", level='error',
                        sources=[self.plugin_id, plugin_info.plugin_id])()
            return False

        # run the initialize function
        try:
            plugin_info.loaded_info.plugin_instance.initialize()
            plugin_info.loaded_info.is_initialized = True

        except Exception: # pylint: disable=broad-except
            LogRecord(f"could not run the initialize function for {plugin_info.plugin_id}", level='error',
                      sources=[self.plugin_id, plugin_info.plugin_id], exc_info=True)()
            if exit_on_error:
                LogRecord(f"{plugin_info.plugin_id:<30} : DID NOT INITIALIZE", level='error',
                          sources=[self.plugin_id, plugin_info.plugin_id])()
                sys.exit(1)
            return False

        LogRecord(f"{plugin_info.plugin_id:<30} : successfully initialized ({plugin_info.name})", level='info',
                    sources=[self.plugin_id, plugin_info.plugin_id])()

        self.api('plugins.core.events:add.event')(f"ev_{plugin_info.plugin_id}_initialized", self.plugin_id,
                                                    description=f"Raised when {plugin_info.plugin_id} is initialized",
                                                    arg_descriptions={'None': None})

        if not self.api.startup:
            self.api('plugins.core.events:raise.event')(f"ev_{plugin_info.plugin_id}_initialized", {})
            self.api('plugins.core.events:raise.event')(f"ev_{self.plugin_id}_plugin_initialized",
                                                {'plugin':plugin_info.name,
                                                    'plugin_id':plugin_info.plugin_id})
        LogRecord(f"{plugin_info.plugin_id:<30} : successfully loaded", level='info',
                  sources=[self.plugin_id, plugin_info.plugin_id])()

        # update plugins_to_load
        plugins_to_load = self.api(f"{self.plugin_id}:setting.get")('pluginstoload')
        if plugin_info.plugin_id not in plugins_to_load:
            plugins_to_load.append(plugin_info.plugin_id)

        plugin_info.loaded_info.is_loaded = True

        return True

    def unload_single_plugin(self, plugin_id):
        """
        unload a plugin
          1) run uninitialize function
          2) destroy instance
          3) remove from sys.modules
          4) remove from loaded_plugins
          5) remove from all the plugin lookup dictionaries

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
                        level='error', sources=[self.plugin_id, plugin_info.plugin_id])()
            return False

        try:
            # run the uninitialize function if it exists
            if plugin_info.loaded_info.plugin_instance:
                if plugin_info.loaded_info.is_initialized:
                        plugin_info.loaded_info.plugin_instance.uninitialize()
                self.api('plugins.core.events:raise.event')(f"ev_{plugin_info.plugin_id}_uninitialized", {})
                self.api('plugins.core.events:raise.event')(f"ev_{self.plugin_id}_plugin_uninitialized",
                                                    {'plugin':plugin_info.name,
                                                    'plugin_id':plugin_info.plugin_id})
                LogRecord(f"{plugin_info.plugin_id:<30} : successfully unitialized ({plugin_info.name})", level='info',
                        sources=[self.plugin_id, plugin_info.plugin_id])()
            else:
                LogRecord(f"{plugin_info.plugin_id:<30} : plugin instance not found ({plugin_info.name})", level='info',
                        sources=[self.plugin_id, plugin_info.plugin_id])()

        except Exception: # pylint: disable=broad-except
            LogRecord(f"unload: error running the uninitialize method for {plugin_info.plugin_id}", level='error',
                        sources=[self.plugin_id, plugin_info.plugin_id], exc_info=True)()
            return False

        # remove from pluginstoload so it doesn't load at startup
        plugins_to_load = self.api(f"{self.plugin_id}:setting.get")('pluginstoload')
        if plugin_info.plugin_id in plugins_to_load:
            plugins_to_load.remove(plugin_info.plugin_id)
            self.api(f"{self.plugin_id}:setting.change")('pluginstoload', plugins_to_load)

        # clean up lookup dictionaries
        # del self.plugin_lookup_by_short_name[plugin['short_name']]
        # del self.plugin_lookup_by_full_import_location[plugin_info.full_import_location]
        # del self.plugin_lookup_by_plugin_filepath[plugin_id]

        if plugin_info.loaded_info.plugin_instance:
            # delete the instance
            del plugin_info.loaded_info.plugin_instance

        if plugin_info.loaded_info.is_imported:
            if imputils.deletemodule(
                plugin_info.full_import_location
            ):
                LogRecord(f"{plugin_info.plugin_id:<30} : deleting imported module was successful ({plugin_info.name})",
                            level='info', sources=[self.plugin_id, plugin_info.plugin_id])()
            else:
                LogRecord(f"{plugin_info.plugin_id:<30} : deleting imported module failed ({plugin_info.name})",
                            level='error', sources=[self.plugin_id, plugin_info.plugin_id])()

        # remove from loaded_plugins
        del self.plugins_info[plugin_id]

        return True

    # get stats for this plugin
    def get_stats(self):
        """
        return stats for events

        returns:
          a dict of statistics
        """
        stats = {'Base Sizes': {}}
        stats['Base Sizes']['showorder'] = ['Class', 'Api', 'loaded_plugins',
                                            'all_plugin_info_from_disk']
        stats['Base Sizes']['plugins_info'] = f"{sys.getsizeof(self.plugins_info)} bytes"

        stats['Base Sizes']['Class'] = f"{sys.getsizeof(self)} bytes"
        stats['Base Sizes']['Api'] = f"{sys.getsizeof(self.api)} bytes"

        stats['Plugins'] = {
            'showorder': ['Total', 'Loaded'],
            'Total': len(self.plugins_info),
            'Loaded': len(self.api(f"{self.plugin_id}:get.loaded.plugins.list")()),
        }
        return stats

    @RegisterToEvent(event_name='ev_plugins.core.proxy_shutdown')
    def _eventcb_shutdown(self, _=None):
        """
        do tasks on shutdown
        """
        self.api(f"{self.plugin_id}:save.all.plugins.state")()

    # save all plugins
    def _api_save_all_plugins_state(self, _=None):
        """
        save all plugins
        """
        for plugin_id in self.api(f"{self.plugin_id}:get.loaded.plugins.list")():
            self.api(f"{plugin_id}:save.state")()

    @AddParser( description='load a plugin')
    @AddArgument('plugin',
                    help='the plugin to load, don\'t include the .py',
                    default='',
                    nargs='?')
    def _command_load(self):
        """
        @G%(name)s@w - @B%(cmdname)s@w
          Load a plugin
          @CUsage@w: load @Yplugin@w
            @Yplugin@w    = the id of the plugin to load,
                            example: example.timerex
        """
        args = self.api('plugins.core.commands:get.current.command.args')()
        tmsg = []
        if self.update_all_plugin_information():
            LogRecord(
                "conflicts between plugins, see errors and correct before attempting to load another plugin",
                level='error',
                sources=[self.plugin_id],
            )()
            tmsg.append('conflicts between plugins, see errors and correct before attempting to load another plugin')
            return True, tmsg

        plugin_id = args['plugin']
        plugin_found_f = False
        if plugin_id:
            if plugin_id in self.plugins_info.keys():
                plugin_found_f = True
            else:
                tmsg.append(f"plugin {plugin_id} not in cache, rereading plugins from disk")
                self.update_all_plugin_information()
                if plugin_id in self.plugins_info.keys():
                    plugin_found_f = True

        if plugin_found_f:
            if self.api(f"{self.plugin_id}:is.plugin.loaded")(plugin_id):
                tmsg.append(f"{plugin_id} is already loaded")
            elif self.load_single_plugin(plugin_id, exit_on_error=False):
                tmsg.append(f"Plugin {plugin_id} was loaded")
            else:
                tmsg.append(f"Plugin {plugin_id} would not load")
        else:
            tmsg.append(f"plugin {plugin_id} not found")

        return True, tmsg

    @AddParser(description='unload a plugin')
    @AddArgument('plugin',
                    help='the plugin to unload',
                    default='',
                    nargs='?')
    def _command_unload(self):
        """
        @G%(name)s@w - @B%(cmdname)s@w
          unload a plugin
          @CUsage@w: unload @Yplugin@w
            @Yplugin@w    = the id of the plugin to unload,
                            example: example.timerex
        """
        args = self.api('plugins.core.commands:get.current.command.args')()
        tmsg = []
        plugin = args['plugin']
        plugin_found_f = bool(plugin and plugin in self.plugins_info.keys())
        if plugin_found_f:
            if self.unload_single_plugin(plugin):
                tmsg.append(f"Plugin {plugin} successfully unloaded")
            else:
                tmsg.append(f"Plugin {plugin} could not be unloaded")
        else:
            tmsg.append(f"plugin {plugin} not found")

        return True, tmsg


    @AddParser(description='reload a plugin')
    @AddArgument('plugin',
                    help='the plugin to reload',
                    default='',
                    nargs='?')
    def _command_reload(self):
        """
        @G%(name)s@w - @B%(cmdname)s@w
          reload a plugin
          @CUsage@w: reload @Yplugin@w
            @Yplugin@w    = the id of the plugin to reload,
                            example: example.timerex
        """
        args = self.api('plugins.core.commands:get.current.command.args')()
        tmsg = []
        plugin = args['plugin']
        plugin_found_f = bool(plugin and plugin in self.plugins_info.keys())
        loaded_plugins = self.api(f"{self.plugin_id}:get.loaded.plugins.list")()
        if plugin_found_f and plugin not in loaded_plugins:
            return True, [f"Plugin {plugin} is not loaded, use load instead"]
        if not plugin_found_f:
            return True, [f"Plugin {plugin} not found"]
        if self.unload_single_plugin(plugin):
            tmsg.append(f"Plugin {plugin} successfully unloaded")
        else:
            tmsg.append(f"Plugin {plugin} could not be unloaded")
            return True, tmsg

        if self.api(f"{self.plugin_id}:is.plugin.loaded")(plugin):
            tmsg.append(f"{plugin} is already loaded")
        elif self.load_single_plugin(plugin, exit_on_error=False):
            tmsg.append(f"Plugin {plugin} was loaded")
        else:
            tmsg.append(f"Plugin {plugin} would not load")

        return True, tmsg

    @RegisterToEvent(event_name="ev_plugins.core.events_all_events_registered")
    def _eventcb_all_events_registered(self):
        """
        this resends all the different plugin initialization events
        """
        for plugin_info in self.plugins_info.values():
            if plugin_info.loaded_info.plugin_instance:
                self.api('plugins.core.events:raise.event')(f"ev_{plugin_info.plugin_id}_initialized", {})
                self.api('plugins.core.events:raise.event')(f"ev_{self.plugin_id}_plugin_initialized",
                                                    {'plugin':plugin_info.name,
                                                    'plugin_id':plugin_info.plugin_id})

    # initialize this plugin
    def initialize(self):
        """
        initialize plugin
        """

        self.can_reload_f = False
        self.auto_initialize_f = False
        LogRecord('Loading plugins', level='info', sources=[self.plugin_id])()
        self._load_plugins_on_startup()

        super().initialize()

        super()._add_commands()

        self.api('plugins.core.timers:add.timer')('global_save', self._api_save_all_plugins_state, 60, unique=True, log=False)

        self.api('plugins.core.events:add.event')(
            f"ev_{self.plugin_id}_plugin_initialized",
            self.plugin_id,
            description="Raised when any plugin is initialized",
            arg_descriptions={
                'plugin': 'The plugin name',
                'plugin_id': 'The plugin id',
            },
        )
        self.api('plugins.core.events:add.event')(
            f"ev_{self.plugin_id}_plugin_uninitialized",
            self.plugin_id,
            description="Raised when any plugin is initialized",
            arg_descriptions={
                'plugin': 'The plugin name',
                'plugin_id': 'The plugin id',
            },
        )

        self.initializing_f = False

        self.api(f"{self.plugin_id}:save.all.plugins.state")()

        loaded_plugins = self.api(f"{self.plugin_id}:get.loaded.plugins.list")()
        for plugin_id in loaded_plugins:
            self.api('plugins.core.events:add.event')(f"ev_{plugin_id}_initialized", self.plugin_id,
                                                        description=f"Raised when {plugin_id} is initialized",
                                                        arg_descriptions={'None': None})
            self.api('plugins.core.events:add.event')(f"ev_{plugin_id}_uninitialized", self.plugin_id,
                                                        description=f"Raised when {plugin_id} is uninitialized",
                                                        arg_descriptions={'None': None})

        self.api('plugins.core.events:raise.event')('ev_core.plugins.pluginm_post_plugins_initialize')

        # warn about plugins that had import errors
        for plugin_info in self.plugins_info.values():
            if plugin_info.import_errors:
                for error in plugin_info.import_errors:
                    traceback_message = traceback.format_exception(error[1])
                    traceback_message = [item.strip() for item in traceback_message if item and item != '\n']
                    LogRecord([f'Plugin {plugin_info.plugin_id} had an import error: ', *traceback_message],
                                level='warning', sources=[self.plugin_id])()
